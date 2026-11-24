# 智慧办公室

职责：云端管交易、总控管放行、监控管感知、继电器只听总控。契约见 [docs/接口契约.md](docs/接口契约.md)。

## 子项目

| 目录 | 角色 | 状态 |
|------|------|------|
| [SmartCenter](SmartCenter/) | 中央总控：Home Assistant + **custom_components/lobn_office**（不改 HA 主干，可 uv 升级） | 配置流 / 单测通过 |
| [SmartCCTV](SmartCCTV/) | 内网监控：只上报事件，**本地不执行开门** | adapter=`center_only` |
| [LOBN_FireClassroom](LOBN_FireClassroom/) | 小程序 + [server](LOBN_FireClassroom/server/) + [admin](LOBN_FireClassroom/admin/) | 预约/营销/授权发件箱；公网 `fireclassroom.aleedu.com` |

## SmartCenter 与 HA 升级

不 fork 整仓改核心。业务在 `SmartCenter/config/custom_components/lobn_office/`，使用 HA 增量接口：Config Flow、Entity、HTTP View、DataUpdateCoordinator、Intent。升级主干只需改 `homeassistant==版本` 再 `uv sync`。钉选见 `SmartCenter/VERSION`（当前 2026.11.3，Python ≥3.14.2）。

## 环境

全中文 · 自有服务 uv + Python 3.14 · Ubuntu/Debian  
已有：云服务器、PVE、网络摄像机、ESP32ETH

## 快速入口

三端统一 `./START.sh`（启动 / 运维 / 环境检测，选中后清屏刷新）：

```bash
cd SmartCenter && ./START.sh                # HA 总控；repair --yes 后 start
cd LOBN_FireClassroom && ./START.sh         # 转调 server/；小程序用微信开发者工具开本目录
cd SmartCCTV && ./START.sh                  # 终端或 Docker；配置 center.events_url 后上报总控
```

验收：[docs/验收清单.md](docs/验收清单.md) · 密钥：[docs/部署与密钥.md](docs/部署与密钥.md)




https://github.com/NACXA0/SmartCenter

一次开门都进入了那些人：门开启状态持续采集经过门的人脸
门一直开怎么办？

