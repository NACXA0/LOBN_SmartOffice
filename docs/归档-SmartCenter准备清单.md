# 归档 SmartCenter 子模块：状态清单

> 背景：店内平台源码已复制到本仓根（`addon/` · `config/` · `firmware/`）。  
> 旧子模块目录 `SmartCenter/` **原样保留**；删除与 GitHub 归档**必须由你手动执行**。  
> 决策：[决策-归档SmartCenter子模块.md](决策-归档SmartCenter子模块.md) · 架构：[架构-HAOS四App.md](架构-HAOS四App.md) · 日常入口：[../README.md](../README.md)。

## A. 已完成（复制、改指向、本机验收）

- [x] 源码复制到仓库根：`addon/` · `config/` · `firmware/` · `tests/` · `pyproject.toml` · `uv.lock` · `VERSION` · `repository.yaml`
- [x] 根 `START.sh` 吸收平台命令（`all` / `addon*` / 本机 HA）；FireClassroom 仍委托子仓
- [x] 父仓文档路径改指向 `addon/` · `config/` · `firmware/`（不再以 `SmartCenter/…` 为日常入口）
- [x] 决策文与本清单；workspace 去掉已删的 SmartCCTV 文件夹项，SmartCenter 标「待归档」
- [x] `SmartCenter/README.md` 已改为「待归档」说明，指向父仓根（其它子模块文件仍未改；`.gitmodules` **未动**）
- [x] 本机验收（仓库根）：
  - `./START.sh diagnose` — 平台路径 / FireClassroom / 归档提示正常
  - `./START.sh repair --yes` + `addon-repair` — 依赖可装
  - `./START.sh addon-test` — **20 passed**
  - `./START.sh test` — **25 passed**（含修正根上 `tests/test_esp_door.py` 的 `HOST_SIM` 深度）
  - `./START.sh addon-start` → `GET /healthz` → `addon-stop` — 冒烟通过
  - `./START.sh addon-ui-build` — Vite 构建到 `addon/app/webui/` 成功

## B. 留给你手动（未勾选）

| # | 动作 | 说明 |
|---|------|------|
| 1 | GitHub 归档 | 在 GitHub 将 `NACXA0/SmartCenter` 标为 **Archived**（只读历史） |
| 2 | 去掉子模块 | `git submodule deinit -f SmartCenter`；从 `.gitmodules` 删除 SmartCenter 段；`git rm --cached SmartCenter`（或等价去掉 gitlink）；删除工作树 `SmartCenter/` |
| 3 | 附加组件商店 URL | 把根 [repository.yaml](../repository.yaml) 与 [addon/config.yaml](../addon/config.yaml) 里的 `url` 从 `NACXA0/SmartCenter` 改到父仓地址；HAOS 商店仓库改指新 URL |
| 4 | 清理 workspace | 删除 [LOBN_SmartOffice.code-workspace](../LOBN_SmartOffice.code-workspace) 里「SmartCenter（待归档）」文件夹项 |
| 5 | 提交父仓 | 确认无 secrets / `.venv` / `data/` / `config/home-assistant_v2.db*` 后自行 `git add` / `commit` |

## C. 当前正确下一动作

日常只在仓库根用 `./START.sh`。  
`SmartCenter/` 仅对照 / 回退。  
本机验收已过 → 按 **B** 表由你手动收掉子模块与远程归档。
