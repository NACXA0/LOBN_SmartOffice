# 对接已有 HAOS（生产）与本机开发选择

内网已有 **HAOS + Frigate + Advanced Camera Card** 时：

| 用途 | 用哪套 | 原因 |
|------|--------|------|
| **日常开发** | **本机 Add-on + Vite + 本机 HA** | 热更新、不碰生产、无端口/ACL 折腾 |
| **生产上线 / 终验** | 店内 HAOS | 真 Frigate、真门、真 Ingress |

**结论：开发采用本机方案**（见 [开发工作流.md](开发工作流.md)）；店内机只接收合并后的配置与 Add-on 镜像，不做日常热重载目标。

---

## 开发（推荐本机 · 热更新）

```bash
# 在仓库根
./START.sh repair --yes && ./START.sh addon-repair   # 首次
./START.sh all                                        # Vite :5173 + API :8080 + HA :8123
```

| 改什么 | 起什么 |
|--------|--------|
| 工作台 UI / 会话 / 比对 / 人员 | `./START.sh all`（或 `addon` + `addon-ui`） |
| `face_grant_mqtt` / `door_mqtt` / `lobn_office` | 一键里的本机 HA，或单独 `./START.sh dev` |
| 两者联调 grant→自动化 | 本机可选 Mosquitto；**不必**指到店内 IP |

- 工作台开发入口：**http://127.0.0.1:5173/**（HMR）  
- 默认 `MQTT_HOST=off`；勿提交 `.env.lan`  
- 发版：`./START.sh addon-ui-build` → `addon/app/webui/`

不要用 `env.lan` 把开发机绑到店内 HAOS，除非做**有意的**终验。

---

## 生产：把成果装进已有 HAOS

不必重刷。合并配置 → 装 Add-on → 对齐 Frigate zone。

### 1. 核对现网

- [ ] Mosquitto + HA MQTT  
- [ ] Frigate 预览/录像；`frigate/events`  
- [ ] Face Recognition **关**  
- [ ] 记下 Frigate 主机名、门口相机/zone  

### 2. 同步 `config/`

| 路径 | 作用 |
|------|------|
| `packages/door_mqtt.yaml` | 店员开门 |
| `packages/face_grant_mqtt.yaml` | grant → 门脉冲 |
| `packages/rfid_asset_guard.yaml` | 可选 |
| `custom_components/lobn_office/` | 可选 |
| `configuration.yaml` → `packages:` | include 上述 |

检查配置 → 重启 HA。

### 3. 安装 Add-on

`addon/` → 本地附加组件（仓库根 [repository.yaml](../repository.yaml)）。  
Docker 多阶段会构建 `web/` → `app/webui`。  
选项改 Frigate URL、`door_cameras` / `door_zones`、云端 HMAC、容量相关项（见 [SmartOffice.md](SmartOffice.md)）。  
`run.sh` 从 Supervisor 注入 MQTT。  
侧边栏 Ingress → 工作台（总览 / 人员 / 审计）；**无自建登录**。

### 4. 终验（可短时用本机指到 LAN）

仅验收时：`cp addon/env.lan.example addon/.env.lan`，填店内 IP 后 `./START.sh addon`。  
验完改回 `MQTT_HOST=off` / 勿提交 `.env.lan`。

细节与端口：[部署体系.md](部署体系.md) · 样例 [examples/frigate.config.face-door.example.yml](examples/frigate.config.face-door.example.yml)

---

## 配置完整度（简）

骨架齐；现网要改的是 Frigate 名/zone、packages 是否已进 HAOS、生产 `embedder`。开发不依赖内网连通性。
