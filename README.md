# 智慧办公室

职责：云端管交易、总控管放行、监控管感知、继电器只听总控。契约见 [docs/接口契约.md](docs/接口契约.md)。

**监控实现**：不再自研 NVR。店内用 **HAOS + [Frigate](https://github.com/blakeblackshear/frigate) 官方插件**；SmartCenter 是 HA 自定义集成（门禁、告警、与云端业务、统计与面板）。自研 [SmartCCTV](https://github.com/NACXA0/SmartCCTV) **准备归档**——理由见 [docs/决策-归档自研SmartCCTV.md](docs/决策-归档自研SmartCCTV.md)。

## 子仓库（git submodule）

克隆主仓后执行：`git submodule update --init --recursive`

| 目录 | 远程仓库 | 角色 |
|------|----------|------|
| [SmartCenter](https://github.com/NACXA0/SmartCenter) | `NACXA0/SmartCenter` | 中央总控：HAOS 上的 **custom_components/lobn_office** + 配置（不改 HA 主干，可 uv 升级） |
| [SmartCCTV](https://github.com/NACXA0/SmartCCTV) | `NACXA0/SmartCCTV` | **历史 / 待归档**。感知改由 Frigate 插件承担，勿再当生产监控迭代 |
| [LOBN_FireClassroom](https://github.com/NACXA0/LOBN_FireClassroom) | `NACXA0/LOBN_FireClassroom` | [miniprogram_wechat](LOBN_FireClassroom/miniprogram_wechat/) + [backend](LOBN_FireClassroom/backend/) + [frontend_admin](LOBN_FireClassroom/frontend_admin/)；公网 `fireclassroom.aleedu.com` |
| [SmartCenter/firmware/esp32s3_door](SmartCenter/firmware/esp32s3_door/) | （随 SmartCenter） | ESP32-S3 + W5500 门禁：只听总控 `door.command.v1`；可选 DHT11 / PIR / 按钮上报 |

## SmartCenter 与 HA 升级

不 fork 整仓改核心。业务在 `SmartCenter/config/custom_components/lobn_office/`，使用 HA 增量接口：Config Flow、Entity、HTTP View、DataUpdateCoordinator、Intent。升级主干只需改 `homeassistant==版本` 再 `uv sync`。钉选见 `SmartCenter/VERSION`（当前 2026.11.3，Python ≥3.14.2）。

## 环境

全中文 · 自有服务 uv + Python 3.14 · Ubuntu/Debian  
已有：云服务器、PVE、网络摄像机、ESP32ETH

## 快速入口

根目录编排本地全栈开发测试：

```bash
./START.sh                # 菜单：启动 / 状态 / 环境检测·修复·测试 / submodule（仍可能列出待归档的 SmartCCTV）
./START.sh test --yes     # SmartCenter + FireClassroom（及历史 SmartCCTV，若 submodule 仍在）
./START.sh repair --yes
```

单端：

```bash
cd SmartCenter && ./START.sh                # 启动→开发=前台 HA；导出 center.zip
cd LOBN_FireClassroom && ./START.sh         # 启动→开发=Vite+API；编译/导出生产包
# 监控：HAOS 安装 Frigate 插件，维护其 config.yml（不要再依赖 SmartCCTV/START.sh 做生产）
# 门禁固件：SmartCenter/firmware/esp32s3_door（config.example.h → config.h 后 pio upload）
```

小程序用微信开发者工具打开 `LOBN_FireClassroom/miniprogram_wechat/`。总控门禁适配器选 `esp`，填 ESP 根地址与 Bearer token。

验收：[docs/验收清单.md](docs/验收清单.md) · 密钥：[docs/部署与密钥.md](docs/部署与密钥.md) · 归档决策：[docs/决策-归档自研SmartCCTV.md](docs/决策-归档自研SmartCCTV.md)





