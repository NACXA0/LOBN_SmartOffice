# 华为 HoloSens SDC 监控后台功能梳理

> 来源：内网设备 Web 管理台 `https://192.168.1.125`（浏览器实地抓取）  
> 设备：`D2150-10-I-P(3.6mm)` · 固件 `SDC 8.2.0.SPC139` · 登录用户 `admin`  
> 用途：对照学习成熟 IPC/SDC 后台能力；本仓库监控已改为 HAOS+Frigate，本篇主要反哺总控/运维体验设计（非对接说明书）

---

## 1. 平台概览

| 项 | 内容 |
|----|------|
| 产品线 | 华为 HoloSens / SDC（Smart Domain Camera）Web 配置台 |
| 前端形态 | 多页 SPA：一级模块整页跳转 `pages/{mod}/{mod}.html`，二/三级通过 `$('#section').load(...)` AJAX 装载 |
| 路由 | `g_router.routerTo` / `jumpTo`；会话 cookie：`first` / `second` / `third` |
| 路径规则 | 二级：`/pages/{first}/{second}/{second}.html`；三级：`/pages/{first}/{second}/{third}/{third}.html` |
| 菜单数据 | 运行时 `menuData` + `navigation_handler.js` 按能力位裁剪可见项 |
| 能力开关 | `/data/ConfigData.js`、`deviceAbility`、`setting_router.json` |
| 本地插件 | ActiveX/OCX 预览与绘制（`IVS_OCXPlayer` 等）；无插件时部分实时画面不可用 |
| UI 组件库 | `/libs/ucd/*`（Tabs、Dialog、Droplist、DatePicker、BaseTable、RangeSlider、guardPlan…） |

### 本机关键能力（ConfigData 摘录）

- 支持：SD 卡录像、定时抓拍、人脸检测、车道/车牌相关能力位、IPv6、ROI（最多 4）、隐私遮挡（最多 4）、移动侦测区（最多 4）、水印、预录  
- 不支持 / 关闭：球机、热成像、多算法模式（`DevTypeisMultAlg=false`）、语音对讲、麦克风、eMMC、Smart Wizard、GPS 等  

---

## 2. 一级导航总表

| ID | 中文名 | 角色 |
|----|--------|------|
| `main` | 预览配置 | 实时预览主界面 |
| `record` | 录像 | 回放 / 下载 / 计划 |
| `picture` | 图片 | 抓拍设置 / 下载 / FTP |
| `vindicate` | 维护 | 日志、信息、重置、升级、诊断 |
| `setting` | 高级配置 | 音视图、网络、智能、系统等（最深） |
| `quick_configuration` | 快速配置 | 向导式快速开局 |
| `people` | 人脸检测 | 人脸业务实时页 |
| `behavior_analysis` | 行为分析 | 行为分析实时页 |
| `service` | 服务 | 告警输入、通道、通用协议服务 |
| `tlv` | 智能元数据 | TLV/元数据与抓图浏览 |

页脚固定展示：型号、SDC 版本、华为版权信息。

---

## 3. 预览配置（`main`）

- 主播放器容器：`iLivePlayMainOCX` + 工具条 `mainToolBar`
- 侧栏：`main_aside`（通道/控制折叠）
- 典型能力（受能力位控制）：实时流、云台/电子云台、抓图、本地录像、对讲、3D 定位等  
- 学习点：**预览与配置分模块**；配置页也可内嵌隐藏 OCX 做 ROI/OSD/隐私框绘制

---

## 4. 录像（`record`）

### 4.1 录像回放 `playback`
- 通道选择、时间轴 `videoTimeLine`
- 起止时间查询；录像类型筛选：联动 / 手动 / 计划 / 缓存
- 播放 / 停止；SD 卡空间提示

### 4.2 录像下载 `download`
- 按时间段查询列表 + 分页
- 批量下载、停止下载、删除确认对话框

### 4.3 录像计划 `record_plan`
- 启用开关、计划表格（时段）、增删、分页
- 编辑对话框：开始/结束时间

**学习点**：计划与回放/下载分离；类型标签（计划/手动/联动）便于审计与 UI 筛选。

---

## 5. 图片（`picture`）

### 5.1 抓拍设置 `snap_config`
- SD 空间占用百分比、图片质量、分辨率模式
- 水印开关
- **定时抓拍**：启用、格式、间隔
- 重传（Retrans）、JPEG 元数据开关

### 5.2 图片下载 `pic_download`
- 按条件检索本地/卡内抓拍图并下载（ITS 设备有独立变体）

### 5.3 FTP `ftp`
- 单/多 FTP、协议类型、服务器 IP/端口、账号密码
- 可勾选上传：车牌图、人脸图、巡航图/视频图
- 自定义目录规则

**学习点**：抓拍质量与定时策略独立于「智能事件抓拍」；FTP 是边缘出图的经典通道。

---

## 6. 维护（`vindicate`）

| 子项 | 功能要点 |
|------|----------|
| `log` | 操作/告警/错误/硬件等日志；时间筛选；调试开关；一键收集与下载；远程日志收集（IP/端口/证书） |
| `device_message` | 设备型号、硬件版本、SN、BOM、软件/内核/UBOOT、MAC（含 eth1） |
| `mang` | 远程重启；恢复默认；完全恢复（需密码确认） |
| `upgrade` | SDC 软件升级；达芬奇/智能芯片固件；无线模组升级 |
| `app_defin` | 应用定义摄像机 |
| `tuning_result` | 调优结果诊断 |
| `fault_location` | 一键式故障定位 |
| `service_status_monitor` | 视频业务状态监控 |
| `lifecycle` | 生命周期 |

**学习点**：运维面与业务面分离；日志分级 + 一键打包是生产必备。

---

## 7. 高级配置（`setting`）— 核心

### 7.1 音视图 `streams`

| 子页 | 要点 |
|------|------|
| `video_stream` | 通道码流参数；H.265 提示对话框；子页 CGI：`cgi/video_stream_cgi.html` |
| `isp` | 图像参数；可切换 CGI/REST/热成像 ISP 子实现 |
| `isp_stream_package` | 图像/码流套餐 |
| `isp_package_plan` | 图像套餐计划（按时段切套餐） |
| `osd_new` | OSD 模板：增删复制、字体/字号/颜色/透明度、背景、星期/毫秒、插入内容、区域行距；预览叠加 |
| `osd_picture` | 图片叠加 |
| `privacy_mask` | 隐私遮挡启用、区域编号、添加遮挡/马赛克、列表分页、通道 |
| `whitebalance_area` | 白平衡区域选择 |
| `roi` | ROI 启用、多区域、码流类型、质量滑条 0–10 |

能力位还可出现：`audio_stream`、旧版 `osd`、`focus_area`、`bad_point_correction`（本机未必显示）。

### 7.2 网络 `network`

| 子页 | 要点 |
|------|------|
| `tcp_ip` | 多网卡、MAC、IPv4 获取方式/地址/掩码/网关/DNS；IPv6；MTU；QoS（媒体/信令 DSCP）；收包限速；组播 |
| `platform` | 平台对接（见下表协议矩阵） |
| `ip_filter` | IP 黑白名单过滤 |
| `port` | HTTP / HTTPS / RTSP 端口；端口映射（多 RTSP map） |
| `ddns` / `snmp` / `smtp` / `pppoe` | 对应传统网络服务 |
| `p8021x` | 802.1X |
| `network_acceleration` | 网络智能加速 |
| `ssh_sftp` | SSH / SFTP 开关 |
| `security` | HTTPS、兼容模式、安全套件 |
| （能力可选） | `route_config`、`wireless_dial`、`slave_devices`、`wifi_probe`、`wireless_module` |

#### 平台对接协议矩阵（`setting_router.json`）

- **二方协议**：ONVIF、GB/T 28181、GB/T 28181-2、GA/T 1400、GA/T 1400-2、REST、CMCC DM  
- **三方协议**：海康深圳、依图、ehualu、罗普特、ETC、天津交警、YGK 等  
- **鉴权管理**：SDK / REST / ONVIF Auth；JVS  

系统信息页同步展示各协议/SDK 在线状态（28181、GA/T 1400、多路 SDK）。

### 7.3 抓拍参数 `capture`
- 本机可见：`text_overlay` 文字叠加  
  - 字体/颜色/透明度/背景、叠加位置（图内上下 / 图外上下）  
  - 可选字段：时间、车牌、车型、车道、颜色、道路 ID 等（车牌/车型类随业务模式）  
  - 抓拍测试、实时 OSD 预览  
- 能力可选：闪光灯、图像合成、防伪校验等  

### 7.4 智能分析 `intelligent`

| 子页 | 要点 |
|------|------|
| `itgt_alarms` | 智能告警总入口（按通道分 Tab） |
| `itgt_features` | **普通智能**子 Tab： |
| └ 移动侦测 | 启用、画区增删、灵敏度、告警持续时间、布防时间计划 |
| └ 遮挡 / 场景变更 / 虚焦 / 起雾 | 同类「检测 + 灵敏度/计划」模式 |
| └ 聚集 / 停车 / 人群密度 / 排队 / 过线人数 | 人流与场景类算法（多算法模式才全开） |
| `face_detection` | 启用人脸；静态目标；规范化；抓拍模式（优先脸/定时/告警）；灵敏度（脸/人体）；关键点过滤；瞳距最小/最大；跟踪与人体联动；增强/抠图张数等 |
| `face_attribute` | 人脸/人体/骑手/车辆属性开关 |
| `heat_map` | 热度图 |
| `hot_region_analysis` | 热区分析 |

### 7.5 告警配置 `alarms`
- `cert_expire_alarm`：证书有效期检查周期、提前告警周期  

### 7.6 系统配置 `system`

| 子页 | 要点 |
|------|------|
| `system_info` | 温度、CPU、内存、收发速率；平台协议状态；界面语言 |
| `media_info` | 媒体流信息 |
| `time_setting` | 时区；手动 / NTP / GPS 校时；同步间隔；夏令时（按周或按日期） |
| `local_settings` | 渲染模式、编码/视频类型、协议、缓存帧；人脸/人体计数叠加；媒体加密；本地录像/抓拍路径与分段时长 |
| `storage_management` | SD 容量/格式化/刷新/加解锁；离线录像；本地录像/图片存储；码流选择；上传带宽限制；覆盖策略；预录；存储加密与生效时间 |
| `user_management` | 用户列表增删改；多点登录；连锁状态表；密码过期周期；锁定次数/时长 |
| `config_management` | 配置导入导出；设备证书 / SDK 证书与密钥上传恢复 |
| `visible_area` | 可视区域信息 |
| `password_manage` | Web 改密；协议侧鉴权密码；口令有效期；弱口令字典增删导入导出 |
| （能力可选） | PoE 管理、电源同步、违法字典等 |

---

## 8. 快速配置（`quick_configuration`）

- 向导页：`quick_config_title` / `quick_config_msg` + Tab + 预览 OCX  
- 目标：把网络、码流、基础图像等「开局必配」收成一步流  

**学习点**：完整高级配置保留深度，另给 **Quick Start** 降低首配成本。

---

## 9. 人脸检测 / 行为分析 / 智能元数据

| 模块 | 页面要点 |
|------|----------|
| `people` | 人脸业务实时窗（`peopelOcx`）；回调含上传人脸小图 `funOnOCXUploadFacePic` |
| `behavior_analysis` | 双路/多算法 OCX；可回调车牌/车辆类告警信息上传 |
| `tlv` | 主预览 + 搜索栏（名称检索）+ 启用开关；全景/目标图 TLV 上传回调；人脸/人体 OCX 区 |

**学习点**：智能结果不只「告警开关」，还有 **独立运营页**（检索元数据、看抠图）。

---

## 10. 服务（`service`）

### 10.1 告警服务 → 告警输入 `alarm/input`
- 告警源 Tab、应用列表左右切换  
- 基础：告警类型、持续时间  
- 联动动作容器 `actionContainer`  
- 布防计划：星期循环、时段增删  

### 10.2 通道服务 → 通道信息 `channel/channel_info`
- 通道表；属性列表对话框；功能列表对话框  

### 10.3 通用配置服务 `protocol`
- 协议应用容器 + 公共内容区 + 可选预览  

**学习点**：「输入 → 动作 → 时间计划」是告警联动的标准三段式。

---

## 11. 信息架构与交互模式（可复用）

```
顶栏：用户 / 品牌
左侧：一级模块（预览、录像、图片、维护、高级、快速、人脸、行为、服务、TLV）
中部：二级手风琴 / 三级横向 Tab
主区：表单 +（可选）右侧/内嵌视频绘制
底栏：型号 · 版本 · 版权
```

常见交互模式：

1. **通道下拉统一切换**（几乎所有媒体相关页）  
2. **启用开关 + 画区/列表 + 灵敏度 + 布防计划 + 保存**（智能/告警）  
3. **查询条件 → 表格/分页 → 下载或播放**（回放/下载/日志）  
4. **危险操作二次确认 + 当前用户密码**（恢复出厂、删用户、下证书）  
5. **能力位裁菜单**：同一套前端，枪机/球机/卡口/多算法显示不同子集  

---

## 12. 对本项目的启示

自研 SmartCCTV 已归档决策；预览/录像/检测/人脸库直接用 **Frigate**。本篇更多服务 **SmartCenter（告警、门禁、业务面板）** 与店员运维体验：

| HoloSens 能力 | 可借鉴方向 |
|---------------|------------|
| 告警输入三段式 | ESP/IO → 动作（通知/抑制）→ 时间计划（落在总控） |
| 用户 + 弱口令 + 证书到期 | HA/店员安全与运维提示 |
| 平台对接状态面板 | 「对接健康」：云端 HMAC、ESP、Frigate 实体 |
| 快速配置 | 店内开局：房间、门、云端 store_id、Frigate 相机 |
| 日志 / 一键收集 | 总控与 HA 诊断打包 |

不必照搬：OCX、GB28181/GA1400、自研 NVR——监控发行版用 Frigate，业务用总控与云端。

---

## 13. 抓取方法备忘

- 菜单树：页面全局 `menuData`  
- 可见性：`navigation_handler.js` 中各 `id` 的 handler  
- 子页字段：直接 `fetch` HTML，解析 `id=` / 表单结构（文案多在 `langMessage` 异步包，静态 HTML 常为空）  
- 路由装载：`g_router.routerToModule` → `$("#section").load(url)`  
- 设备能力：`/data/ConfigData.js`、`/data/setting_router.json`、`splitMenuData.js` 中的 Tab 定义  

---

*文档由浏览器工具对在线 SDC 管理台梳理生成，菜单以该机当前能力裁剪结果为准；同系列其它机型可能多出 PTZ、热成像、多算法等节点。*
