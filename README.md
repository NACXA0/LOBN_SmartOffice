# 智慧办公室

**一句话架构**：一台 HAOS 跑四个 Supervisor App（HA + Mosquitto + Frigate Full Access + analytics-sidecar），MQTT 总线串联，HACS Frigate 集成做实体翻译，云端 FastAPI 做 M 端业务；摄像头只连 Frigate，门禁板走 ESPHome。全文：[docs/架构-HAOS四App.md](docs/架构-HAOS四App.md)。

原则：云端管交易、sidecar 管智能判定、HA 管保命与设备、Frigate 管感知、继电器只听 ESPHome（经 `home/*/command`）。契约：[docs/接口契约.md](docs/接口契约.md)。

自研 SmartCCTV **已删除出主仓**（远程归档）——[决策](docs/决策-归档自研SmartCCTV.md) · [清单](docs/归档-SmartCCTV准备清单.md)。店内底座验收：[docs/阶段1-HAOS底座验收.md](docs/阶段1-HAOS底座验收.md)。

## 子仓库（git submodule）

```bash
git submodule update --init --recursive
```

| 目录 | 远程 | 角色 |
|------|------|------|
| [SmartCenter](https://github.com/NACXA0/SmartCenter) | `NACXA0/SmartCenter` | HAOS 配置 + ESPHome 教室总控（门/RFID/DHT）+（过渡期）`lobn_office`；保命自动化、iframe、addons/sidecar 脚手架 |
| [LOBN_FireClassroom](https://github.com/NACXA0/LOBN_FireClassroom) | `NACXA0/LOBN_FireClassroom` | 小程序 + 云端 FastAPI + 管理后台；`fireclassroom.aleedu.com` |
| [SmartCenter/firmware](SmartCenter/firmware/esp32s3_door/) | （随 SmartCenter） | 旧 HTTP 门固件；**迁移目标 ESPHome**（见架构文档） |

## 店内四 App（生产）

在 **HAOS** 上安装（阶段①起）：

1. Home Assistant Core  
2. Mosquitto  
3. Frigate Full Access（`config.yml` + Coral）  
4. analytics-sidecar（阶段③再装；智能唯一住处）  

外加 HACS **Frigate Integration**。步骤见 [docs/阶段1-HAOS底座验收.md](docs/阶段1-HAOS底座验收.md)。

## 开发入口

```bash
./START.sh                # 编排 SmartCenter + FireClassroom
./START.sh test --yes
./START.sh repair --yes
```

```bash
cd SmartCenter && ./START.sh           # 开发态 HA
cd LOBN_FireClassroom && ./START.sh    # 云端 + 管理端
# 生产监控/门禁：HAOS + Frigate + ESPHome
```

验收：[docs/验收清单.md](docs/验收清单.md) · 密钥：[docs/部署与密钥.md](docs/部署与密钥.md) · 文档索引：[docs/README.md](docs/README.md)
