# 最终程序架构：HAOS 四 App + MQTT 总线

> 状态：**现行目标架构**（2026-11-26）  
> 一句话：一台 HAOS 主机跑四个 Supervisor 托管的 App（HA 本体 + Mosquitto + Frigate Full Access + **SmartCenter Add-on**），一条 MQTT 总线串起来，一个 HACS 集成（Frigate Integration）做 HA 侧实体翻译，云端 FastAPI 做 M 端业务决策，所有硬件直连各自的管理节点（摄像头→Frigate，ESP 门禁板→ESPHome）。  
> **人脸**：Frigate 关 Face Recognition；交互式采集、人脸库治理、门口比对、概览/审计工作台见 [人脸-SmartCenter-Add-on.md](人脸-SmartCenter-Add-on.md)。本机开发：[开发工作流.md](开发工作流.md)。

自研 [SmartCCTV](决策-归档自研SmartCCTV.md) 已裁定归档，不进入本架构。

---

## 一、总部署图

```text
┌──────────────────── HAOS 主机（N100 小主机 + USB Coral TPU）────────────────────┐
│ Supervisor（安装 / 备份 / 升级 / 看门狗）                                         │
│                                                                                │
│ ① HA 本体                    ② Mosquitto（App）      ③ Frigate Full Access     │
│   ├── Frigate Integration      唯一总线                视频中枢                  │
│   │   （HACS，MQTT 发现）      topic: frigate/# 等     ├── go2rtc 拉流/分发      │
│   ├── MQTT 集成                                         │   摄像头×N 只被拉 ≤2  │
│   ├── 自动化×N（零智能）                                 ├── 检测(Coral+ONNX+zone)│
│   └── 侧边栏 iframe ×2                                   ├── 录像→数据盘(如30天) │
│       ├→ Frigate Web :5000                              └── SQLite 事件库      │
│       └→ SmartCenter Add-on Ingress（采集/人员）                                 │
│                                                                                │
│ ④ SmartCenter Add-on（本地 App · 「智能」唯一住处；人脸控制面）                     │
│    ├── Ingress 工作台（无自建登录）：概览 / 采集 / 人脸库 / 审计                    │
│    ├── 人脸会话 + 本地底库（SQLite，向量不出店）+ 容量维护                           │
│    ├── MQTT：订 frigate/# → 门口比对 → 发 business/access/grant                  │
│    ├── go2rtc 查询型短窗拉流（仅门口有人时）                                       │
│    └── 后续可扩展：利用率看板                                                      │
└──────────────────────────────┬───────────────────────────────────────────────────┘
                               │ MQTT（经路由器，可桥接）
┌──────────────────────────────┴────────────────────────┐
│ 硬件层（各自直连管理节点，不经「总控 HTTP」中转）        │
│  RTSP 摄像头×N ──→ ③ Frigate / go2rtc                 │
│  ESP32 教室总控──→ ESPHome（门/RFID/DHT/警号）→ MQTT │
│  Zigbee 门磁等 ──→ HA (ZHA 等) → 实体                 │
└─────────────────────────────────────────────────────────┘
                               ↑ 云端（VPS，不在 Supervisor 内）
┌──────────────────────────────┴────────────────────────┐
│ 云端 FastAPI（M 端 / LOBN_FireClassroom backend）       │
│   排班 join、交易决策、推送、报表                       │
│   └── 人脸会话中继；经 MQTT bridge / webhook 消费指标   │
└─────────────────────────────────────────────────────────┘
```

---

## 二、四个 App + 一个集成的职责契约

| 组件 | 做什么 | 绝不做什么 |
|------|--------|------------|
| **① HA 本体** | 设备/实体中枢；保命自动化（监听 `business/access/grant` → 发 `home/<node>/door/command`）；侧边栏 iframe；MQTT / ZHA 等集成 | **零智能**：不写分析、排班 join、滞留判定、经营报表逻辑 |
| **② Mosquitto** | 唯一跨 App 事件/指令总线 | 不承载业务逻辑 |
| **③ Frigate Full Access** | 拉流（go2rtc）、检测、zone、录像、发 `frigate/#`；**关闭 Face Recognition** | **零业务**：不做身份底库、不判定「谁能进门」 |
| **④ SmartCenter Add-on** | 采集写库、人脸库治理、门口比对→`grant`、概览统计与审计；鉴权靠 HA Ingress | 不直连摄像头独占；不拉继电器；不进 HA 进程；无自建账号/RBAC |
| **HACS Frigate Integration** | 把 Frigate MQTT/API 译成 HA 实体，供仪表盘与保命自动化引用 | 不替代 Add-on 做业务决策 |
| **云端 FastAPI** | 交易、排班权威数据、推送、报表；人脸帧**中继**（不落长期照片） | 不发门脉冲；不存店内录像主副本；不存 embedding |
| **ESPHome 教室总控** | 订 `home/<node>/door/command` / `…/rfid/allowlist`；脉冲门与警号；上报门 state、sense、RFID event、温湿度 | 不接受非总线私有 HTTP 开门；不编辑白名单；不连预约平台 |
| **RFID 资产防盗** | 整段在 SmartCenter：ESP 本地比对 + HA 名单/通知 | **不进** LOBN_FireClassroom；Add-on **不在**报警关键路径 |

原则沉淀：**感知在 Frigate，智能在 SmartCenter Add-on，保命与设备在 HA，交易在云端，执行在 ESPHome。**  
人脸专文：[人脸-SmartCenter-Add-on.md](人脸-SmartCenter-Add-on.md) · 资产防盗：[资产防盗-RFID.md](资产防盗-RFID.md)。

---

## 三、MQTT 主题规划（总线宪法）

**纪律**

1. 硬件/感知状态上总线：`frigate/#`、`home/#`  
2. 业务指标与业务指令上总线：`business/#`  
3. 执行指令上总线：`home/<node>/door/command`（及对称的 `…/door/state`；`<node>` = 教室总控 `room_id`）  
4. **跨 App 通信只走 MQTT**；**禁止** App 间私下点对点长连接做事件/指令  
5. **REST 仅查询型**：Add-on → go2rtc / Frigate（短窗帧、只读查询）

### 3.1 主题表（初版骨架）

| 主题 | 方向 | 载荷要点 |
|------|------|----------|
| `frigate/events` | Frigate → 总线 | 官方事件 JSON（new/update/end、label、zones、snapshot 等） |
| `frigate/<camera>/person` 等 | Frigate → 总线 | 人数/对象计数类（以 Frigate 实际发布为准） |
| `frigate/tracked_object_update` | Frigate → 总线 | （可选）对象 enrich；**不用** Frigate 人脸名做开门 |
| `home/<node>/door/command` | HA / lobn_office → ESPHome | `home.door.command.v1` 或纯文本 `OPEN`；`<node>` 如 `classroom_1`、`front_gate` |
| `home/<node>/door/state` | ESPHome / 门磁 → 总线 | `open` / `closed` |
| `home/<node>/door/sense`（可选） | ESPHome → 总线 | pir/button 边沿（替代旧 HTTP sense） |
| `home/<node>/rfid/event` | ESPHome → 总线 | 通道读到标签：`tag_id`、`allowed`、`gate`、`ts`（见 `home.rfid.event.v1`） |
| `home/<node>/rfid/allowlist` | HA → ESPHome（**retained**） | 允许过通道的标签列表（见 `home.rfid.allowlist.v1`） |
| `business/access/grant` | SmartCenter Add-on → 总线 | `{door, ttl, reason, subject, command_id, expires_at, …}` **不是**直接脉冲 |
| `business/access/deny`（可选） | Add-on → 总线 | 审计用拒绝原因 |
| `business/analytics/<room>` | Add-on（后续）→ 总线 | `{avg, peak, ts, …}` 利用率等 |
| `business/notify/outbox`（可选） | Add-on → 总线 | 待推送摘要，由 HA/云端消费 |
| `business/cloud/#`（可选） | 云端 bridge ↔ 店 | 排班缓存刷新、报表回执 |

字段只增不改：正式 JSON 样例落在 `docs/contracts/`（新建 `business.access.grant.v1.json` 等时追加，不改旧 `smartcctv.*` 样义）。

---

## 四、核心数据流

### 链路 A：刷脸 → 开门（最重业务链）

1. 摄像头 → go2rtc(Frigate) → 门口 zone 检出 `person`（不做 Frigate 人脸）  
2. Frigate → MQTT `frigate/events`  
3. SmartCenter Add-on 订事件 → go2rtc 短窗比对本地底库（冷却 / 多人同框 / 多帧一致）  
4. 命中 → MQTT `business/access/grant`（`reason=face_match`，带 `command_id` / `expires_at`）  
5. HA 自动化监听 grant → 发布 `home/<node>/door/command`  
6. ESPHome 脉冲 → `home/<node>/door/state`  
7. Add-on 记审计与机会式验证（`accepted`→`verified` 或退回 `pending`）

### 链路 B：教室利用率（后续扩展，不阻塞刷脸）

1. `frigate/<classroom>/person` 等计数流 → Add-on 滑动窗口  
2. 每 N 分钟 → `business/analytics/<room>` `{avg, peak, ts}`  
3. HA MQTT 发现 → `sensor.*_utilization` 仪表盘  
4. 云端订阅/拉取 → 时序 → 周月报

### 链路 C：纠纷取证导出（后续扩展）

1. 侧边栏 iframe → Frigate Web → Export  
2. 片段落入 `/media/frigate/exports/`（只读挂载）  
3. 可选 rclone 加密上传 → 清理本地  
4. 家长请求 → 云端生成带签名临时下载链

---

## 五、SmartCenter Add-on 内部结构

仓库落点：[addon/](../addon/)。**不**把人脸模型塞进 `custom_components`。

```text
addon/
├── config.yaml / Dockerfile / run.sh
├── web/                    # Vite+React 源码（Radix / Lucide；Frigate 风格侧栏）
├── app/
│   ├── main.py             # API + Ingress 静态
│   ├── face/               # 会话、质量门控、门口比对
│   ├── store.py            # SQLite 底库 / 审计 / 统计
│   ├── maintenance.py      # 长时间运行：裁剪 / 孤儿帧 / 会话 TTL
│   ├── mqtt_bus.py
│   └── webui/              # 构建产物（HashRouter，base ./）
└── tests/
```

**选型**：FastAPI + aiomqtt + SQLite（WAL）+ 工作台 SPA。嵌入可插拔（开发 Mock；生产 ONNX）。零 HA Python 依赖即可迁独立宿主。  
**工作台四页**：概览 · 采集 · 人脸库 · 审计（门口比对全自动、无操作页）。  
**鉴权**：仅 HA Ingress；Add-on 不做登录 UI。

---

## 六、实施顺序（四阶段）

纪律：先保命与感知，再刷脸 Add-on；利用率/取证不阻塞刷脸上线。步骤见 [部署体系.md](部署体系.md)。

| 阶段 | 内容 | 完成标准 |
|------|------|----------|
| **① 底座** | HAOS + Mosquitto + Frigate Full Access + Coral；关 Face Recognition；HACS Frigate Integration | 预览/录像/zone 事件上 `frigate/#` |
| **② 执行层** | ESPHome 教室总控 + 门磁；HA `door_mqtt`；可选 RFID | 无 Add-on 也能钥匙/店员路径开门 |
| **③ SmartCenter Add-on** | Ingress 工作台；底库；门口比对→grant；容量维护；`face_grant_mqtt`；`/data` 备份 | 刷脸可开；工作台可用；边界单测通过 |
| **④ 扩展** | 利用率看板、排班 join、取证 rclone | 不阻塞刷脸上线 |

---

## 七、故障域与备份

| 层 | 挂了会怎样 | 备份 |
|----|------------|------|
| **保命层**（ESPHome + HA 基础自动化 + 物理钥匙并联） | 店可降级营业 | HAOS Supervisor 快照；ESPHome 固件仓 |
| **感知层**（Frigate） | 无人脸自动放行；利用率停；预约/手动开门仍可走保命路径 | Frigate config + 录像盘；Coral 驱动 |
| **智能层**（SmartCenter Add-on） | 无人脸自动开门；保命层不受影响 | Add-on 镜像 + `/data`（库+合格帧）备份 |
| **云端** | 新单/排班同步受影响；店内已缓存策略可短时继续 | VPS 备份；店不依赖云发脉冲 |

**容错本质**：智能层全挂 → 降级运行，不停摆。

Supervisor 备份范围：HA 配置、Mosquitto、Frigate、Add-on `/data` 与选项、录像盘策略。

---

## 八、五条架构铁律

1. **HA 零智能**：只做设备翻译与保命自动化；分析/决策不进 HA 进程。  
2. **Frigate 零业务 / 零人脸库**：只做检测/录像/事件；身份与开门判定在 SmartCenter Add-on。  
3. **总线即宪法**：跨 App 事件与指令只走 MQTT；REST 仅查询（含 go2rtc 短窗）。  
4. **摄像头单连接**：视频消费经 go2rtc；摄像头侧连接数 ≤2。  
5. **可迁移性**：Add-on 可迁独立宿主；换嵌入模型靠 `model_version` + 本地合格帧重嵌。

---

## 九、与旧形态对照（归档 SmartCCTV / 旧 lobn 门协议）

| 旧 | 新 |
|----|----|
| 自研 SmartCCTV FastAPI :8300 | Frigate + SmartCenter Add-on（Ingress） |
| Frigate Face Recognition | **关闭**；Add-on 交互式底库 |
| HMAC A/C + `smartcctv.event.v1` HTTP | MQTT `frigate/#` + `business/#` |
| `door.command.v1` HTTP → 自研 ESP 固件 | `home/<node>/door/command` → ESPHome |
| `lobn_office` 内做人脸热路径 | Add-on 发 grant；HA 只翻译成 command |

旧契约样例保留在 [contracts/](contracts/)，标注历史，见 [接口契约.md](接口契约.md)。

---

## 十、一句话总结

完整程序架构：一台 HAOS，Supervisor 托管四个 App——HA（设备中枢+保命）、Mosquitto（唯一总线）、Frigate Full Access（视频中枢，关人脸库）、SmartCenter Add-on（人脸控制面：采集/库/比对/统计）；HACS Frigate 集成做实体翻译；MQTT 分 `frigate/#` / `home/#` / `business/#`；刷脸链路经总线串联；智能层挂掉时保命层仍转。
