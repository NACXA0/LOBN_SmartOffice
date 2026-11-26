# 资产防盗（RFID）— SmartCenter 专属

> 状态：**现行边界**（2026-11-26）  
> 一句话：RFID 资产防盗整段留在 SmartCenter；与 LOBN_FireClassroom（预约 / 交易 / 小程序）**无耦合**。

## 归属

| 层 | 职责 | 不做什么 |
|----|------|----------|
| **ESPHome 教室总控** | 读通道标签、DHT11、门脉冲、警号 GPIO；断网按最后一份白名单本地比对 | 不编辑白名单、不存资产名称、不连云端 |
| **HA** | 唯一白名单编辑处；通知 / 消警 / 仪表盘；MQTT 保留消息下发名单 | 不写串口驱动；比对不进 `lobn_office` |
| **Mosquitto** | `home/<room>/rfid/#` 总线 | 无业务逻辑 |
| **LOBN_FireClassroom** | — | **不参与**：无台账、无告警回写、无小程序推送 |
| **analytics-sidecar** | （可选）只订阅事件做轨迹 | **不在报警关键路径**；挂了也要响 |

依据：[架构-HAOS四App.md](架构-HAOS四App.md) 铁律——HA 零智能禁止的是排班 / 滞留 / 经营报表；通道白名单报警与「布防后门磁断开就响」同类，属保命联锁。

## 默认现场选型（教室总控）

每间教室**只选一种**读头接口，不是三种齐焊：

| 项 | 默认 | 说明 |
|----|------|------|
| 读头接口 | **RS485**（UART + DE/RE） | UHF 资产通道机常见；厂商帧用 `external_components` 解析后只吐标签号 |
| 备选 | 韦根 / RS232 | 见 ESPHome 包内 example；韦根走独立中断/RMT 组件，勿在 YAML lambda 位翻转 |
| 警号 | **板载 GPIO** | 教室总控直接驱动；不另起独立警号控制器 |
| 白名单 | HA → MQTT retained `…/rfid/allowlist` | 板上缓存；Wi‑Fi/HA 短断仍按最后名单响 |

## 数据流

```text
通道读头 ──→ ESPHome 教室总控 ──┬── 本地比对 ──→ 警号 GPIO
                               └── MQTT home/<room>/rfid/event
HA 白名单编辑 ──retained──→ home/<room>/rfid/allowlist ──→ ESP 缓存
home/<room>/rfid/event ──→ HA 自动化（通知 / 消警）
```

主题与 JSON 样例：[接口契约.md](接口契约.md) §4.7、[contracts/](contracts/)。  
节点与配置落点：[SmartCenter/esphome/](../SmartCenter/esphome/)、[SmartCenter/config/packages/rfid_asset_guard.yaml](../SmartCenter/config/packages/rfid_asset_guard.yaml)。
