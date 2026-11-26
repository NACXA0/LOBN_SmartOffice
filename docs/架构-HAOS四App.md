# 最终程序架构：HAOS 四 App + MQTT 总线

> 状态：**现行目标架构**（2026-11-25）  
> 一句话：一台 HAOS 主机跑四个 Supervisor 托管的 App（HA 本体 + Mosquitto + Frigate Full Access + analytics-sidecar），一条 MQTT 总线串起来，一个 HACS 集成（Frigate Integration）做 HA 侧实体翻译，云端 FastAPI 做 M 端业务决策，所有硬件直连各自的管理节点（摄像头→Frigate，ESP 门禁板→ESPHome）。

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
│       └→ sidecar 看板 :8080                                                     │
│                                                                                │
│ ④ analytics-sidecar（本地 App · 本项目「智能」唯一住处）                          │
│    ├── MQTT 订阅: frigate/#、home/#、business/#（按需）                           │
│    ├── Frigate REST（查询型）: /api/events、latest.jpg                            │
│    ├── 分析: 滞留 / 到岗 / 轨迹 / 热力                                            │
│    ├── SQLite 自持库（指标 / 审计）                                               │
│    └── FastAPI :8080 看板 + webhook                                              │
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
│   └── 经 MQTT bridge 或 webhook 消费 sidecar 指标      │
└─────────────────────────────────────────────────────────┘
```

---

## 二、四个 App + 一个集成的职责契约

| 组件 | 做什么 | 绝不做什么 |
|------|--------|------------|
| **① HA 本体** | 设备/实体中枢；保命自动化（监听 `business/access/grant` → 发 `home/*/command`）；侧边栏 iframe；MQTT / ZHA 等集成 | **零智能**：不写分析、排班 join、滞留判定、经营报表逻辑 |
| **② Mosquitto** | 唯一跨 App 事件/指令总线 | 不承载业务逻辑 |
| **③ Frigate Full Access** | 拉流（go2rtc）、检测、zone、人脸库、录像、发 `frigate/#` | **零业务**：不判定「谁能进门」、不做利用率报表 |
| **④ analytics-sidecar** | 订阅感知与状态；分析；开门决策发 `business/access/grant`；指标发 `business/analytics/#`；审计 SQLite；看板 :8080 | 不直连摄像头；不直接拉继电器；不进 HA Python 进程 |
| **HACS Frigate Integration** | 把 Frigate MQTT/API 译成 HA 实体，供仪表盘与保命自动化引用 | 不替代 sidecar 做业务决策 |
| **云端 FastAPI** | 交易、排班权威数据、推送、报表、签名下载链 | 不发门脉冲；不存店内录像主副本 |
| **ESPHome 教室总控** | 订 `home/*/command` / `…/rfid/allowlist`；脉冲门与警号；上报门 state、sense、RFID event、温湿度 | 不接受非总线私有 HTTP 开门；不编辑白名单；不连预约平台 |
| **RFID 资产防盗** | 整段在 SmartCenter：ESP 本地比对 + HA 名单/通知 | **不进** LOBN_FireClassroom；sidecar **不在**报警关键路径 |

原则沉淀：**感知在 Frigate，智能在 sidecar，保命与设备在 HA，交易在云端，执行在 ESPHome。**  
资产防盗专文：[资产防盗-RFID.md](资产防盗-RFID.md)。

---

## 三、MQTT 主题规划（总线宪法）

**纪律**

1. 硬件/感知状态上总线：`frigate/#`、`home/#`  
2. 业务指标与业务指令上总线：`business/#`  
3. 执行指令上总线：`home/<device>/command`（及对称的 `…/state`）  
4. **跨 App 通信只走 MQTT**；**禁止** App 间私下点对点长连接做事件/指令  
5. **REST 仅查询型**：sidecar → Frigate `:5000`（事件列表、快照、导出目录只读挂载）

### 3.1 主题表（初版骨架）

| 主题 | 方向 | 载荷要点 |
|------|------|----------|
| `frigate/events` | Frigate → 总线 | 官方事件 JSON（new/update/end、label、zones、snapshot 等） |
| `frigate/<camera>/person` 等 | Frigate → 总线 | 人数/对象计数类（以 Frigate 实际发布为准） |
| `frigate/tracked_object_update` | Frigate → 总线 | 人脸 sub_label 等 enrich |
| `home/<door>/command` | HA 保命自动化 → ESPHome | 如 `OPEN` + ttl / command_id |
| `home/<door>/state` | ESPHome / 门磁 → 总线 | open/closed、来源 |
| `home/<door>/sense`（可选） | ESPHome → 总线 | pir/button 边沿（替代旧 HTTP sense） |
| `home/<room>/rfid/event` | ESPHome → 总线 | 通道读到标签：`tag_id`、`allowed`、`gate`、`ts`（见 `home.rfid.event.v1`） |
| `home/<room>/rfid/allowlist` | HA → ESPHome（**retained**） | 允许过通道的标签列表（见 `home.rfid.allowlist.v1`） |
| `business/access/grant` | sidecar → 总线 | `{door, ttl, reason, subject, ts, …}` **不是**直接脉冲 |
| `business/access/deny`（可选） | sidecar → 总线 | 审计用拒绝原因 |
| `business/analytics/<room>` | sidecar → 总线 | `{avg, peak, ts, …}` 利用率等 |
| `business/notify/outbox`（可选） | sidecar → 总线 | 待推送摘要，由 HA/云端消费 |
| `business/cloud/#`（可选） | 云端 bridge ↔ 店 | 排班缓存刷新、报表回执 |

字段只增不改：正式 JSON 样例落在 `docs/contracts/`（新建 `business.access.grant.v1.json` 等时追加，不改旧 `smartcctv.*` 样义）。

---

## 四、核心数据流

### 链路 A：老师到场 → 开门（最重业务链）

1. 摄像头 → go2rtc(Frigate) → 检测 known person（如「张教练」）在 `front_desk` zone  
2. Frigate → MQTT `frigate/events`  
3. sidecar 订阅 → 查排班（云端 FastAPI 或本地缓存）→ 判定合法  
4. sidecar → MQTT `business/access/grant` `{door:front, ttl:60s, reason:coach_verified}`  
5. HA 自动化监听 grant → 发布 `home/front_door/command` `OPEN`  
6. ESPHome 收到 → 继电器脉冲 → 门磁回报 → `home/front_door/state`  
7. sidecar 记审计（谁、何时、为什么、门是否开）

### 链路 B：教室利用率（日常链）

1. `frigate/<classroom>/person` 等计数流 → sidecar 滑动窗口  
2. 每 N 分钟 → `business/analytics/<room>` `{avg, peak, ts}`  
3. HA MQTT 发现 → `sensor.*_utilization` 仪表盘  
4. 云端订阅/拉取 → 时序 → 周月报

### 链路 C：纠纷取证导出（低频高价值）

1. 侧边栏 iframe → Frigate Web → Export  
2. 片段落入 `/media/frigate/exports/`（sidecar `media:ro`）  
3. sidecar 扫描 → rclone 加密上传 → 清理本地  
4. 家长请求 → 云端生成带签名临时下载链

---

## 五、analytics-sidecar 内部结构

仓库落点（实施时新建，本次仅定目录契约）：建议 `SmartCenter/addons/analytics_sidecar/` 或独立 submodule；**不**放进 HA `custom_components`。

```text
analytics-sidecar/
├── config.yml              # Supervisor App 描述
├── Dockerfile
├── requirements.txt
├── app/
│   ├── main.py             # FastAPI + asyncio + MQTT
│   ├── config.py           # Supervisor 注入环境变量
│   ├── ingest/
│   │   ├── mqtt_sub.py     # frigate/#、home/#、business/#
│   │   └── frigate_api.py  # REST：/api/events、latest.jpg
│   ├── analyzers/
│   │   ├── occupancy.py
│   │   ├── presence.py
│   │   └── heatmap.py
│   ├── decide/
│   │   └── access.py       # → business/access/grant
│   ├── sinks/
│   │   └── mqtt_pub.py
│   ├── store/
│   │   ├── sqlite.py
│   │   └── retention.py    # 如 72h 滚动
│   ├── api/
│   │   ├── board.py
│   │   └── healthz.py
│   └── webui/
└── tests/
```

### `config.yml` 骨架

```yaml
name: Analytics Sidecar
version: "0.1.0"
slug: analytics_sidecar
description: 教室视频事件智能分析（滞留/到岗/热力/门禁决策）
arch: [amd64]
startup: services
services:
  - mqtt:need
build: false
image: local/analytics-sidecar
map:
  - media:ro
ports:
  8080/tcp: 8080
options:
  frigate_host: "ccab4aaf-frigate-fa"
  school_id: 1
  retention_hours: 72
  analytics_interval_min: 5
schema:
  frigate_host: str
  school_id: int
  retention_hours: int
  analytics_interval_min: int
```

**选型**：FastAPI（单循环 MQTT + REST + 定时）+ paho-mqtt + SQLite。零 HA Python API 依赖；迁独立 Docker 宿主只改地址。

---

## 六、实施顺序（四阶段）

纪律：阶段③先打通「事件流 → 指标 → 看板」最小管道，再加算法与开门决策。

| 阶段 | 内容 | 完成标准 |
|------|------|----------|
| **① 底座** | HAOS + Mosquitto + Frigate Full Access + Coral；摄像头经 go2rtc；HACS Frigate Integration；侧边栏 iframe→Frigate | 预览/录像/zone 事件上 `frigate/#` |
| **② 执行层** | ESPHome 门板 + 门磁；HA 保命自动化：手动/授权类 `command`；**不含**教练识别决策 | 无 sidecar 也能钥匙/店员路径开门 |
| **③ sidecar 管道** | 本地 App 骨架；订 `frigate/#`；写 SQLite；`business/analytics/#`；看板 iframe :8080 | 利用率指标进 HA sensor |
| **④ 智能与云** | presence/access 决策；云端排班 join；取证 rclone；废弃旧 CCTV HMAC / HTTP 门协议 | 链路 A/B/C 验收通过 |

---

## 七、故障域与备份

| 层 | 挂了会怎样 | 备份 |
|----|------------|------|
| **保命层**（ESPHome + HA 基础自动化 + 物理钥匙并联） | 店可降级营业 | HAOS Supervisor 快照；ESPHome 固件仓 |
| **感知层**（Frigate） | 无人脸自动放行；利用率停；预约/手动开门仍可走保命路径 | Frigate config + 录像盘；Coral 驱动 |
| **智能层**（sidecar） | 无自动 grant / 无经营指标；保命层不受影响 | sidecar 镜像 + SQLite 卷；可空跑 |
| **云端** | 新单/排班同步受影响；店内已缓存策略可短时继续 | VPS 备份；店不依赖云发脉冲 |

**容错本质**：智能层全挂 → 降级运行，不停摆。

Supervisor 备份范围：HA 配置、Mosquitto、Frigate、sidecar 选项与数据盘策略（录像保留天数与导出目录）。

---

## 八、五条架构铁律

1. **HA 零智能**：只做设备翻译与保命自动化；分析/决策不进 HA 进程。  
2. **Frigate 零业务**：只做检测/录像/事件；「谁能进、是否滞留」在 sidecar。  
3. **总线即宪法**：跨 App 事件与指令只走 MQTT；REST 仅查询。  
4. **摄像头单连接**：视频消费经 go2rtc；摄像头侧连接数 ≤2。  
5. **可迁移性**：sidecar 零 HA API 依赖；换宿主只改地址。

---

## 九、与旧形态对照（归档 SmartCCTV / 旧 lobn 门协议）

| 旧 | 新 |
|----|----|
| 自研 SmartCCTV FastAPI :8300 | Frigate Full Access + sidecar :8080 |
| HMAC A/C + `smartcctv.event.v1` HTTP | MQTT `frigate/#` + `business/#` |
| `door.command.v1` HTTP → 自研 ESP 固件 | `home/*/command` → ESPHome |
| `lobn_office` 内做人脸热路径开门决策 | sidecar 发 grant；HA 只翻译成 command |
| `cctv.lobn` | 取消；Frigate / sidecar 走 HAOS 内网名 |

旧契约样例保留在 [contracts/](contracts/)，标注历史，见 [接口契约.md](接口契约.md)。

---

## 十、一句话总结

完整程序架构：一台 HAOS，Supervisor 托管四个 App——HA（设备中枢+保命）、Mosquitto（唯一总线）、Frigate Full Access（视频中枢，go2rtc 独占摄像头）、analytics-sidecar（全项目唯一智能代码住处）；HACS Frigate 集成做实体翻译；MQTT 分 `frigate/#` / `home/#` / `business/#`；三条核心链（到场开门、利用率、取证）经总线串联；智能层挂掉时保命层仍转；五条铁律护栏长期演进。
