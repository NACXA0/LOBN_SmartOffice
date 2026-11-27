# 智慧办公室

**一句话架构**：一台 HAOS 跑四个 Supervisor App（HA + Mosquitto + Frigate Full Access + **SmartCenter Add-on**），MQTT 总线串联，HACS Frigate 集成做实体翻译，云端 FastAPI 做 M 端业务；摄像头只连 Frigate，门禁板走 ESPHome，刷脸底库与工作台在 Add-on。全文：[docs/架构-HAOS四App.md](docs/架构-HAOS四App.md)。

原则：云端管交易与采集中继、Add-on 管智能判定与人脸库治理、HA 管保命与设备、Frigate 管感知（关 Face Recognition）、继电器只听 ESPHome（经 `home/*/command`）。契约：[docs/接口契约.md](docs/接口契约.md)。

自研 SmartCCTV **已删除出主仓**（远程归档）——[决策](docs/决策-归档自研SmartCCTV.md) · [清单](docs/归档-SmartCCTV准备清单.md)。

店内平台源码已升到**本仓根**（`addon/` · `config/` · `firmware/`）。旧子模块目录 [`SmartCenter/`](SmartCenter/) **原样保留、待你手动归档删除**——[决策](docs/决策-归档SmartCenter子模块.md) · [清单](docs/归档-SmartCenter准备清单.md)。日常从仓库根启动，不要再 `cd SmartCenter`。

## 目录

| 路径 | 角色 |
|------|------|
| [addon/](addon/) | **SmartCenter Add-on**（人脸工作台 + 底库 + 门口比对 → `business/access/grant`） |
| [config/](config/) | HA 配置（packages、过渡期 `lobn_office`） |
| [firmware/](firmware/) | 硬件固件：`esphome/` 生产教室总控；`esp32s3_door/` HTTP 遗留 |
| [docs/](docs/) | 总线宪法、部署、验收 |
| [repository.yaml](repository.yaml) | HA 附加组件商店仓库入口 |
| [LOBN_FireClassroom](https://github.com/NACXA0/LOBN_FireClassroom) | 子模块：小程序 + 云端 FastAPI + 管理后台；`fireclassroom.aleedu.com` |
| [SmartCenter/](SmartCenter/) | **待归档**旧子模块副本（勿作日常入口） |

```bash
git submodule update --init --recursive   # 主要拉 FireClassroom；SmartCenter 子模块仍在直至你手动移除
```

## 店内部署（生产）

完整步骤（HA / Frigate / 硬件 / Add-on / 云端）：**[docs/部署体系.md](docs/部署体系.md)**。  
已有 HAOS？→ **[docs/对接已有HAOS.md](docs/对接已有HAOS.md)**。

在 **HAOS** 上按阶段安装：

1. Home Assistant Core + Mosquitto + Frigate Full Access（Coral）  
2. HACS **Frigate Integration**（可选 Advanced Camera Card）  
3. ESPHome 教室总控（门 / RFID）  
4. **SmartCenter Add-on**（Ingress 工作台：概览 / 采集 / 人脸库 / 审计 → `business/access/grant`）  

底座勾选：[docs/阶段1-HAOS底座验收.md](docs/阶段1-HAOS底座验收.md)。

## 开发入口（本机优先 · 热更新）

日常**不要**绑店内 HAOS。专文：[docs/开发工作流.md](docs/开发工作流.md)。

```bash
./START.sh repair --yes && ./START.sh addon-repair   # 首次
./START.sh all                                        # Vite :5173 + API reload :8080 + 本机 HA :8123
# 关终端 = 全停
```

| 改什么 | 看哪里 |
|--------|--------|
| 工作台 UI | http://127.0.0.1:5173/（HMR） |
| 人脸 API / 比对 | :8080 + `addon/app` 热重载 |
| HA packages | :8123 |
| 云端 / 小程序 | `./START.sh classroom` 或 `cd LOBN_FireClassroom && ./START.sh` |

发版前：`./START.sh addon-ui-build` · `./START.sh addon-test`。

```bash
./START.sh                # 菜单：平台 + 消防教室编排
./START.sh test-all --yes
```

验收：[docs/验收清单.md](docs/验收清单.md) · 密钥：[docs/部署与密钥.md](docs/部署与密钥.md) · **文档索引**：[docs/README.md](docs/README.md)
