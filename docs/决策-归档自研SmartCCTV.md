# 决策：归档自研 SmartCCTV

> 状态：已裁定 · 主仓目录与 submodule 已删除 · 见 [归档-SmartCCTV准备清单.md](归档-SmartCCTV准备清单.md)  
> 日期：2026-11-25  
> 终态架构：[架构-HAOS四App.md](架构-HAOS四App.md) · 店内下一步：[阶段1-HAOS底座验收.md](阶段1-HAOS底座验收.md)

---

## 1. 结论

**停止维护并归档** [SmartCCTV](https://github.com/NACXA0/SmartCCTV)（自研 NVR / YOLO / 人脸管线 / 自研 Web / HMAC 事件口）。

店内终态：

| 层 | 承担 |
|----|------|
| HAOS Supervisor | 托管四个 App |
| Frigate Full Access | 视频中枢（拉流、检测、录像、人脸库、发 `frigate/#`） |
| Mosquitto | 唯一跨 App 总线 |
| analytics-sidecar | **唯一智能住处**（分析、到岗/开门决策发 `business/access/grant`） |
| HA 本体 + HACS Frigate 集成 | 设备翻译、保命自动化、iframe；**零智能** |
| 云端 FastAPI | M 端交易、排班、报表 |
| ESPHome | 门板执行与状态上 MQTT |

---

## 2. 为什么去掉自研 CCTV

1. **职责已被 Frigate 覆盖**：预览、录像、检测、zone、人脸库、UI、MQTT——自研是重复造轮。  
2. **与 HAOS 四 App 形态冲突**：再挂 `cctv.lobn:8300` 多一套进程、密钥 A/C、升级路径。  
3. **成本**：YOLO/InsightFace/自研前端与边界条件文档，仍不如 Frigate 社区覆盖。  
4. **业务增量不该进 NVR**：排班 join、利用率、开门决策属于 sidecar + 云端，不是监控发行版。

### 与「sidecar」一词的区分

| 已否决 | 现行 |
|--------|------|
| Frigate + **HMAC CCTV 兼容 sidecar**（假装还是 SmartCCTV HTTP） | **analytics-sidecar**（Supervisor 本地 App，MQTT 总线，零 HA API） |

前者延续技术债；后者是架构里的智能层，**不**复刻自研 CCTV。

---

## 3. 一句话

> 监控用 Frigate，智能用 analytics-sidecar，保命用 HA+ESPHome，交易用云端。SmartCCTV 归档即可。
