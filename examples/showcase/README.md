# 展示案例 Showcase

| 文件 | 内容 | 语言 |
|---|---|---|
| `showcase-1-global-fulfilment.vsdx` | 全球订单履约：4 泳道、15 节点、3 个决策门、3 条退回虚线、跨泳道流转 | 中文 · English · 日本語 |
| `showcase-2-platform-architecture.vsdx` | 电商平台逻辑架构：接入/服务/数据三层容器 + 外部系统、同步/异步标注 | 中文 · English · русский |

每个案例同时提供导出的 `*.png`。

## UI 截图 `ui/`

| 截图 | 说明 |
|---|---|
| `panel-overview.png` | 面板总览：左侧页面/形状树，中间画布（网格只在纸面内），底部状态条 |
| `shape-inspector.png` | 选中形状：八个缩放手柄 + 旋转/连接点手柄；右侧 TEXT / GEOMETRY / STYLE（含线型）/ SHAPEDATA 可编辑 |
| `connector-inspector.png` | 选中连接线：ROUTE 区可调起点/终点方向，STYLE 区可选实线/虚线/点线/点划线/无 |

截图来自仓库自带的 `tests/serve_engine.py` + `tests/interactive.html`（真实 client.js + 真实引擎）。
