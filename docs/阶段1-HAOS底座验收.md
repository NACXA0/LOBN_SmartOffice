# 阶段①：HAOS 底座验收（Mosquitto + Frigate）

> 依据：[架构-HAOS四App.md](架构-HAOS四App.md) §六 · 全文部署：[部署体系.md](部署体系.md)。  
> **完成标准**：预览 / 录像可用，且 MQTT 上能看到 `frigate/events`（有人走过时）。  
> 本阶段**不**装 SmartCenter Add-on，**不**写开门决策，**不**恢复 SmartCCTV。Frigate **关闭** Face Recognition。

本机 Cursor 无法代替店内 N100 操作；请在 **HAOS 主机**上按下列清单勾选。

---

## 0. 硬件与前提

- [ ] N100（或同等）已刷 **HAOS**，能进 Supervisor
- [ ] USB **Coral TPU** 已插入（Frigate Full Access 检测加速）；无 Coral 时可先 CPU 跑通事件再换
- [ ] 局域网能访问摄像头 RTSP；路由器不强制多播怪异策略
- [ ] 数据盘规划好（录像保留如 30 天）

---

## 1. 安装 App

Supervisor → 应用商店：

| 顺序 | App | 说明 |
|------|-----|------|
| 1 | **Mosquitto broker** | 唯一总线；记下主机内地址（通常 `core-mosquitto`）与用户/密码 |
| 2 | **Frigate Full Access**（或官方 Frigate 带设备权限的变体） | 挂载 Coral、`/media`、config |
| 3 | （已有）Home Assistant Core | 本机自带 |

HACS：

- [ ] 安装 **Frigate Integration**（实体翻译，MQTT 发现）
- [ ] HA → 设置 → 设备与服务 → 添加 MQTT（连上一步 Mosquitto）
- [ ] 添加 Frigate 集成，指向 Frigate API（Supervisor 内网名，常见形如 `ccab4aaf-frigate-fa` 或文档当前 slug）

---

## 2. Frigate `config.yml` 最小骨架

可复制仓库样例 [examples/frigate.config.phase1.example.yml](examples/frigate.config.phase1.example.yml) 到 Frigate 的 `config.yml`，再改账号/IP/zone。

在 Frigate 配置中至少包含（按实机改 IP/账号）：

```yaml
mqtt:
  host: core-mosquitto
  user: "<mqtt_user>"
  password: "<mqtt_password>"

go2rtc:
  streams:
    front_desk:
      - rtsp://user:pass@192.168.x.x:554/Streaming/Channels/101

cameras:
  front_desk:
    ffmpeg:
      inputs:
        - path: rtsp://127.0.0.1:8554/front_desk
          roles: [detect, record]
    detect:
      enabled: true
    record:
      enabled: true
      retain:
        days: 30
    zones:
      front_desk_zone:
        coordinates: ...   # 在 Frigate UI 画区后粘贴

detectors:
  coral:
    type: edgetpu
    device: usb

objects:
  track:
    - person

# 身份在 SmartCenter Add-on；阶段①起就关掉 Frigate 人脸
face_recognition:
  enabled: false
```

纪律：

- 摄像头 **只**被 go2rtc/Frigate 拉流（连接数 ≤2）
- `config.yml` **不要**写「谁能进门」等业务规则；**不要**开 Face Recognition

可选：HACS **Advanced Camera Card** 做 Lovelace 预览（与 Frigate Integration 配合）。

---

## 3. HA 侧边栏（可选但推荐）

- [ ] 面板 → 添加网页 → iframe → Frigate UI（Supervisor 端口映射，常见 `:5000` 或 Ingress）
- [ ] 能打开实时预览与录像时间轴

---

## 4. MQTT 验收（必过）

在任意能连 Mosquitto 的机器上：

```bash
# 示例：mosquitto_sub（用户/主机按实机改）
mosquitto_sub -h <haos-ip> -u <user> -P '<pass>' -t 'frigate/#' -v
```

或在 HA → 开发者工具 → MQTT → 监听 `frigate/#`。

勾选：

- [ ] 订阅后安静等待，有人进入画面时出现 **`frigate/events`**（或相机相关 `frigate/<camera>/...`）
- [ ] JSON 中能看到 `label`（如 person）、相机名、可选 `zones`
- [ ] Frigate Integration 在 HA 中出现对应 camera / sensor 实体

失败时优先查：Frigate 日志里 MQTT connected、Mosquitto ACL、主题前缀是否为 `frigate`。

---

## 5. 阶段①完成定义（全部勾上才算过）

- [ ] Mosquitto 运行正常  
- [ ] Frigate 预览 + 录像可用  
- [ ] go2rtc 拉流，摄像头侧连接数 ≤2  
- [ ] HACS Frigate Integration 实体可见  
- [ ] Frigate Face Recognition **已关闭**  
- [ ] MQTT 上实测到 `frigate/events`（或等价 frigate 事件流）  

通过后 → 下一轮：**阶段② ESPHome 保命开门**，再 **阶段③ SmartCenter Add-on 刷脸**（见 [部署体系.md](部署体系.md)）。  
利用率/取证等扩展不阻塞刷脸上线。

---

## 6. 本仓对应位置

| 物 | 路径 |
|----|------|
| 部署体系 | [部署体系.md](部署体系.md) |
| 架构 | [架构-HAOS四App.md](架构-HAOS四App.md) |
| Frigate 样例 | [examples/frigate.config.phase1.example.yml](examples/frigate.config.phase1.example.yml) |
| 总验收 | [验收清单.md](验收清单.md) |
| SmartCenter 开发 HA | `../SmartCenter/`（不能替代店内 Frigate） |
