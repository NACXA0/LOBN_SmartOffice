# SmartOffice 工作台 UI

HA Ingress 深色工作台：**可折叠分组侧栏**；桌面侧栏 + 底栏状态；移动端底栏导航。交互对齐管理端「列表 → 抽屉 → 档案」，主题保持 Ingress 深色。

| 路由 | 页 | 职责 |
|------|-----|------|
| `#/overview` | 总览 | 指标下钻、状态分布、待重采 |
| `#/people` | 人员 | 名册表 + 抽屉速览 |
| `#/people/:id` | 档案 | 身份 / 人脸凭证 / 最近比对 |
| `#/people/:id/capture` | 采集 | 档案内摄像头质检 |
| `#/audit` | 审计 | 跨来源开门流水 |

技术栈：React 18 + Vite + HashRouter（`base: './'`，适配 HA Ingress）+ Radix UI + Lucide。

```bash
# 开发（需后端 :8080；一键 all 已含；在仓库根）
./START.sh addon-ui

# 构建到 app/webui（生产 / Docker / Ingress）
./START.sh addon-ui-build
```

完整工作流：[docs/开发工作流.md](../../docs/开发工作流.md) · 产品说明：[docs/SmartOffice.md](../../docs/SmartOffice.md)。
