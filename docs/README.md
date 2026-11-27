# 文档索引

> 仓库根：[../README.md](../README.md) · 现行架构一句话：**HAOS 四 App + MQTT；刷脸在 SmartCenter Add-on**。

## 怎么读

| 你想… | 先看 |
|-------|------|
| 弄清系统边界与铁律 | [架构-HAOS四App.md](架构-HAOS四App.md) |
| 店内从零装齐 / 上线清单 | [部署体系.md](部署体系.md) |
| 已有 HAOS+Frigate 怎么接 | [对接已有HAOS.md](对接已有HAOS.md) |
| **本机日常开发（热更）** | [开发工作流.md](开发工作流.md) |
| 人脸采集 / 库 / 开门 / 工作台 | [人脸-SmartCenter-Add-on.md](人脸-SmartCenter-Add-on.md) |
| 勾选是否可上线 | [验收清单.md](验收清单.md) |

## 架构与契约

| 文档 | 内容 |
|------|------|
| [架构-HAOS四App.md](架构-HAOS四App.md) | 四 App、MQTT 主题、刷脸链路、故障域、铁律 |
| [接口契约.md](接口契约.md) | v2 总线契约；§9 历史 HTTP/HMAC |
| [contracts/](contracts/) | JSON 样例（含历史 `smartcctv.*`） |
| [决策-归档自研SmartCCTV.md](决策-归档自研SmartCCTV.md) | 为何去掉自研 CCTV |
| [归档-SmartCCTV准备清单.md](归档-SmartCCTV准备清单.md) | 删除状态 |
| [决策-归档SmartCenter子模块.md](决策-归档SmartCenter子模块.md) | 为何把店内平台升到父仓根 |
| [归档-SmartCenter准备清单.md](归档-SmartCenter准备清单.md) | 子模块手动归档步骤 |

## 部署与运维

| 文档 | 内容 |
|------|------|
| [部署体系.md](部署体系.md) | HA / Mosquitto / Frigate / Add-on / 硬件 / 云端 / 备份 |
| [对接已有HAOS.md](对接已有HAOS.md) | 现网合并配置与终验；开发本机优先 |
| [开发工作流.md](开发工作流.md) | 一键 HMR、按改动选入口、本机 vs 生产差异 |
| [部署与密钥.md](部署与密钥.md) | 密钥、网络名、备份要点 |
| [阶段1-HAOS底座验收.md](阶段1-HAOS底座验收.md) | Mosquitto + Frigate + `frigate/events` |
| [验收清单.md](验收清单.md) | HAOS 四 App 总验收（含工作台 / 容量） |

## 人脸与设备

| 文档 | 内容 |
|------|------|
| [人脸-SmartCenter-Add-on.md](人脸-SmartCenter-Add-on.md) | 职责、状态机、工作台四页、容量、API、开发 |
| [资产防盗-RFID.md](资产防盗-RFID.md) | RFID 通道防盗（仅 SmartCenter；与 FireClassroom 解耦） |
| [examples/frigate.config.phase1.example.yml](examples/frigate.config.phase1.example.yml) | 阶段① Frigate 骨架 |
| [examples/frigate.config.face-door.example.yml](examples/frigate.config.face-door.example.yml) | 刷脸阶段 Frigate（关人脸库） |

## 产品与其它

| 文档 | 内容 |
|------|------|
| [小程序设计规范.md](小程序设计规范.md) | 小程序 UI 约定（通用） |
| [管理端页面设计规范.md](管理端页面设计规范.md) | FireClassroom `/admin` 壳层与信息架构 |
| [华为HoloSens-SDC平台功能梳理.md](华为HoloSens-SDC平台功能梳理.md) | 成熟 IPC 后台学习笔记 |

## 云端 FireClassroom（子仓文档）

业务细节在子仓，勿与店内 HAOS 文档混写：

| 文档 | 内容 |
|------|------|
| [../LOBN_FireClassroom/docs/README.md](../LOBN_FireClassroom/docs/README.md) | **云端文档索引** |
| [../LOBN_FireClassroom/docs/角色与控制台.md](../LOBN_FireClassroom/docs/角色与控制台.md) | 平台端 / 门店端、管理员与店长运维 |
| [../LOBN_FireClassroom/docs/目录与启动.md](../LOBN_FireClassroom/docs/目录与启动.md) | START.sh、目录同构 |
| [../LOBN_FireClassroom/docs/管理端.md](../LOBN_FireClassroom/docs/管理端.md) | 导航与页面 |
| [../LOBN_FireClassroom/docs/配置说明.md](../LOBN_FireClassroom/docs/配置说明.md) | config.yaml / 管理端开关 |
| [../LOBN_FireClassroom/docs/API概览.md](../LOBN_FireClassroom/docs/API概览.md) | 接口分组与鉴权 |
| [../LOBN_FireClassroom/docs/payment-runbook.md](../LOBN_FireClassroom/docs/payment-runbook.md) | 微信支付 |

## 仓内补充入口

| 路径 | 说明 |
|------|------|
| [部署说明.md](部署说明.md) | 店内平台部署摘要（原 SmartCenter 侧） |
| [../addon/README.md](../addon/README.md) | Add-on 本地命令 |
| [../addon/web/README.md](../addon/web/README.md) | 工作台前端（Vite） |
| [../firmware/esphome/README.md](../firmware/esphome/README.md) | 教室总控固件 |
| [../LOBN_FireClassroom/README.md](../LOBN_FireClassroom/README.md) | 云端 / 小程序 / 管理端总览 |
| [归档-SmartCenter准备清单.md](归档-SmartCenter准备清单.md) | 旧子模块手动归档步骤（未勾选项由你执行） |
