# SmartOffice：办公室总管

> 配套 [架构-HAOS四App.md](架构-HAOS四App.md) · 部署 [部署体系.md](部署体系.md) · 本机 [开发工作流.md](开发工作流.md)。  
> Frigate **关闭** Face Recognition，负责录像与 go2rtc；人员、空间、放行、在场、值守、问询的判断在本 Add-on（[`addon/`](../addon/)）。  
> 面板产品名：**SmartOffice**（slug `smartoffice`）。旧称 SmartCenter 仅指已归档的子模块仓库。

SmartOffice = 这台 HA 上的**办公室总管**：补上 HA 不做的判断（这是谁、这间空间里有没有人、这扇门该不该开、这件资产是谁的、现在要不要叫人）。HA 继续当设备宿主和保命执行。交易留在各自的业务仓库。预约（FireClassroom）只是第一个**场景适配器**，不是产品主线。

## 四问（任何功能先过）

1. **总管挂了还必须能用吗？** → HA / ESP（脉冲、RFID 警号、保命按钮）。
2. **是关于「这间办公室」的事实或判断吗？** → 总管。
3. **是某门生意的钱和单据吗？** → 场景仓库（云端）。
4. **是设备的读数或动作吗？** → 实体先落 HA；总管消费读数、发布意图，不摸设备。

## 三方契约

| 层 | 职责 | 不做 |
|----|------|------|
| **HA** | 传感器实体、grant→脉冲、环境意图→climate/light、布防状态仪表盘、保命按钮、Ingress 登录 | 零判断 |
| **SmartOffice** | 人员/访客、空间/围栏、布防、资产台账、策略窗口、告警审计、环境意图、问询 | 不摸设备、不做交易、不越级保命 |
| **场景仓库** | 钱和单据；交出策略窗口（如 `grant.v1`） | 不碰设备、白名单、向量 |

传感器设备与历史归 HA；「太热 / 人走了灯还亮」的判断归总管；预约平台不读原始传感器。

## 职责一览

| 做 | 不做 |
|----|------|
| 人员档案 + 人脸凭证 + 访客有效期 | 相册上传当完成；向量出店；学员建成 HA person |
| 空间（门/房间/通道）+ 围栏 + 人数 + 滞留 | 第二路 RTSP；摄像头管理台 |
| 仲裁器唯一发 `business/access/grant` | 拉继电器 |
| 策略窗口（预约适配器其一） | 编辑预约 / 收款 |
| 资产台账 → retained 白名单；订 RFID 事件进告警 | 驱动警号；采购财务 |
| 布防时刻；环境意图 `business/environment/<space>` | climate 集成 |
| 统一告警总线 + 问询（解释脸 / VLM / 助理） | 模型直接开门或改布防；对直播跑 VLM |
| Ingress 工作台（总览 / 空间 / 人员 / 记录） | 自建账号 / RBAC / 门店切换 |

在线 AI **不在**放行热路径上；未配置 `ai_base_url` 则相关按钮隐藏。

## 开门仲裁

```text
人脸比对 / 策略窗口 / 店员手动
        ↓ AccessRequest（source=face_match|schedule|staff_manual）
   access 仲裁器（门冷却 · command_id 去重 · 单事务记账）
        ↓ 唯一 publish
   MQTT business/access/grant
        ↓
   HA face_grant_mqtt → home/<node>/door/command
```

- 仲裁器唯一调用 `publish_grant`；**发布成功才记门冷却**。
- `access_ledger`：跨来源流水；`match_audit`：比对明细。
- HA `door_mqtt.yaml` 保命按钮留下，不进审计。

## 人员模型（办公室造访 ≠ 预约凭证）

人员管理覆盖**所有被监控识别到的人**（含陌生人），不只是员工/学员。

| 概念 | 含义 |
|------|------|
| **人员档案** | 本店出现过或录入过的人；`person_kind`=`staff\|student\|visitor\|stranger` |
| **人脸凭证** | 向量底库；可来自店员采集或预约平台（`origin=booking`） |
| **造访 visits** | 监控真实识别到才记；`sighted` / `visit_count` / `last_seen_at` |
| **仅凭证** | 预约录入了脸但 `visit_count=0`：人还没真来过办公室 |
| **关联 link** | 陌生人档可合并到正式 `user_id`（向量+造访迁过去） |
| **手动建档** | 未识别也可 `POST /api/persons` 录入姓名/身份/备注，再相册上传或现场采集 |
| **相册入库** | `POST …/photos` 追加可见参考图（借鉴 FaceID）；单张可删；约 20 张上限 |
| **忽略** | `ignored`：再识别作负锚、不告警、不开门 |

刷脸开门另判：`can_open_by_face`（非陌生人 + 未忽略 + accepted/verified + 未过期）。陌生人会建档、会计造访，**默认不开门**。

## face_status / 访客

`none` → `pending` → `accepted` → `verified`；`rejected` 停用。  
访客也是人：`valid_until` 到期自动退出比对；活动空间可受限；到期前提醒。

## 通用 · 场景 · HA

**一套资源 + 作用域视图**（勿复制人员/资产模块）。详见 [架构-通用与场景.md](架构-通用与场景.md)。

| | 通用（全店） | 场景（如教室） | HA |
|--|--|--|--|
| 人/资产/监控/门 | 全量台账 | 同 API，按 `scene`/`space` 过滤 | — |
| 预约 / 教室网 | — | 场景适配器 / 专有插件 | — |
| ESPHome、灯、空调 | 意图 | 场景页深链/展示 | 实体与执行 |

`spaces.access_mode`：`face` · `schedule` · `always_open`（里门常开仍识别）· `armed_only`。预约关掉不影响造访与陌生人建档。

## 工作台

无自建登录。深色 Ingress；可折叠侧栏。手机底栏：**总览 · 空间 · 人员 · 记录**（场景入口渐进增加）。门口是某个空间的详情。助理是抽屉。

| 路由 | 职责 |
|------|------|
| `#/overview` | 待处理告警、有人的空间、今日放行、正在布防 |
| `#/spaces` · `#/spaces/:id` | 空间列表 / 画面·围栏·手动开·人数·布防·门禁模式 |
| `#/people` · `#/people/:id` · `…/capture` | 人员与采集（手机前置摄像头） |
| `#/audit` | 放行流水 + 告警 |
| API `/api/scenes` | 场景透镜（绑定 space_ids + adapter） |

## 长期运行铁则

- 每个表有界（流水条数+天；窗口过期即删；人工表以空间/物件为上限）。
- 热路径不碰盘（冷却内存化；一次 grant 单事务；dashboard 60s 缓存）。
- 文件不漫游（会话目录定点清理；告警/VLM 临时目录 TTL+容量）。
- 入站防抖（忙则丢；RFID event_id；门磁边沿；告警去抖/锁存）。
- 出站限流（AI 令牌桶，超限 429，无自动重试）。
- 外部退避（go2rtc / 云端 / AI）；失败只降级不挂死。
- 启动 `PRAGMA quick_check`；库损坏隔离另起，门可用性优先。

## 主要 HTTP API（摘要）

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/healthz` | 就绪 |
| GET | `/api/stats` | 总览（缓存） |
| GET/POST | `/api/spaces` · `…/{id}` | 空间 |
| POST | `/api/spaces/{id}/open` | 手动开门 staff_manual |
| GET/POST | `/api/alerts` | 告警 |
| GET/POST | `/api/assets` | 资产台账 |
| POST | `/api/assets/publish-allowlist` | 显式发布白名单 |
| GET | `/api/audit` · `/api/match-audit` | 流水 |
| POST | `/api/ai/explain-crop` · `/api/ai/transcribe` · `/api/ai/assist` | 问询（限流） |

鉴权：生产靠 HA Ingress；本机 `SMARTCENTER_DEV_AUTH=1`。

## 仓内路径

| 路径 | 说明 |
|------|------|
| `addon/` | Supervisor Add-on |
| `addon/app/access/` | 开门仲裁 |
| `addon/app/alerts/` | 统一告警总线 |
| `addon/app/face/` | 采集 / 比对 |
| `addon/app/detect/` | 人体 / 遗留物 |
| `addon/web/` | 工作台源码 |
| `config/packages/face_grant_mqtt.yaml` | grant → 门脉冲 |
| `config/packages/door_mqtt.yaml` | 保命手动开门 |
