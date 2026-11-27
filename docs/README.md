# 文档索引 · 智慧办公室（店内平台）

> 仓库根：[../README.md](../README.md)  
> 一句话：**HAOS 四 App + MQTT；刷脸在 SmartCenter Add-on（本仓 `addon/`）**。  
> **边界**：本目录只写店内 HAOS / Add-on / 固件 / 总线。云端业务见 [LOBN_FireClassroom/docs](../LOBN_FireClassroom/docs/README.md)。

## 怎么读

| 你想… | 先看 |
|-------|------|
| 系统边界与铁律 | [架构-HAOS四App.md](架构-HAOS四App.md) |
| 店内从零装齐 | [部署体系.md](部署体系.md) · 摘要 [部署说明.md](部署说明.md) |
| 已有 HAOS 怎么接 | [对接已有HAOS.md](对接已有HAOS.md) |
| 本机日常开发（热更） | [开发工作流.md](开发工作流.md) |
| 人脸采集 / 库 / 开门 / 工作台 | [人脸-SmartCenter-Add-on.md](人脸-SmartCenter-Add-on.md) |
| 勾选是否可上线 | [验收清单.md](验收清单.md) |
| 云端 / 小程序 / 管理端 | [../LOBN_FireClassroom/docs/README.md](../LOBN_FireClassroom/docs/README.md) |

## 架构与契约

| 文档 | 内容 |
|------|------|
| [架构-HAOS四App.md](架构-HAOS四App.md) | 四 App、MQTT 主题、刷脸链路、故障域、铁律 |
| [接口契约.md](接口契约.md) | v2 总线契约；§9 历史 HTTP/HMAC |
| [contracts/](contracts/) | JSON 样例（含历史 `smartcctv.*`） |

## 部署 · 开发 · 验收

| 文档 | 内容 |
|------|------|
| [部署体系.md](部署体系.md) | HA / Mosquitto / Frigate / Add-on / 硬件 / 云端 / 备份 |
| [部署说明.md](部署说明.md) | 店内平台部署摘要（阶段顺序 + 目录对照） |
| [对接已有HAOS.md](对接已有HAOS.md) | 现网合并配置与终验；开发本机优先 |
| [开发工作流.md](开发工作流.md) | 一键 HMR、按改动选入口、本机 vs 生产 |
| [部署与密钥.md](部署与密钥.md) | 密钥、网络名、备份要点 |
| [阶段1-HAOS底座验收.md](阶段1-HAOS底座验收.md) | Mosquitto + Frigate + `frigate/events` |
| [验收清单.md](验收清单.md) | HAOS 四 App 总验收 |

## 人脸 · 设备

| 文档 | 内容 |
|------|------|
| [人脸-SmartCenter-Add-on.md](人脸-SmartCenter-Add-on.md) | 职责、状态机、工作台四页、容量、API |
| [资产防盗-RFID.md](资产防盗-RFID.md) | RFID 通道防盗（店内平台；与 FireClassroom 解耦） |
| [examples/frigate.config.phase1.example.yml](examples/frigate.config.phase1.example.yml) | 阶段① Frigate 骨架 |
| [examples/frigate.config.face-door.example.yml](examples/frigate.config.face-door.example.yml) | 刷脸阶段 Frigate（关人脸库） |

## 仓内代码入口

| 路径 | 说明 |
|------|------|
| [../addon/README.md](../addon/README.md) | Add-on 本地命令 |
| [../addon/web/README.md](../addon/web/README.md) | 工作台前端（Vite） |
| [../firmware/esphome/README.md](../firmware/esphome/README.md) | 教室总控固件 |
| [../START.sh](../START.sh) | 根入口（平台 + 消防教室编排） |

## 云端子仓（勿混写）

业务细节只在子仓文档：

| 入口 | 内容 |
|------|------|
| [../LOBN_FireClassroom/docs/README.md](../LOBN_FireClassroom/docs/README.md) | 云端文档索引 |
| [../LOBN_FireClassroom/README.md](../LOBN_FireClassroom/README.md) | 小程序 / API / 管理端总览 |

## 归档 · 参考

| 文档 | 内容 |
|------|------|
| [归档/决策-归档自研SmartCCTV.md](归档/决策-归档自研SmartCCTV.md) | 为何去掉自研 CCTV |
| [归档/归档-SmartCCTV准备清单.md](归档/归档-SmartCCTV准备清单.md) | CCTV 删除状态 |
| [归档/决策-归档SmartCenter子模块.md](归档/决策-归档SmartCenter子模块.md) | 为何升到父仓根 |
| [归档/归档-SmartCenter准备清单.md](归档/归档-SmartCenter准备清单.md) | SmartCenter 子模块归档状态 |
| [参考/华为HoloSens-SDC平台功能梳理.md](参考/华为HoloSens-SDC平台功能梳理.md) | 成熟 IPC 后台学习笔记 |
