/**
 * LOBN 门禁：ESP32-S3 + W5500。
 * 只执行总控 door.command.v1 脉冲；DHT11 / PIR / 按钮可缺省，绝不自行开门。
 */
#include <Arduino.h>
#include <SPI.h>
#include <Ethernet.h>
#include <EthernetUdp.h>
#include <ArduinoJson.h>
#include <DHT.h>
#include <esp_task_wdt.h>
#include <esp_mac.h>
#include <sys/time.h>
#include <time.h>

#include "config.h"

#ifndef LOBN_FW_VERSION
#define LOBN_FW_VERSION "0.2.0"
#endif

#if STATUS_LED_RGB
#include <esp32-hal-rgb-led.h>
#endif

// ESP32 Arduino Core 的 Server::begin(uint16_t) 为纯虚；官方 Ethernet 库未实现。
class LobnEthernetServer : public EthernetServer {
 public:
  explicit LobnEthernetServer(uint16_t port) : EthernetServer(port) {}
  void begin(uint16_t port = 0) override {
    (void)port;
    EthernetServer::begin();
  }
};

enum class LedMode : uint8_t {
  Boot = 0,
  EthDown,
  Ready,
  Pulse,
  Pir,
  Error,
};

static byte mac[6];
static LobnEthernetServer server(HTTP_PORT);
static DHT dht(PIN_DHT11, DHT11);
static EthernetUDP ntp_udp;

static bool dht_present = false;
static bool pir_present = false;
static bool button_present = false;
static bool eth_up = false;
static bool time_synced = false;

static bool pulsing = false;
static char active_command_id[48] = {0};
static unsigned long pulse_end_ms = 0;

static int last_pir = LOW;
static unsigned long pir_change_ms = 0;
static bool pir_stable_high = false;
static unsigned long last_pir_report_ms = 0;

static int last_btn = HIGH;
static unsigned long btn_change_ms = 0;
static bool btn_down = false;
static unsigned long last_press_report_ms = 0;

static unsigned long last_telemetry_ms = 0;
static unsigned long last_eth_check_ms = 0;
static unsigned long last_ntp_ms = 0;
static LedMode led_mode = LedMode::Boot;
static unsigned long led_override_until = 0;

static void status_led_set(uint8_t r, uint8_t g, uint8_t b) {
#if STATUS_LED_RGB
  neopixelWrite(PIN_STATUS_LED, r, g, b);
#else
  bool on = (r | g | b) != 0;
  bool level = STATUS_LED_ACTIVE_HIGH ? on : !on;
  digitalWrite(PIN_STATUS_LED, level ? HIGH : LOW);
#endif
}

static void status_led_apply(LedMode mode) {
  led_mode = mode;
  switch (mode) {
    case LedMode::Boot: status_led_set(16, 16, 0); break;      // 黄
    case LedMode::EthDown: status_led_set(32, 0, 0); break;    // 红
    case LedMode::Ready: status_led_set(0, 24, 0); break;      // 绿
    case LedMode::Pulse: status_led_set(0, 0, 40); break;      // 蓝
    case LedMode::Pir: status_led_set(40, 12, 0); break;       // 橙
    case LedMode::Error: status_led_set(40, 0, 20); break;     // 品红
  }
}

static void status_led_flash(LedMode mode, unsigned long ms) {
  status_led_apply(mode);
  led_override_until = millis() + ms;
}

static void status_led_tick() {
  if (led_override_until != 0) {
    if ((long)(millis() - led_override_until) < 0) return;
    led_override_until = 0;
  }
  if (pulsing) {
    status_led_apply(LedMode::Pulse);
  } else if (!eth_up) {
    status_led_apply(LedMode::EthDown);
  } else {
    status_led_apply(LedMode::Ready);
  }
}

static void relay_set(bool on) {
  bool level = RELAY_ACTIVE_HIGH ? on : !on;
  digitalWrite(PIN_RELAY, level ? HIGH : LOW);
}

static void relay_release() {
  relay_set(false);
  pulsing = false;
  active_command_id[0] = '\0';
  pulse_end_ms = 0;
}

static float clamp_seconds(float s) {
  if (s < 0.2f) return 0.2f;
  if (s > 15.0f) return 15.0f;
  return s;
}

static bool const_time_eq(const char *a, const char *b, size_t n) {
  uint8_t diff = 0;
  for (size_t i = 0; i < n; i++) {
    diff |= (uint8_t)a[i] ^ (uint8_t)b[i];
  }
  return diff == 0;
}

static bool auth_ok(const String &req) {
  const char *prefix = "Authorization:";
  int idx = req.indexOf(prefix);
  if (idx < 0) return false;
  int line_end = req.indexOf("\r\n", idx);
  String line = req.substring(idx, line_end >= 0 ? line_end : req.length());
  line.trim();
  // "Authorization: Bearer <token>"
  const String expect = String("Authorization: Bearer ") + LOBN_DOOR_TOKEN;
  if (line.length() != expect.length()) return false;
  return const_time_eq(line.c_str(), expect.c_str(), expect.length());
}

static void send_json(EthernetClient &client, int code, const String &body) {
  client.print("HTTP/1.1 ");
  client.print(code);
  if (code == 200) client.print(" OK");
  else if (code == 401) client.print(" Unauthorized");
  else if (code == 409) client.print(" Conflict");
  else client.print(" Error");
  client.println();
  client.println("Content-Type: application/json");
  client.println("Connection: close");
  client.print("Content-Length: ");
  client.println(body.length());
  client.println();
  client.print(body);
}

static void uuid_like(char *buf, size_t n) {
  snprintf(buf, n, "%08lx-%04lx-%04lx-%04lx-%08lx%04lx",
           (unsigned long)esp_random(),
           (unsigned long)(esp_random() & 0xffff),
           (unsigned long)(esp_random() & 0xffff),
           (unsigned long)(esp_random() & 0xffff),
           (unsigned long)esp_random(),
           (unsigned long)(esp_random() & 0xffff));
}

static bool ntp_sync_once() {
  // Simple NTP over UDP (pool.ntp.org or gateway DNS may fail offline; use public IP-ish via DNS)
  const char *hosts[] = {"ntp.aliyun.com", "cn.pool.ntp.org", "time.nist.gov"};
  byte pkt[48] = {0};
  pkt[0] = 0x1B;
  for (const char *host : hosts) {
    ntp_udp.begin(2390);
    if (!ntp_udp.beginPacket(host, 123)) {
      ntp_udp.stop();
      continue;
    }
    ntp_udp.write(pkt, 48);
    ntp_udp.endPacket();
    unsigned long start = millis();
    while (millis() - start < 1200) {
      if (ntp_udp.parsePacket() >= 48) {
        ntp_udp.read(pkt, 48);
        ntp_udp.stop();
        uint32_t secs = ((uint32_t)pkt[40] << 24) | ((uint32_t)pkt[41] << 16) |
                        ((uint32_t)pkt[42] << 8) | (uint32_t)pkt[43];
        // NTP epoch → Unix
        time_t unix_ts = (time_t)(secs - 2208988800UL);
        timeval tv = {.tv_sec = unix_ts, .tv_usec = 0};
        settimeofday(&tv, nullptr);
        time_synced = true;
        Serial.printf("ntp ok ts=%lu via %s\n", (unsigned long)unix_ts, host);
        return true;
      }
      delay(10);
      esp_task_wdt_reset();
    }
    ntp_udp.stop();
  }
  Serial.println("ntp fail");
  return false;
}

static double wall_ts() {
  time_t now = time(nullptr);
  if (time_synced && now > 1700000000) return (double)now;
  // 无 NTP 时仍上报，由总控决定是否 skew_drop；避免 millis 伪时间
  return (double)now;
}

static bool post_sense(const char *json, size_t len) {
  EthernetClient c;
  c.setTimeout(800);
  if (!c.connect(CENTER_HOST, CENTER_PORT)) return false;
  c.print("POST ");
  c.print(CENTER_SENSE_PATH);
  c.println(" HTTP/1.1");
  c.print("Host: ");
  c.println(CENTER_HOST);
  c.print("Authorization: Bearer ");
  c.println(LOBN_DOOR_TOKEN);
  c.println("Content-Type: application/json");
  c.print("Content-Length: ");
  c.println((int)len);
  c.println("Connection: close");
  c.println();
  c.write((const uint8_t *)json, len);

  unsigned long start = millis();
  bool ok = false;
  while (c.connected() && millis() - start < 1200) {
    while (c.available()) {
      String line = c.readStringUntil('\n');
      if (line.startsWith("HTTP/1.")) {
        int code = line.substring(9, 12).toInt();
        ok = (code >= 200 && code < 300);
      }
    }
    delay(1);
  }
  c.stop();
  return ok;
}

static void report_sense(const char *kind, const char *edge, float temp, float hum, bool has_th) {
  JsonDocument doc;
  char eid[40];
  uuid_like(eid, sizeof(eid));
  doc["schema"] = "esp.sense.v1";
  doc["event_id"] = eid;
  doc["kind"] = kind;
  if (edge && edge[0]) doc["edge"] = edge;
  doc["ts"] = wall_ts();
  doc["device"]["dht"] = dht_present;
  doc["device"]["pir"] = pir_present;
  doc["device"]["button"] = button_present;
  if (has_th) {
    doc["temperature_c"] = temp;
    doc["humidity_pct"] = hum;
  }
  char out[384];
  size_t n = serializeJson(doc, out, sizeof(out));
  if (n == 0 || n >= sizeof(out)) return;
  for (int i = 0; i < 2; i++) {
    if (post_sense(out, n)) break;
    delay(30);
    esp_task_wdt_reset();
  }
}

static void handle_health(EthernetClient &client) {
  JsonDocument doc;
  doc["ok"] = true;
  doc["version"] = LOBN_FW_VERSION;
  doc["door"] = pulsing ? "pulsing" : "locked";
  doc["command_id"] = active_command_id;
  doc["uptime_ms"] = millis();
  doc["free_heap"] = ESP.getFreeHeap();
  doc["eth"]["link"] = eth_up;
  doc["eth"]["ip"] = Ethernet.localIP().toString();
  doc["time_synced"] = time_synced;
  doc["ts"] = wall_ts();
  doc["device"]["dht"] = dht_present;
  doc["device"]["pir"] = pir_present;
  doc["device"]["button"] = button_present;
  doc["pir_state"] = pir_stable_high ? "high" : "low";
  String out;
  serializeJson(doc, out);
  send_json(client, 200, out);
}

static void handle_door_command(EthernetClient &client, const String &body) {
  JsonDocument doc;
  if (deserializeJson(doc, body)) {
    send_json(client, 400, "{\"ok\":false,\"error\":\"invalid_json\"}");
    return;
  }
  const char *schema = doc["schema"] | "";
  const char *action = doc["action"] | "open";
  const char *cid = doc["command_id"] | "";
  float seconds = doc["seconds"] | 5.0f;

  if (strcmp(schema, "door.command.v1") != 0 || !cid[0] || strlen(cid) >= sizeof(active_command_id)) {
    send_json(client, 400, "{\"ok\":false,\"error\":\"bad_command\"}");
    return;
  }

  if (strcmp(action, "close") == 0) {
    relay_release();
    JsonDocument resp;
    resp["result"] = "released";
    resp["command_id"] = cid;
    String out;
    serializeJson(resp, out);
    send_json(client, 200, out);
    return;
  }

  if (strcmp(action, "open") != 0) {
    send_json(client, 400, "{\"ok\":false,\"error\":\"unknown_action\"}");
    return;
  }

  if (pulsing) {
    send_json(client, 409, "{\"ok\":false,\"error\":\"busy\"}");
    return;
  }

  seconds = clamp_seconds(seconds);
  strncpy(active_command_id, cid, sizeof(active_command_id) - 1);
  active_command_id[sizeof(active_command_id) - 1] = '\0';
  pulsing = true;
  pulse_end_ms = millis() + (unsigned long)(seconds * 1000.0f);
  relay_set(true);
  status_led_flash(LedMode::Pulse, (unsigned long)(seconds * 1000.0f));

  JsonDocument resp;
  resp["result"] = "pulsed";
  resp["command_id"] = cid;
  resp["seconds"] = seconds;
  String out;
  serializeJson(resp, out);
  send_json(client, 200, out);
  Serial.printf("door pulse cid=%s sec=%.1f\n", cid, seconds);
}

static void serve_http() {
  EthernetClient client = server.available();
  if (!client) return;
  client.setTimeout(500);

  String req;
  req.reserve(256);
  unsigned long start = millis();
  while (client.connected() && millis() - start < 1500) {
    while (client.available()) {
      char c = (char)client.read();
      req += c;
      if ((int)req.length() > HTTP_MAX_REQ_BYTES) {
        send_json(client, 413, "{\"ok\":false,\"error\":\"req_too_large\"}");
        client.stop();
        return;
      }
      if (req.endsWith("\r\n\r\n")) break;
    }
    if (req.endsWith("\r\n\r\n")) break;
    esp_task_wdt_reset();
  }

  int content_len = 0;
  int cl = req.indexOf("Content-Length:");
  if (cl >= 0) content_len = req.substring(cl + 15).toInt();
  if (content_len < 0) content_len = 0;
  if (content_len > HTTP_MAX_BODY_BYTES) {
    send_json(client, 413, "{\"ok\":false,\"error\":\"body_too_large\"}");
    client.stop();
    return;
  }

  String body;
  body.reserve(content_len);
  while ((int)body.length() < content_len && millis() - start < 2500) {
    while (client.available() && (int)body.length() < content_len) {
      body += (char)client.read();
    }
    esp_task_wdt_reset();
  }

  bool get_health = req.startsWith("GET /v1/health");
  bool post_door = req.startsWith("POST /v1/door/command");

  if (get_health) {
    handle_health(client);
  } else if (post_door) {
    if (!auth_ok(req)) {
      send_json(client, 401, "{\"ok\":false,\"error\":\"unauthorized\"}");
    } else {
      handle_door_command(client, body);
    }
  } else {
    send_json(client, 404, "{\"ok\":false,\"error\":\"not_found\"}");
  }
  client.stop();
}

static void probe_devices() {
  dht.begin();
  delay(1500);
  float t = dht.readTemperature();
  float h = dht.readHumidity();
  if (!isnan(t) && !isnan(h) && !(fabsf(t - 85.0f) < 0.5f && h < 0.5f) &&
      t >= -10.0f && t <= 60.0f && h >= 0.0f && h <= 100.0f) {
    dht_present = true;
  } else {
    dht_present = false;
  }
  Serial.printf("dht probe: present=%d t=%.1f h=%.1f\n", dht_present ? 1 : 0, t, h);

  pinMode(PIN_PIR, INPUT);
#if PIR_FORCE_PRESENT
  pir_present = true;
#else
  int same = 0;
  int prev = digitalRead(PIN_PIR);
  for (int i = 0; i < 10; i++) {
    delay(20);
    int v = digitalRead(PIN_PIR);
    if (v == prev) same++;
    prev = v;
  }
  pir_present = (same >= 8);
#endif
  last_pir = digitalRead(PIN_PIR);
  pir_stable_high = (PIR_ACTIVE_HIGH ? last_pir == HIGH : last_pir == LOW);
  Serial.printf("pir probe: present=%d raw=%d\n", pir_present ? 1 : 0, last_pir);

  pinMode(PIN_BUTTON, INPUT_PULLUP);
#if BUTTON_FORCE_PRESENT
  button_present = true;
#else
  button_present = false;  // 默认不宣称有按钮，避免空脚误报
#endif
  last_btn = digitalRead(PIN_BUTTON);
}

static bool dht_sample(float &t, float &h) {
  if (!dht_present) return false;
  t = dht.readTemperature();
  h = dht.readHumidity();
  if (isnan(t) || isnan(h)) return false;
  if (fabsf(t - 85.0f) < 0.5f && h < 0.5f) return false;
  if (t < -10.0f || t > 60.0f || h < 0.0f || h > 100.0f) return false;
  return true;
}

static void poll_sensors() {
  unsigned long now = millis();

  if (pir_present) {
    int v = digitalRead(PIN_PIR);
    if (v != last_pir) {
      pir_change_ms = now;
      last_pir = v;
    } else if (now - pir_change_ms >= PIR_DEBOUNCE_MS) {
      bool active = PIR_ACTIVE_HIGH ? (v == HIGH) : (v == LOW);
      if (active && !pir_stable_high) {
        pir_stable_high = true;
        if (now - last_pir_report_ms >= PIR_REPORT_COOLDOWN_MS) {
          last_pir_report_ms = now;
          status_led_flash(LedMode::Pir, 400);
          report_sense("pir", "rise", 0, 0, false);
          Serial.println("pir rise");
        }
      } else if (!active && pir_stable_high) {
        pir_stable_high = false;
        report_sense("pir", "fall", 0, 0, false);
        Serial.println("pir fall");
      }
    }
  }

  if (button_present) {
    int raw = digitalRead(PIN_BUTTON);
    int pressed_level = BUTTON_ACTIVE_LOW ? LOW : HIGH;
    if (raw != last_btn) {
      btn_change_ms = now;
      last_btn = raw;
    } else if (now - btn_change_ms >= BUTTON_DEBOUNCE_MS) {
      bool down = (raw == pressed_level);
      if (down && !btn_down) {
        btn_down = true;
        if (now - last_press_report_ms >= BUTTON_PRESS_COOLDOWN_MS) {
          last_press_report_ms = now;
          report_sense("button", "press", 0, 0, false);
        }
      } else if (!down && btn_down) {
        btn_down = false;
        report_sense("button", "release", 0, 0, false);
      }
    }
  }

  if (now - last_telemetry_ms >= TELEMETRY_INTERVAL_MS) {
    last_telemetry_ms = now;
    float t = 0, h = 0;
    bool ok = dht_sample(t, h);
    report_sense("telemetry", "", t, h, ok);
  }
}

static void init_mac() {
  // 用芯片 MAC 派生本地管理地址，避免多板 DE:AD:BE:EF 冲突
  uint8_t base[6] = {0};
  esp_read_mac(base, ESP_MAC_WIFI_STA);
  mac[0] = (base[0] & 0xFE) | 0x02;  // locally administered, unicast
  mac[1] = base[1];
  mac[2] = base[2];
  mac[3] = base[3];
  mac[4] = base[4];
  mac[5] = base[5];
  Serial.printf("eth mac %02X:%02X:%02X:%02X:%02X:%02X\n",
                mac[0], mac[1], mac[2], mac[3], mac[4], mac[5]);
}

static const char *eth_hw_name(EthernetHardwareStatus hw) {
  switch (hw) {
    case EthernetW5100: return "W5100";
    case EthernetW5200: return "W5200";
    case EthernetW5500: return "W5500";
    default: return "NoHardware";
  }
}

static const char *eth_link_name(EthernetLinkStatus st) {
  switch (st) {
    case LinkON: return "ON";
    case LinkOFF: return "OFF";
    default: return "Unknown";
  }
}

// W5500 VERSIONR @ 0x0039，正常应为 0x04
static uint8_t w5500_read_version_raw() {
  pinMode(PIN_ETH_CS, OUTPUT);
  digitalWrite(PIN_ETH_CS, HIGH);
  delay(1);
  digitalWrite(PIN_ETH_CS, LOW);
  // addr 0x0039, control=0x00 (VDM read, common regs)
  SPI.transfer(0x00);
  SPI.transfer(0x39);
  SPI.transfer(0x00);
  uint8_t ver = SPI.transfer(0x00);
  digitalWrite(PIN_ETH_CS, HIGH);
  return ver;
}

static bool eth_begin() {
  Serial.printf("eth pins CS=%d RST=%d SCK=%d MISO=%d MOSI=%d\n",
                PIN_ETH_CS, PIN_ETH_RST, PIN_ETH_SCK, PIN_ETH_MISO, PIN_ETH_MOSI);

  pinMode(PIN_ETH_RST, OUTPUT);
  digitalWrite(PIN_ETH_RST, LOW);
  delay(100);
  digitalWrite(PIN_ETH_RST, HIGH);
  // 部分模块板载复位芯片脉冲可达 ~560ms
  delay(600);

  SPI.begin(PIN_ETH_SCK, PIN_ETH_MISO, PIN_ETH_MOSI, PIN_ETH_CS);
  // MISO 浮空诊断：CS 拉高时若读到稳定 0x00，多半是线未接到芯片或芯片没电
  pinMode(PIN_ETH_CS, OUTPUT);
  digitalWrite(PIN_ETH_CS, HIGH);
  pinMode(PIN_ETH_MISO, INPUT_PULLUP);
  delay(2);
  int miso_idle = digitalRead(PIN_ETH_MISO);
  Serial.printf("eth MISO idle(with pullup)=%d (expect 1 if floating/ok)\n", miso_idle);

  // 慢速探测，排除长杜邦线/干扰
  SPI.beginTransaction(SPISettings(1000000, MSBFIRST, SPI_MODE0));
  uint8_t ver = w5500_read_version_raw();
  SPI.endTransaction();
  Serial.printf("eth spi VERSIONR=0x%02X (expect 0x04)\n", ver);
  if (ver == 0x00) {
    Serial.println("eth HARDWARE: chip silent — check VCC(3V3 or 5V per module), GND, RST high, MOSI/MISO/SCK/CS");
  }

  Ethernet.init(PIN_ETH_CS);

  // 注意：hardwareStatus()/getChip() 在 Ethernet.begin()→W5100.init() 之前恒为 0
  if (ver != 0x04 && ver != 0x00) {
    // 0xFF=总线浮空常见；非 0x04 也先尝试 begin，以兼容个别模块
    Serial.printf("eth warn: unexpected VERSIONR 0x%02X, still trying begin\n", ver);
  }
  if (ver == 0xFF || (ver == 0x00 && miso_idle == 1)) {
    Serial.println("eth tip: chip silent — check VCC/GND/RST/SPI; PIR 等外设可能拖垮供电");
  }

#if ETH_IP_0 == 0 && ETH_IP_1 == 0 && ETH_IP_2 == 0 && ETH_IP_3 == 0
  Serial.println("eth: DHCP...");
  eth_up = Ethernet.begin(mac) != 0;
#else
  IPAddress ip(ETH_IP_0, ETH_IP_1, ETH_IP_2, ETH_IP_3);
  IPAddress dns(ETH_DNS_0, ETH_DNS_1, ETH_DNS_2, ETH_DNS_3);
  IPAddress gw(ETH_GW_0, ETH_GW_1, ETH_GW_2, ETH_GW_3);
  IPAddress sn(ETH_SN_0, ETH_SN_1, ETH_SN_2, ETH_SN_3);
  Serial.printf("eth: static %u.%u.%u.%u\n", ETH_IP_0, ETH_IP_1, ETH_IP_2, ETH_IP_3);
  Ethernet.begin(mac, ip, dns, gw, sn);
  eth_up = (Ethernet.localIP() != IPAddress(0, 0, 0, 0));
#endif
  delay(500);
  EthernetHardwareStatus hw = Ethernet.hardwareStatus();
  EthernetLinkStatus link = Ethernet.linkStatus();
  Serial.printf("eth chip=%s link=%s ip=%s\n", eth_hw_name(hw), eth_link_name(link),
                Ethernet.localIP().toString().c_str());
  if (hw == EthernetNoHardware) {
    eth_up = false;
    status_led_apply(LedMode::EthDown);
    return false;
  }
  if (link == LinkOFF) eth_up = false;
  return eth_up;
}

static void eth_maintain() {
  unsigned long now = millis();
  if (now - last_eth_check_ms < ETH_RECHECK_MS) return;
  last_eth_check_ms = now;

  EthernetLinkStatus st = Ethernet.linkStatus();
  bool link = (st == LinkON) || (st == Unknown);  // 部分模块不报 link
  if (!link) {
    eth_up = false;
    return;
  }
#if ETH_IP_0 == 0 && ETH_IP_1 == 0 && ETH_IP_2 == 0 && ETH_IP_3 == 0
  Ethernet.maintain();
#endif
  if (Ethernet.localIP() == IPAddress(0, 0, 0, 0)) {
    eth_up = false;
    Serial.println("eth: reinit");
    eth_begin();
    if (eth_up) server.begin();
  } else {
    eth_up = true;
  }

  if (eth_up && (!time_synced || now - last_ntp_ms > 3600000UL)) {
    last_ntp_ms = now;
    ntp_sync_once();
  }
}

void setup() {
  Serial.begin(115200);
  delay(600);
  Serial.println();
  Serial.printf("lobn door boot fw=%s\n", LOBN_FW_VERSION);

#if !STATUS_LED_RGB
  pinMode(PIN_STATUS_LED, OUTPUT);
#endif
  status_led_apply(LedMode::Boot);

  pinMode(PIN_RELAY, OUTPUT);
  relay_release();

  // Arduino-ESP32 2.x API
  esp_task_wdt_init(WDT_TIMEOUT_SEC, true);
  esp_task_wdt_add(NULL);

  init_mac();
  if (!eth_begin()) {
    status_led_apply(LedMode::EthDown);
    Serial.println("eth: down at boot (will retry)");
  } else {
    server.begin();
    ntp_sync_once();
    last_ntp_ms = millis();
  }

  probe_devices();
  Serial.printf("lobn door ip=%s link=%d heap=%u\n",
                Ethernet.localIP().toString().c_str(),
                (int)Ethernet.linkStatus(),
                (unsigned)ESP.getFreeHeap());
  status_led_tick();
}

void loop() {
  esp_task_wdt_reset();

  if (pulsing && (long)(millis() - pulse_end_ms) >= 0) {
    relay_release();
    Serial.println("door pulse end");
  }

  eth_maintain();
  serve_http();
  poll_sensors();
  status_led_tick();
}
