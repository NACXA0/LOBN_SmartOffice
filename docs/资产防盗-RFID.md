# 资产防盗（RFID）— 店内平台专属

> 状态：**现行边界**（办公室总管版）  
> 一句话：ESP 本地比对+警号永不依赖 Add-on；白名单由 SmartOffice **资产台账**生成并 retained 发布；事件进入总管同一条告警。与 LOBN_FireClassroom（预约 / 交易 / 小程序）**无耦合**。

## 归属

| 层 | 职责 | 不做什么 |
|----|------|----------|
| **ESPHome 教室总控** | 读通道标签、门脉冲、警号 GPIO；断网按最后一份白名单本地比对 | 不编辑白名单、不存资产名称、不连云端 |
| **SmartOffice** | 资产台账（标签号→名称/空间/经手人）；生成 allowlist 并 retained 发布；订 `rfid/event` 进告警（带画面与资产名） | 不驱动警号；不做采购/财务；空名单须显式指令才发布 |
| **HA** | 通知 / 消警 / 仪表盘展示；保命层不受 Add-on 影响 | 不再是白名单唯一编辑处；比对不进 `lobn_office` |
| **Mosquitto** | `home/<room>/rfid/#` 总线 | 无业务逻辑 |
| **LOBN_FireClassroom** | — | **不参与**：无台账、无告警回写、无小程序推送 |

依据：[架构-HAOS四App.md](架构-HAOS四App.md) · [SmartOffice.md](SmartOffice.md)——通道白名单报警与「布防后门磁断开就响」同类，属保命联锁；总管挂了铃仍要响。

## 默认现场选型（教室总控）

每间教室**只选一种**读头接口，不是三种齐焊：

| 项 | 默认 | 说明 |
|----|------|------|
| 读头接口 | **RS485**（UART + DE/RE） | UHF 资产通道机常见；厂商帧用 `external_components` 解析后只吐标签号 |
| 备选 | 韦根 / RS232 | 见 ESPHome 包内 example |
| 警号 | **板载 GPIO** | 教室总控直接驱动 |
| 白名单 | SmartOffice → MQTT retained `…/rfid/allowlist` | 板上缓存；`rev` 单调，回退可拒收 |

## 数据流

```text
通道读头 ──→ ESPHome 教室总控 ──┬── 本地比对 ──→ 警号 GPIO
                               └── MQTT home/<room>/rfid/event
SmartOffice 台账 ──retained──→ home/<room>/rfid/allowlist ──→ ESP 缓存
home/<room>/rfid/event ──→ SmartOffice 告警总线（event_id 去重）
                         └──→ HA 自动化（通知 / 消警）
```

主题与 JSON 样例：[接口契约.md](接口契约.md)、[contracts/](contracts/)。  
节点与配置落点：[firmware/esphome/](../firmware/esphome/)、[config/packages/rfid_asset_guard.yaml](../config/packages/rfid_asset_guard.yaml)。
