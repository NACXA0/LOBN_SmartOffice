# 决策：归档自研 SmartCCTV

> 状态：已裁定 · 准备归档仓库 · 尚未删远程  
> 日期：2026-11-25  
> 替代方案：**HAOS + Frigate 官方插件**；感知与录像不再自研

---

## 1. 结论

**停止维护并准备归档** [SmartCCTV](https://github.com/NACXA0/SmartCCTV)（自研 NVR / YOLO / 人脸管线 / 自研 Web 面板）。

智慧办公室的监控能力改为：

| 层 | 承担 |
|----|------|
| **HAOS** | 店内总控运行时（Home Assistant OS） |
| **Frigate 官方插件** | 拉流、预览、录像回放、检测、区域、人脸库与识别、告警与 UI |
| **SmartCenter**（`custom_components/lobn_office` + HA 配置） | 门禁策略、与云端业务、告警通知编排、店员相关自定义面板/统计；**不重做 NVR** |

自研 CCTV 曾经承担的「录像 / 检测 / 比对 / 上报事实」职责，由 **Frigate 覆盖**；与开门、授权、云端交易相关的逻辑仍只在总控与云端。

---

## 2. 为什么去掉自研 CCTV

### 2.1 职责已被成熟开源覆盖

对照自研目标（≤10 路 RTSP、检测、人脸、区域规则、回放、告警）与 [Frigate](https://github.com/blakeblackshear/frigate)：

| 自研 SmartCCTV 目标 | Frigate（HA 插件） |
|---------------------|-------------------|
| RTSP 拉流 / 多路预览 | go2rtc + 官方 UI |
| 连续/事件录像与回放 | `record` / timeline |
| 人检测、区域、滞留类规则 | detect + zones + 官方规则 |
| 人脸库与识别 | 内置 Face Recognition（小/大模型） |
| 运维面板（登录、事件、健康） | Frigate UI + HA 集成 |
| MQTT / HA 事件 | 原生 MQTT 主题 + Frigate HA 集成 |

继续自研等于重复实现一套已有产品：拉流稳定性、录像索引、CPU/加速器适配、UI、升级与社区缺陷修复都要自己扛。

### 2.2 与总控形态冲突

目标形态是 **一台 HAOS**：Frigate 作插件，SmartCenter 作 HA 自定义集成。再挂一个独立 FastAPI「SmartCCTV」会多出：

- 第二套进程、端口（`cctv.lobn:8300`）、鉴权与升级路径  
- 自研事件总线 → HMAC → 总控，而 Frigate→HA 已有一流集成路径  
- 文档与验收里「监控宕机 / 监控开门」等表述，与「监控从不执行开门」叠床架屋  

归档后：**感知在 Frigate，放行只在总控，交易只在云端**，边界更短。

### 2.3 成本与风险

自研栈绑定 YOLO26、InsightFace/ONNX、自维护前端与 Docker 全栈（见 `SmartCCTV/docs/` 01–09）。模型许可、依赖轮、夜视降级、磁盘治理等已在文档里堆了大量边界条件，却仍达不到 Frigate 社区的覆盖面。

**增量业务**（预约授权、人脸与云端 user_id、门禁、业务统计）本就应落在 SmartCenter / 云端，而不是再造一个监控发行版。

### 2.4 曾考虑过、现已否决的折中

曾评估「官方 Frigate 容器 + 自研薄 sidecar（保留 HMAC enroll / passages / assist）」以兼容旧契约。  
**当前裁定：不采用。** 理由是 Frigate 已覆盖监控职责；契约侧应收敛到 **HA 内**（Frigate 事件 → `lobn_office`），而不是长期保留独立 CCTV 服务与密钥 A/C 双进程模型。Sidecar 只是把技术债换了个壳。

---

## 3. 目标架构（归档后）

```text
摄像头 ──RTSP──► Frigate（HAOS 插件）
                    │
                    ├─ UI / 录像 / 人脸库（店员运维）
                    └─ 事件（MQTT / HA 实体）──► lobn_office（SmartCenter）
                                                    │
                        ┌───────────────────────────┼───────────────────────────┐
                        ▼                           ▼                           ▼
                   门禁策略 / ESP              告警通知 / 自定义面板         云端业务（授权、统计…）
```

原则不变（见 [接口契约.md](接口契约.md)）：**云端管交易、总控管放行、监控管感知、继电器只听总控。**  
变化的是「监控」的实现从自研 SmartCCTV 换成 Frigate；感知进入总控的通道从「独立 HMAC 进程」改为 **HA 生态内集成**（具体接线在 SmartCenter 实施时落文档，不在本决策里扩写 sidecar）。

---

## 4. 对现有仓库与文档的影响

| 项 | 处理 |
|----|------|
| `SmartCCTV/` submodule | **准备归档**：远程仓库设为 Archived；主仓随后去掉 submodule 引用与根 `START.sh` 中的 cctv 编排 |
| `SmartCCTV/docs/*` | 保留作历史调研；[00-INDEX](../SmartCCTV/docs/00-INDEX.md) 标明「方案已废弃」 |
| 密钥 A / C、`cctv.lobn` | 部署文档改为「历史 / 过渡」；终态以 HA+Frigate+总控为准 |
| `smartcctv.event.v1` 与 enroll/assist/passages HTTP | 契约文档标注为 **自研 CCTV 时期接口**；总控改为消费 Frigate/HA 事件后，再修订契约版本（字段只增不改原则下可新开 schema，旧样例留档） |
| 验收清单 | 去掉「SmartCCTV 无法开门」等依赖自研进程的条目，改为 Frigate/总控表述 |

本决策**只要求更新说明文档**；删除 submodule、改 SmartCenter 接线、归档 GitHub 仓库可分步执行，不在本文一次做完。

---

## 5. 一句话

> 监控不要自研发行版：Frigate 已经是完整监控系统；我们只维护总控与云端业务。SmartCCTV 完成历史使命，归档即可。
