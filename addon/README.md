# SmartOffice Add-on

HAOS Supervisor Add-on：店内策略 sidecar — 人员凭证（人脸）、开门仲裁 → `business/access/grant`，以及 Ingress **工作台**（总览 / 人员 / 审计）。

- 专文：[docs/SmartOffice.md](../docs/SmartOffice.md)

## 本机开发

```bash
./START.sh addon-repair && ./START.sh repair   # 首次各装一次依赖
./START.sh all                                   # Vite :5173 + API :8080
```

| 命令 | 作用 |
|------|------|
| 全栈（构建页同端口） | `./START.sh addon` |
| 仅后端 / 仅前端 | `addon-api` / `addon-ui` |
| 构建工作台 | `addon-ui-build` → `app/webui` |
| 单测 | `addon-test` |
| 停残留 | `stop-all` / `addon-stop` |

## 生产

装到 HAOS；Frigate 关人脸；`packages/face_grant_mqtt.yaml` 译 grant。

长时间运行：日志滚动（`/data/logs/`）、审计/`grants_seen`/孤儿帧自动裁剪、门口匹配限流；详见专文「长时间运行」。
