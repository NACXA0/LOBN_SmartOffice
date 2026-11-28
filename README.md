# 智慧办公室

**一句话架构**：一台 HAOS 跑四个 Supervisor App（HA + Mosquitto + Frigate Full Access + **SmartOffice**），MQTT 总线串联，HACS Frigate 集成做实体翻译，云端 FastAPI 做 M 端业务；摄像头只连 Frigate，门禁板走 ESPHome，人员底库与开门仲裁在 SmartOffice。全文：[docs/架构-HAOS四App.md](docs/架构-HAOS四App.md)。

原则：云端管交易与采集中继、**SmartOffice 是办公室总管**（人员/空间/资产/放行/告警/问询）、HA 管保命与设备、Frigate 管录像与 go2rtc（关 Face Recognition）、继电器只听 ESPHome。预约只是场景适配器之一。契约：[docs/接口契约.md](docs/接口契约.md) · 总管专文：[docs/SmartOffice.md](docs/SmartOffice.md)。

**通用 vs 场景 vs HA**（同一套资源 + 作用域视图，不复制模块）：[docs/架构-通用与场景.md](docs/架构-通用与场景.md)。里门可 `always_open`，预约关掉时人员/造访/告警仍运行。

店内平台在**本仓根**（`addon/` · `config/` · `firmware/`）。自研 SmartCCTV、旧 SmartCenter 子模块均已归档——[docs/归档/](docs/归档/README.md)。

## 目录

| 路径 | 角色 |
|------|------|
| [addon/](addon/) | **SmartOffice** 办公室总管（空间/人员/资产/仲裁/告警 → `business/access/grant`） |
| [config/](config/) | HA 配置（packages、过渡期 `lobn_office`） |
| [firmware/](firmware/) | 硬件固件：`esphome/` 生产教室总控；`esp32s3_door/` HTTP 遗留 |
| [docs/](docs/) | 店内平台文档（架构 / 部署 / SmartOffice / 验收） |
| [repository.yaml](repository.yaml) | HA 附加组件商店仓库入口 |
| [LOBN_FireClassroom](LOBN_FireClassroom/) | 子模块：小程序 + 云端 FastAPI + 管理后台；文档见其 `docs/` |

```bash
git submodule update --init --recursive   # LOBN_FireClassroom
```

## 店内部署（生产）

完整步骤：**[docs/部署体系.md](docs/部署体系.md)**。  
已有 HAOS？→ **[docs/对接已有HAOS.md](docs/对接已有HAOS.md)**。

1. Home Assistant Core + Mosquitto + Frigate Full Access（Coral）  
2. HACS **Frigate Integration**（可选 Advanced Camera Card）  
3. ESPHome 教室总控（门 / RFID）  
4. **SmartOffice**（Ingress：总览 / 空间 / 人员 / 记录）  

底座：[docs/阶段1-HAOS底座验收.md](docs/阶段1-HAOS底座验收.md)。

## 开发入口（本机优先 · 热更新）

专文：[docs/开发工作流.md](docs/开发工作流.md)。日常**不要**绑店内 HAOS。

```bash
./START.sh repair --yes && ./START.sh addon-repair   # 首次
./START.sh all                                        # Vite :5173 + API :8080 + 本机 HA :8123
# 关终端 = 全停
```

| 改什么 | 看哪里 |
|--------|--------|
| 工作台 UI | http://127.0.0.1:5173/ |
| 人员 API / 比对 / 仲裁 | :8080 + `addon/app` |
| HA packages | :8123 |
| 云端 / 小程序 | `./START.sh classroom` 或 `cd LOBN_FireClassroom && ./START.sh` |

发版前：`./START.sh addon-ui-build` · `./START.sh addon-test`。

```bash
./START.sh                # 菜单
./START.sh test-all --yes
```

验收：[docs/验收清单.md](docs/验收清单.md) · 密钥：[docs/部署与密钥.md](docs/部署与密钥.md) · **文档索引**：[docs/README.md](docs/README.md) · 云端：[LOBN_FireClassroom/docs/README.md](LOBN_FireClassroom/docs/README.md)
