#!/usr/bin/env bash
# 智慧办公室根入口：本地全部开发 / 环境 / 自动化测试（选中后清屏覆盖刷新）
# 各端细节仍用子目录 ./START.sh；本脚本只编排。
# 生产监控：HAOS 四 App（docs/架构-HAOS四App.md）；自研 SmartCCTV 已删除。
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

SC="$ROOT/SmartCenter"
FC="$ROOT/LOBN_FireClassroom"
FW="$SC/firmware/esphome"
FW_LEGACY="$SC/firmware/esp32s3_door"
YES=0
CI=0

for arg in "$@"; do
  case "$arg" in
    --yes|-y) YES=1 ;;
    --ci) CI=1; YES=1 ;;
  esac
done

have() { command -v "$1" >/dev/null 2>&1; }

clear_screen() {
  if [[ -t 1 && "$CI" -eq 0 ]]; then
    printf '\033[H\033[2J'
  fi
}

pause_back() {
  if [[ "$CI" -eq 1 || "$YES" -eq 1 ]]; then return 0; fi
  echo
  read -r -p "按回车返回菜单… " _
}

run_child() {
  local dir="$1"
  shift
  if [[ ! -x "$dir/START.sh" ]]; then
    echo "[FAIL] 缺少可执行 $dir/START.sh"
    return 1
  fi
  local extra=()
  [[ "$YES" -eq 1 ]] && extra+=(--yes)
  [[ "$CI" -eq 1 ]] && extra+=(--ci)
  (cd "$dir" && ./START.sh "$@" "${extra[@]}")
}

# ---------- 环境 ----------
cmd_submodules() {
  echo "=== git submodule ==="
  if [[ ! -d "$ROOT/.git" ]]; then
    echo "[WARN] 非 git 根目录，跳过"
    return 0
  fi
  git submodule status || true
  echo
  echo "将执行: git submodule update --init --recursive"
  if [[ "$YES" -eq 1 ]] || { read -r -p "继续? [y/N] " a && [[ "$a" =~ ^[Yy]$ ]]; }; then
    git submodule update --init --recursive
    echo "完成"
  else
    echo "已取消"
  fi
}

cmd_diagnose() {
  echo "=== 根仓环境检测（本地全栈）==="
  local fail=0
  have uv && echo "[OK] uv $(uv --version 2>/dev/null | head -1)" || { echo "[FAIL] uv"; fail=1; }
  have git && echo "[OK] git" || { echo "[FAIL] git"; fail=1; }
  have npm && echo "[OK] npm $(npm -v 2>/dev/null)" || echo "[WARN] 无 npm（消防教室前端）"
  local py
  py="$(uv python find 3.14 2>/dev/null || true)"
  if [[ -n "$py" ]]; then echo "[OK] python $py"; else echo "[WARN] 未 pin Python 3.14"; fi

  echo "--- 子项目 ---"
  for name in SmartCenter LOBN_FireClassroom; do
    local d="$ROOT/$name"
    if [[ -d "$d" ]]; then
      if [[ -x "$d/START.sh" ]]; then
        echo "[OK] $name/START.sh"
      else
        echo "[FAIL] $name 缺 START.sh"; fail=1
      fi
    else
      echo "[FAIL] 缺 $name（先 submodule update）"; fail=1
    fi
  done
  if [[ -d "$FW" && -f "$FW/START.sh" ]]; then
    echo "[OK] 生产固件 ESPHome $FW"
  else
    echo "[WARN] 无 SmartCenter/firmware/esphome"
  fi
  if [[ -d "$FW_LEGACY" ]]; then
    echo "[OK] 遗留 HTTP 固件 $FW_LEGACY（勿新部署）"
  fi
  [[ -f "$ROOT/docs/架构-HAOS四App.md" ]] && echo "[OK] docs/架构-HAOS四App.md" || echo "[WARN] 无架构文档"
  [[ -f "$ROOT/docs/阶段1-HAOS底座验收.md" ]] && echo "[OK] docs/阶段1-HAOS底座验收.md" || echo "[WARN] 无阶段1验收"
  [[ -f "$ROOT/docs/接口契约.md" ]] && echo "[OK] docs/接口契约.md" || echo "[WARN] 无接口契约"

  if [[ -f "$ROOT/.gitmodules" ]]; then
    echo "--- submodule ---"
    git submodule status 2>/dev/null || true
  fi

  echo
  echo ">>> SmartCenter"
  run_child "$SC" diagnose || fail=1
  echo
  echo ">>> LOBN_FireClassroom"
  run_child "$FC" diagnose || fail=1

  echo
  echo "--- 磁盘 ---"
  df -h "$ROOT" | tail -1
  return "$fail"
}

cmd_repair() {
  echo "=== 环境修复（SmartCenter + FireClassroom）==="
  echo "将依次: submodule（如需）→ SmartCenter / FireClassroom repair"
  if [[ "$YES" -eq 1 ]] || { read -r -p "继续? [y/N] " a && [[ "$a" =~ ^[Yy]$ ]]; }; then
    if [[ -d "$ROOT/.git" ]] && [[ ! -x "$SC/START.sh" || ! -x "$FC/START.sh" ]]; then
      git submodule update --init --recursive || true
    fi
    local old_yes=$YES
    YES=1
    run_child "$SC" repair || true
    run_child "$FC" repair || true
    YES=$old_yes
    if [[ -d "$FW" && ! -f "$FW/include/config.h" && -f "$FW/include/config.example.h" ]]; then
      echo "[提示] 旧 HTTP 门固件: config.example.h → config.h；生产请改 ESPHome（见 docs/架构-HAOS四App.md）"
    fi
    echo "修复编排完成"
  else
    echo "已取消"
  fi
}

cmd_test() {
  echo "=== 本地全部自动化测试 ==="
  local fail=0
  local old_yes=$YES
  YES=1

  echo
  echo ">>> SmartCenter"
  if run_child "$SC" test; then echo "[OK] SmartCenter"; else echo "[FAIL] SmartCenter"; fail=1; fi

  echo
  echo ">>> LOBN_FireClassroom"
  if run_child "$FC" test; then echo "[OK] FireClassroom"; else echo "[FAIL] FireClassroom"; fail=1; fi

  if [[ -d "$FW/host_sim" ]]; then
    echo
    echo ">>> 门禁固件 host_sim（旧 HTTP；经 SmartCenter 单测）"
    echo "[OK] 见 SmartCenter tests/test_esp_door.py · 迁移目标 ESPHome"
  fi

  YES=$old_yes
  echo
  if [[ "$fail" -eq 0 ]]; then
    echo "全部测试通过"
  else
    echo "存在失败项目（见上方）"
  fi
  return "$fail"
}

# ---------- 启动 / 停止（本地联调） ----------
cmd_start_all() {
  echo "=== 后台启动（本地联调：FireClassroom → SmartCenter）==="
  echo "生产监控/门禁：HAOS+Frigate+ESPHome（docs/架构-HAOS四App.md · docs/阶段1-HAOS底座验收.md）"
  run_child "$FC" start || true
  run_child "$SC" start || true
  echo "完成。状态请选「运维 → 状态」"
}

cmd_stop_all() {
  echo "=== 停止 ==="
  run_child "$SC" stop || true
  run_child "$FC" stop || true
  echo "已请求停止"
}

cmd_status() {
  echo "=== 状态 ==="
  echo
  echo ">>> SmartCenter"
  run_child "$SC" status || true
  echo
  echo ">>> LOBN_FireClassroom"
  run_child "$FC" status || true
}

cmd_help() {
  cat <<EOF
用法: ./START.sh [子命令] [--yes|--ci]

智慧办公室根入口 — 本地开发测试
  架构: docs/架构-HAOS四App.md
  阶段1店内验收: docs/阶段1-HAOS底座验收.md
  启动   FireClassroom + SmartCenter
  运维   状态 / 帮助
  环境   检测 / 修复 / 测试 / submodule
  开发   消防教室数据

子命令:
  diagnose | repair | test | submodules
  start | stop | status
  db-check | db-fix | db-seed | db-rebuild
  center | classroom
  help

单端: cd SmartCenter|LOBN_FireClassroom && ./START.sh
固件: cd SmartCenter/firmware/esphome && ./START.sh（Device Builder）
遗留: SmartCenter/firmware/esp32s3_door/（HTTP，勿新部署）
EOF
}

# ---------- 菜单 ----------
run_action() {
  local title="$1"
  shift
  clear_screen
  echo "智慧办公室 · $title"
  echo "----------------------------------------"
  "$@" || true
  pause_back
}

menu_start() {
  while true; do
    clear_screen
    cat <<EOF
智慧办公室 · 启动（本地）
  1) 后台启动（FireClassroom + SmartCenter）
  2) 停止
  3) 进入 SmartCenter 菜单
  4) 进入 FireClassroom 菜单
  0) 返回上级
EOF
    read -r -p "> " c
    case "$c" in
      1) run_action "启动" cmd_start_all ;;
      2) run_action "停止" cmd_stop_all ;;
      3) clear_screen; (cd "$SC" && ./START.sh) || true ;;
      4) clear_screen; (cd "$FC" && ./START.sh) || true ;;
      0) return 0 ;;
      *) ;;
    esac
  done
}

menu_ops() {
  while true; do
    clear_screen
    cat <<EOF
智慧办公室 · 运维
  1) 状态
  2) 帮助
  0) 返回上级
EOF
    read -r -p "> " c
    case "$c" in
      1) run_action "状态" cmd_status ;;
      2) run_action "帮助" cmd_help ;;
      0) return 0 ;;
      *) ;;
    esac
  done
}

menu_env() {
  while true; do
    clear_screen
    cat <<EOF
智慧办公室 · 环境检测
  1) 环境检测（根 + Center + Classroom）
  2) 环境修复 / 安装
  3) 全部自动化测试
  4) 同步 git submodule
  0) 返回上级
EOF
    read -r -p "> " c
    case "$c" in
      1) run_action "环境检测" cmd_diagnose ;;
      2) run_action "环境修复" cmd_repair ;;
      3) run_action "全部测试" cmd_test ;;
      4) run_action "submodule" cmd_submodules ;;
      0) return 0 ;;
      *) ;;
    esac
  done
}

menu_dev() {
  while true; do
    clear_screen
    cat <<EOF
智慧办公室 · 开发（消防教室数据）
  1) 数据架构检测
  2) 修复数据结构（两次确认）
  3) 注入示例数据（二次确认）
  4) 重建数据库（三次确认，清空）
  5) 进入 FireClassroom 完整菜单
  0) 返回上级
EOF
    read -r -p "> " c
    case "$c" in
      1) run_action "数据架构检测" run_child "$FC" db-check ;;
      2) run_action "修复数据结构" run_child "$FC" db-fix ;;
      3) run_action "注入示例数据" run_child "$FC" db-seed ;;
      4) run_action "重建数据库" run_child "$FC" db-rebuild ;;
      5) clear_screen; (cd "$FC" && ./START.sh) || true ;;
      0) return 0 ;;
      *) ;;
    esac
  done
}

menu() {
  while true; do
    clear_screen
    cat <<EOF
智慧办公室（本地开发测试）
  1) 启动
  2) 运维
  3) 环境检测
  4) 开发
  0) 退出
EOF
    read -r -p "> " choice
    case "$choice" in
      1) menu_start ;;
      2) menu_ops ;;
      3) menu_env ;;
      4) menu_dev ;;
      0) clear_screen; exit 0 ;;
      *) ;;
    esac
  done
}

main() {
  local cmd="${1:-}"
  case "$cmd" in
    "") menu ;;
    diagnose) cmd_diagnose ;;
    repair|install) cmd_repair ;;
    test) cmd_test ;;
    submodules|submodule) cmd_submodules ;;
    start|start-all) cmd_start_all ;;
    stop|stop-all|kill) cmd_stop_all ;;
    status) cmd_status ;;
    center|smartcenter) (cd "$SC" && exec ./START.sh "${@:2}") ;;
    classroom|fireclassroom|fc) (cd "$FC" && exec ./START.sh "${@:2}") ;;
    cctv|smartcctv)
      echo "[GONE] SmartCCTV 已从主仓删除。监控见 docs/架构-HAOS四App.md 与 docs/阶段1-HAOS底座验收.md"
      exit 1
      ;;
    db-check|db-fix|db-seed|db-rebuild) run_child "$FC" "$cmd" ;;
    help|-h|--help) cmd_help ;;
    *) echo "未知: $cmd"; cmd_help; exit 1 ;;
  esac
}

main "$@"
