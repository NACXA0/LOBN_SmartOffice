#!/usr/bin/env bash
# 业务链可达性快检（对照 docs/接口契约 + 验收清单）
# 生产：Camera→Frigate→SmartOffice→grant→HA MQTT→ESPHome
# 本板遗留：HA EspDoorAdapter HTTP → ESP :8080 ；sense → HA /api/lobn_office/esp/sense
set -u

ESP_IP="${ESP_IP:-192.168.1.250}"
HA="${HA_URL:-http://127.0.0.1:8123}"
SO="${SMARTOFFICE_URL:-http://127.0.0.1:8080}"
UI="${SMARTOFFICE_UI:-http://127.0.0.1:5173}"
FRIGATE="${FRIGATE_URL:-http://127.0.0.1:5000}"
GO2RTC="${GO2RTC_URL:-http://127.0.0.1:1984}"
CAM_HOST="${CAM_HOST:-192.168.15.1}"
CAM_PORT="${CAM_PORT:-554}"

probe_http() {
  local name="$1" url="$2" expect="${3:-}"
  local code
  code=$(curl -sS -m2 -o /tmp/lobn_chain_body -w '%{http_code}' "$url" 2>/dev/null || echo 000)
  if [[ -n "$expect" ]]; then
    if [[ "$code" == "$expect" ]]; then echo "UP   $name ($code)"; else echo "DOWN $name (got $code want $expect)"; fi
  else
    if [[ "$code" =~ ^[23] ]]; then echo "UP   $name ($code)"; elif [[ "$code" == "401" ]]; then echo "UP   $name (401 auth)"; else echo "DOWN $name ($code)"; fi
  fi
}

probe_tcp() {
  local name="$1" host="$2" port="$3"
  if timeout 1 bash -c "echo >/dev/tcp/$host/$port" 2>/dev/null; then echo "UP   $name"; else echo "DOWN $name"; fi
}

echo "=== platform ==="
probe_http "HA" "$HA/api/"
probe_http "SmartOffice API" "$SO/"
probe_http "SmartOffice UI" "$UI/"
probe_http "Frigate" "$FRIGATE/api/version"
probe_http "go2rtc" "$GO2RTC/api"
probe_tcp  "MQTT :1883" 127.0.0.1 1883
probe_tcp  "Camera RTSP" "$CAM_HOST" "$CAM_PORT"

echo "=== legacy ESP (W5500 HTTP) ==="
probe_tcp  "ESP ping/tcp :8080" "$ESP_IP" 8080
probe_http "ESP health" "http://$ESP_IP:8080/v1/health"

echo "=== notes ==="
echo "- 生产开门：MQTT home/<node>/door/command → ESPHome（勿新部署本目录）"
echo "- 本板联调：HA lobn_office door_adapter=esp, esp_base_url=http://$ESP_IP:8080, esp_token 与固件一致"
echo "- 刷脸链缺 Frigate/MQTT 时无法跑通 grant；摄像头仅 RTSP 通不够"
echo "- 验收：docs/验收清单.md · docs/阶段1-HAOS底座验收.md"
