# ESP32-S3 门禁固件（历史 · HTTP）

> **遗留**：仅联调 / 单测参考。新店与生产请用  
> [../esphome/](../esphome/)（`./START.sh` → Device Builder 或 CLI）。  
> 总览：[../README.md](../README.md) · 架构：[docs/架构-HAOS四App.md](../../docs/架构-HAOS四App.md)。

旧链路：SmartCenter / HA `EspDoorAdapter` HTTP → 以太网 W5500 → ESP32-S3 → 继电器。

- 只执行总控 `door.command.v1`（Bearer token）。
- DHT11 / PIR / 按钮可缺省；PIR / 按钮只上报 `esp.sense.v1`，本地不开门。
- 联调说明与指示灯：[`DEBUG.md`](DEBUG.md)

### PIR（VCC / VOUT / GND）

| PIR | 接到 |
|-----|------|
| VCC | ESP **5V**（标称 3~12V） |
| GND | GND |
| VOUT | **GPIO6** |

### 烧录 / 冒烟

```bash
cp include/config.example.h include/config.h   # 改引脚、token、CENTER_HOST、静态 IP
./.venv/bin/pio run -t upload                  # 首次：python3 -m venv .venv && .venv/bin/pip install platformio
# 烧录后按一下 RESET（勿按住 BOOT）
ESP_IP=192.168.1.250 ./scripts/hw_smoke.sh
python3 -m unittest host_sim/test_door_logic.py
```

**不要**用 `firmware/esphome/START.sh` 或 Device Builder 打开本目录。
## HTTP（废弃中）

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/v1/health` | 门状态、器件在位 |
| POST | `/v1/door/command` | 需 `Authorization: Bearer <token>` |

`host_sim/door_logic.py` 镜像脉冲夹紧与忙时拒绝，供仓库单测。
