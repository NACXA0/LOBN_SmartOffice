#pragma once
// 复制为 config.h 后填入真实值；config.h 勿提交。

#define LOBN_FW_VERSION "0.2.0"

// —— W5500 SPI ——
#define PIN_ETH_CS   14
#define PIN_ETH_RST  9
#define PIN_ETH_SCK  12
#define PIN_ETH_MISO 13
#define PIN_ETH_MOSI 11

// —— 继电器：高电平吸合 ——
#define PIN_RELAY    4
#define RELAY_ACTIVE_HIGH 1

// —— 传感器（可缺省；未接时 present=false，门服务照常）——
// DHT11：DATA→GPIO5，VCC 3.3/5V，GND，DATA 上拉 4.7k~10k（模块自带可省）
#define PIN_DHT11    5
// PIR（VCC / VOUT / GND）：VCC→5V（或 3.3V），GND→GND，VOUT→GPIO6
// 多数模块 5V 供电时 VOUT 仍约 3.3V，可直连 ESP32-S3；若确认 5V 电平须加分压
#define PIN_PIR      6
#define PIR_ACTIVE_HIGH 1
#define PIR_FORCE_PRESENT 0   // 接好 PIR 时改 1；未接保持 0
// 按钮：一端 GPIO7，一端 GND（内部上拉）
#define PIN_BUTTON   7
#define BUTTON_ACTIVE_LOW 1
#define BUTTON_FORCE_PRESENT 0

// —— 板载指示灯（ESP32-S3-DevKitC 多为 WS2812；新板 GPIO48，旧板 GPIO38）——
#define PIN_STATUS_LED 48
#define STATUS_LED_RGB 1      // 1=neopixelWrite；0=普通 GPIO 高低电平
#define STATUS_LED_ACTIVE_HIGH 1

// —— 网络：全 0 = DHCP；联调可写静态 ——
#define ETH_IP_0 192
#define ETH_IP_1 168
#define ETH_IP_2 1
#define ETH_IP_3 250
#define ETH_GW_0 192
#define ETH_GW_1 168
#define ETH_GW_2 1
#define ETH_GW_3 1
#define ETH_SN_0 255
#define ETH_SN_1 255
#define ETH_SN_2 255
#define ETH_SN_3 0
#define ETH_DNS_0 192
#define ETH_DNS_1 168
#define ETH_DNS_2 1
#define ETH_DNS_3 1

#define HTTP_PORT 8080
#define HTTP_MAX_REQ_BYTES 2048
#define HTTP_MAX_BODY_BYTES 1024

// 与 HA lobn_office EspDoorAdapter / esp_token 一致
#define LOBN_DOOR_TOKEN "change-me-esp-token"

// sense 上报：填跑 HA 的主机 IP（勿用未解析的 hostname，除非板上做 DNS）
#define CENTER_HOST "192.168.73.1"
#define CENTER_PORT 8123
#define CENTER_SENSE_PATH "/api/lobn_office/esp/sense"

#define TELEMETRY_INTERVAL_MS 30000
#define PIR_DEBOUNCE_MS 200
#define PIR_REPORT_COOLDOWN_MS 2000
#define BUTTON_DEBOUNCE_MS 50
#define BUTTON_PRESS_COOLDOWN_MS 3000
#define ETH_RECHECK_MS 5000
#define WDT_TIMEOUT_SEC 15
