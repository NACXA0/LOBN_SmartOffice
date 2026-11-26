# SmartCenter Add-on：交互式人脸与刷脸开门

> 配套 [架构-HAOS四App.md](架构-HAOS四App.md) · 部署 [部署体系.md](部署体系.md) §5 · 本机 [开发工作流.md](开发工作流.md)。  
> Frigate **关闭** Face Recognition；底库与比对在本 Add-on。

## 职责

Add-on = **本店人脸控制面**（采集写库、库治理、门口仲裁、可观测）。HA 只负责登录与 Ingress；不开自建账号、不做 RBAC。

| 做 | 不做 |
|----|------|
| 交互式采集会话（质检循环 → 写底库） | 单张相册上传当完成 |
| **人脸库管理**（查/启停/删/改名/补采/合格帧） | 向量出店、上云、跨店共享 |
| 门口 zone `person` → go2rtc 短窗比对 → `grant` | 拉继电器（HA package） |
| **统计概览**（状态分布、开门 grant/deny、待重采队列） | 云端 BI / 长留存分析 |
| 开门审计 + 链路健康 | 自建员工账号（权限用 HA） |

## face_status

`none` → `pending`（采集中）→ `accepted`（底库可开，未验证）→ `verified`（门口前 3 次达标）  
连续 3 次门口低于验证线 → 退回 `pending`。`rejected` 由工作人员拒绝。云端只展示状态；开门以本地底库为准（停用指令以云端为准）。

## 采集渠道

| 渠道 | 入口 | 鉴权 |
|------|------|------|
| 工作人员 | HA Ingress 工作台 `getUserMedia`（USB / 官方 App） | HA 管理员 |
| 学生 | 小程序 `faceEnroll` → 云端 `/api/face/session/*` → Add-on | 学员 JWT；云端只中继帧 |

合格条件：检出分、脸框、五官点、清晰度、正脸；连续多帧 + 轻微姿态变化；静止照片拒。**物理上无文件选择器**。

关键流程（工作人员）：搜索选人 → 开始会话 → 自动质检送帧 → 凑满 N 帧写库 → 门口试刷转 `verified`。

## 仲裁（门口）

- 同人冷却 30s（单调钟 + 落盘；重启不丢）
- 多人同框：全部匹配才开（现实现：多帧须同一身份，否则拒）
- 多帧一致性：单帧高分不够
- 失败关闭：模型 / go2rtc / Frigate 不可用 → 人脸路径停，店员手动仍可开
- 红外/灰度跳过；同一摄像头单飞比对；MQTT 洪峰时比对限流（忙则丢）

## 底库保命

- 向量行带 `model_version`；本地保留合格帧供换模型重嵌（`/api/admin/reembed`）
- `/data` SQLite **在线备份**（勿热拷贝库文件）；WAL 模式
- 备份不进 git、不进云端对象存储

## 长时间运行（容量与稳定性）

面向 7×24 门口流量，所有会「只增不减」的路径都有上限：

| 增量源 | 风险 | 收敛策略（默认） |
|--------|------|------------------|
| 应用日志 | 磁盘打满 | `data/logs/smartcenter.log` **滚动**（5×5MB，可配） |
| `match_audit` | DB 膨胀 | 保留最近 **5000** 条或 **30** 天，周期裁剪 |
| `grants_seen` | 去重表膨胀 | 保留 **48h**（仅防短窗重放） |
| 采集半成品帧 | 管理员关页残留 | 会话 TTL **30min** 超时丢弃；孤儿 jpg 周期扫 |
| Frigate `event_id` 内存表 | 进程内存涨 | 5min 滑动窗口清理 |
| MQTT 抓帧洪峰 | 协程堆积 / OOM | `match_concurrency`（默认 1）忙则丢、不排队 |
| SQLite | 锁/碎片 | WAL + `PRAGMA optimize` / wal_checkpoint |
| 在线备份 | 备份目录涨 | 仍只留最近 **10** 份 |

维护任务默认每 **15min**（`maintenance_interval_sec`）；`/healthz` 带 `store` 行数与库体积。磁盘余量不足 64MB 时拒采集并跳过门口比对写库。

可在 Add-on options 调整：`audit_max_rows`、`audit_max_age_days`、`log_max_mb`、`log_backup_count`、`session_ttl_sec` 等。

## Ingress 工作台 UI

无自建登录、无 RBAC：HA Ingress 进 → **管理员工作台**（Frigate 风格：无顶栏，侧栏导航）。

| 页 | 职责映射 |
|----|----------|
| **概览** | 统计：库规模、状态分布、24h/7d 开门、待重采队列、运行时 |
| **采集** | 搜索选人 → 自动质检送帧；无相册上传 |
| **人脸库** | 列表 + 详情抽屉（改名/帧/验证计数）· Switch 启停 · 删除确认 · 补采 |
| **审计** | 门口流水 + 链路灯 |

桌面：侧栏四键 + 底栏状态；手机：底栏。源码 `addon/web/`（React · Radix · Lucide），构建 `app/webui/`（`base: './'`，适配 Ingress）。  
门口比对**无操作页**（全自动），结果进审计与概览。

本地一键开发（`./START.sh all`）：**Vite HMR + uvicorn --reload + 本机 HA**，主打开 `:5173`。见 [开发工作流.md](开发工作流.md)。

## 主要 HTTP API（摘要）

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/healthz` | 就绪 / 磁盘 / MQTT / store 计数 |
| GET | `/api/stats` | 概览仪表盘 |
| GET | `/api/persons` · `/api/persons/search` | 列表 / 本地+云端反查 |
| GET/PATCH | `/api/persons/{id}` | 详情（含帧列表）/ 改名 |
| GET | `/api/persons/{id}/thumb` · `.../frame/{i}` | 缩略图 / 分帧 |
| POST | `/api/persons/{id}/enable|disable` · DELETE | 启停 / 删 |
| POST | `/api/enroll/start` · `.../{sid}/frame` · `.../cancel` | 采集会话 |
| GET | `/api/audit` | 开门流水 |
| POST | `/api/admin/reembed` | 换模型重嵌 |

鉴权：生产靠 HA Ingress / Supervisor；本机可 `SMARTCENTER_DEV_AUTH=1`。

## 仓内路径

| 路径 | 说明 |
|------|------|
| `SmartCenter/addon/` | Supervisor Add-on（Ingress + MQTT + FastAPI） |
| `SmartCenter/addon/web/` | 工作台源码 |
| `SmartCenter/addon/app/webui/` | 构建产物 |
| `SmartCenter/config/packages/face_grant_mqtt.yaml` | grant → 门脉冲 |
| `LOBN_FireClassroom/backend/.../face.py` | 会话中继 + `face_status` 回写 + 学员搜索 |
| `docs/examples/frigate.config.face-door.example.yml` | Frigate 门口 zone 样例 |

本地单测：`cd SmartCenter && ./START.sh addon-test`（或 `addon && .venv/bin/pytest -q`）。
