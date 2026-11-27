# 决策：归档 SmartCenter 子模块（升入父仓根）

> 状态：**已完成** · 源码在父仓根 · 工作树与 submodule 已删 · GitHub Archived · 见 [归档-SmartCenter准备清单.md](归档-SmartCenter准备清单.md)  
> 日期：2026-11-27  
> 终态架构：[../架构-HAOS四App.md](../架构-HAOS四App.md)

---

## 1. 结论

**停止把 [SmartCenter](https://github.com/NACXA0/SmartCenter) 当作与父仓平级的产品子模块。**  
店内平台（HA 配置、ESPHome 固件、**SmartCenter Add-on**）以 **LOBN_SmartOffice 仓库根** 为唯一日常入口。

| 对象 | 处理 |
|------|------|
| Add-on / `config/` / `firmware/` 源码 | 已在父仓根，继续维护 |
| 父仓文档与 `START.sh` | 指向根路径 |
| 工作树 `SmartCenter/` | **已删除** |
| GitHub `NACXA0/SmartCenter` | **Archived**（只读历史） |
| `LOBN_FireClassroom` | **仍为子模块**（云端业务，独立发版） |

产品名「SmartCenter Add-on」保留（Supervisor 侧边栏 / Ingress 标题）；归档的是**子模块仓库布局**，不是 Add-on 本身。

---

## 2. 为什么升根

1. **与现行架构一致**：父仓已是「基于 HA 的智能办公室」；SmartCCTV 归档后，店内智能层就在 Add-on，不应再套一层对等子仓。  
2. **HA 附加组件仓库布局**：Supervisor 认仓库根 `repository.yaml` + 子目录 `addon/`。  
3. **一个 git 根装一台 HAOS**：配置、固件、Add-on、总线文档同仓版本；云端业务用子模块钉 SHA。  
4. **日常入口**：仓库根 `./START.sh all`。

---

## 3. 与「归档 SmartCCTV」的区别

| | SmartCCTV | SmartCenter 子模块 |
|--|-----------|-------------------|
| 能力 | 自研 NVR / 人脸管线，被 Frigate+Add-on **替代** | 店内平台源码，**能力保留**，只改仓位 |
| 父仓动作 | 删除目录与编排 | 复制到根 → 改指向 → 删子模块 |
| 远程 | Archived | Archived |

---

## 4. 纪律

- 日常开发、文档链接、HAOS 对接说明**只写**根路径（`addon/` · `config/` · `firmware/`）。  
- FireClassroom 继续子模块；不要把小程序/云端 API 并进 `addon/`。  
- 店内文档在主仓 `docs/`；云端文档在 `LOBN_FireClassroom/docs/`。
