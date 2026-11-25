# 归档 SmartCCTV：状态清单

> 架构终态见 [架构-HAOS四App.md](架构-HAOS四App.md)。  
> 归档理由见 [决策-归档自研SmartCCTV.md](决策-归档自研SmartCCTV.md)。  
> 店内下一步：[阶段1-HAOS底座验收.md](阶段1-HAOS底座验收.md)。

## A. 已完成

- [x] 最终架构全文（四 App、MQTT、链路、sidecar、铁律）
- [x] 决策 / 契约 v2 / 部署密钥 / 验收对齐
- [x] 工作树删除 `SmartCCTV/` 目录
- [x] `.gitmodules` 去掉 SmartCCTV；gitlink 移除
- [x] 根 `START.sh` / `README.md` 不再编排 CCTV
- [x] Caddy `cctv.lobn` 注释掉

## B. 可选后续（非阻塞阶段①）

| # | 动作 | 说明 |
|---|------|------|
| 1 | GitHub `NACXA0/SmartCCTV` 保持 **Archived** | 只读历史 |
| 2 | 密钥库作废 A/C | 见 [部署与密钥.md](部署与密钥.md) |
| 3 | SmartCenter 停用旧 CCTV HMAC 入站 / HTTP 门适配器 | 跟阶段②③一起改 |
| 4 | `firmware/esp32s3_door` → ESPHome | 阶段② |
| 5 | `addons/analytics_sidecar/` 脚手架 | 阶段③（须先有 `frigate/events`） |

## C. 当前正确下一动作

**阶段①**：在店内 HAOS 主机按 [阶段1-HAOS底座验收.md](阶段1-HAOS底座验收.md) 装 Mosquitto + Frigate Full Access + HACS Frigate Integration，验收 MQTT 上可见 `frigate/events`。  
在此之前不写 sidecar、不做开门决策。
