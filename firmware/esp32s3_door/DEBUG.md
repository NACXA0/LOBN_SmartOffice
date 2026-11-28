# ESP32-S3 + W5500 联调备忘（遗留 HTTP 固件）

## PIR 接线（VCC / VOUT / GND）

| PIR | ESP32-S3 | 说明 |
|-----|----------|------|
| VCC | **5V**（模块标 3~12V；3.3V 也可试，灵敏度可能变差） | 与板共地 |
| GND | GND | 必须共地 |
| VOUT | **GPIO6**（`PIN_PIR`） | 有人→高电平（`PIR_ACTIVE_HIGH=1`） |

- 模块有人时 VOUT≈3.3V 可直连；若确认输出 5V，加电阻分压。
- `config.h` 里 `PIR_FORCE_PRESENT 1`：已接线时强制 present，避免悬空误判。
- **PIR 只上报 `esp.sense.v1`，本地绝不因 PIR 开门。**

## 板载灯

- DevKitC 地址灯：`PIN_STATUS_LED` 默认 **GPIO48**（旧板改 38）。
- 颜色：黄=启动 / 红=网断 / 绿=就绪 / 蓝=开门脉冲 / 橙=PIR。

## W5500 RJ45 不亮 / `eth chip=NoHardware` / `VERSIONR=0x00`

软件已避开 Ethernet 库无参 `SPI.begin()` 清引脚的问题。若串口仍是：

```text
eth spi VERSIONR=0x00 (expect 0x04)
eth chip=NoHardware
```

则是 **模块没在 SPI 上应答**（不是网线问题优先）：

1. 用万用表量模块 **VCC**：常见要 **5V** 入（板载 LDO→3.3V）；只接 3.3V 可能整板没电，RJ45 灯也不亮。  
2. **GND 与 ESP 共地**。  
3. **RST** 上电后应为高电平（~3.3V）；若一直为 0，芯片永复位。  
4. 杜邦线短接确认：MOSI↔GPIO11，MISO↔GPIO13，SCK↔GPIO12，CS↔GPIO14。  
5. 换网线/换口不能让 `VERSIONR` 从 0x00 变 0x04；先让芯片应答，Link 灯才会有意义。

## 烧录后卡在 `waiting for download`

1. 不要按住 BOOT；按一下 **RESET**。
2. 或拔掉 USB，只留网线+供电后再上电。
3. 冒烟：`ESP_IP=192.168.1.250 ./scripts/hw_smoke.sh`

## 与 HA / SmartOffice / Frigate

**生产开门链（MQTT，勿用本固件新店）：**  
Camera → Frigate/`frigate/events` → SmartOffice 比对 → `business/access/grant` → HA `face_grant_mqtt` → `home/<node>/door/command` → **ESPHome**。

**本板（W5500 遗留）HA 选项：**

| 选项 | 值 |
|------|-----|
| `door_adapter` | `esp`（默认 `mqtt` 打不到本板） |
| `esp_base_url` | `http://192.168.1.250:8080` |
| `esp_token` | 与 `config.h` 里 `LOBN_DOOR_TOKEN` 一致 |

| 步骤 | 期望 |
|------|------|
| `GET http://ESP:8080/v1/health` | `ok/dht/pir/eth` |
| ESP → `POST HA/api/lobn_office/esp/sense` | Bearer=`esp_token`；`ts` 为 Unix（板上 NTP） |
| Frigate 出 `person` + zone | MQTT `frigate/#` |
| SmartOffice 仲裁 | `business/access/grant` |
| 遗留门脉冲 | `EspDoorAdapter` → `POST /v1/door/command` |

快检：`./scripts/chain_status.sh` · 冒烟：`./scripts/hw_smoke.sh`  
验收：`docs/验收清单.md` · `docs/阶段1-HAOS底座验收.md`
