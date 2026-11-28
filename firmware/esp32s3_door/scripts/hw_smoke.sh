#!/usr/bin/env bash
# 硬件冒烟：ESP HTTP + 可选摄像头 RTSP + HA sense 可达性
set -euo pipefail

ESP_IP="${ESP_IP:-192.168.1.250}"
ESP_TOKEN="${ESP_TOKEN:-change-me-esp-token}"
HA_URL="${HA_URL:-http://127.0.0.1:8123}"
RTSP_URL="${RTSP_URL:-}"

pass=0
fail=0
check() {
  local name="$1"; shift
  if "$@"; then
    echo "PASS  $name"
    pass=$((pass + 1))
  else
    echo "FAIL  $name"
    fail=$((fail + 1))
  fi
}

echo "== ESP $ESP_IP =="
check "ping" ping -c1 -W2 "$ESP_IP" >/dev/null
if curl -fsS -m3 "http://$ESP_IP:8080/v1/health" -o /tmp/lobn_esp_health.json; then
  echo "  health: $(cat /tmp/lobn_esp_health.json)"
  check "health.json" python3 -c 'import json;d=json.load(open("/tmp/lobn_esp_health.json"));assert d.get("ok") is True'
else
  check "health.http" false
fi

CID="smoke-$(date +%s)"
code=$(curl -sS -m3 -o /tmp/lobn_door.json -w '%{http_code}' \
  -X POST "http://$ESP_IP:8080/v1/door/command" \
  -H "Authorization: Bearer $ESP_TOKEN" \
  -H 'Content-Type: application/json' \
  -d "{\"schema\":\"door.command.v1\",\"action\":\"open\",\"command_id\":\"$CID\",\"seconds\":0.5}" || true)
echo "  door HTTP $code body=$(cat /tmp/lobn_door.json 2>/dev/null || true)"
check "door.pulse" test "$code" = "200"

bad=$(curl -sS -m3 -o /dev/null -w '%{http_code}' \
  -X POST "http://$ESP_IP:8080/v1/door/command" \
  -H 'Authorization: Bearer wrong' \
  -H 'Content-Type: application/json' \
  -d "{\"schema\":\"door.command.v1\",\"action\":\"open\",\"command_id\":\"x\",\"seconds\":1}" || true)
check "door.unauth" test "$bad" = "401"

echo "== HA $HA_URL =="
ha_code=$(curl -sS -m3 -o /dev/null -w '%{http_code}' "$HA_URL/api/" || true)
check "ha.api.up" test "$ha_code" = "401" -o "$ha_code" = "200"

if [[ -n "$RTSP_URL" ]]; then
  echo "== RTSP =="
  if command -v ffprobe >/dev/null; then
    check "rtsp.probe" timeout 8 ffprobe -v error -rtsp_transport tcp -i "$RTSP_URL" -show_entries stream=codec_type -of csv=p=0 2>/dev/null | grep -q video
  else
    echo "SKIP  rtsp.probe (no ffprobe)"
  fi
fi

echo "== summary pass=$pass fail=$fail =="
test "$fail" -eq 0
