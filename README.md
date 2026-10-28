# dsh-visio

[![CI](https://github.com/SamyiHu/dsh-visio/actions/workflows/ci.yml/badge.svg)](https://github.com/SamyiHu/dsh-visio/actions/workflows/ci.yml)

**在 DeepSeek Harness（DSH）Web 界面里直接看和改 Visio 图纸（.vsdx）的插件**：实时预览、形状编辑，外加一个给 Agent 用的 `visio` 工具。

引擎是纯 Python 标准库实现，**不需要装 Visio，也不依赖 Office**。

[English](README.en.md) · 简体中文

![status](https://img.shields.io/badge/status-beta-yellow)
![license](https://img.shields.io/badge/license-MIT-blue)
![engine](https://img.shields.io/badge/engine-python--stdlib-green)

## 功能

- **实时预览**：面板把 `.vsdx` 页面渲染成 SVG，每次改动后立即重绘。
- **就地编辑**：移动/缩放、文字、填充、线条、逐行文字颜色、形状数据。
- **形状库**：内置 16 种图形（流程、判定、起止……），支持导入 `.vssx` / `.vstx` 模具；图形用真实 Visio 母版几何绘制，不是几条线拼出来的。
- **连接线**：新增、加标签、删除；线自己的颜色/线宽/箭头都保留，标签从 1-D 形状的文字里读。
- **关系检查**：`validate` 能找出空连接（没有 `Connect` 行的线）、悬空 ID、漂移端点、零尺寸形状。
- **多页、缩放、平移、网格、撤销/重做**，以及文件被外部修改时的自动检测。
- **Agent 工具**：同一套能力以 `visio` 工具暴露给模型，含模具发现（`stencil_info`、`stencil_sheet`）、整图快照（`snapshot`）和自描述的 `capabilities`。

## 安装

```bash
# 1. 克隆到你的本地 bundle 目录旁
git clone https://github.com/SamyiHu/dsh-visio.git
# 2. 装进正在运行的 Harness（之后重载一次 DSH）
dsh plugin install /absolute/path/to/dsh-visio
```

手动等价做法：在 profile 的 `package.json` 里加 `"@local/dsh-visio": "link:/absolute/path/to/dsh-visio"`，执行 `pnpm install`，再重载应用。插件自带 `cordis.patch.yml`，会自动插入。

需要 `PATH` 里有 Python 3.9+（或在插件配置里设 `pythonPath`，或设环境变量 `DSH_VISIO_PYTHON`）。

## 使用

- 侧栏 → **Visio 图纸** 打开面板；浮动画布按钮可以把同一张图放进可拖动的独立窗口。
- 选目录 → 点一个 `.vsdx`：左边树列页面和形状，右边改选中形状的属性。
- Agent 侧直接说需求即可，模型会调 `visio` 工具：
  `open`、`text`、`get_shape`、`list`、`create`、`add_shape`、`move`、`set_text`、`set_cell`、
  `set_prop`、`connect`、`delete`、`validate`、`kinds`、`stencils`、`stencil_info`、
  `stencil_sheet`、`stencil_add`、`snapshot`、`capabilities`、`undo`、`redo`、`normalize`、`export`。
  `examples/basic-shapes.vssx` 是测试用的三母版模具。

## 配置

| 键 | 默认值 | 含义 |
|---|---|---|
| `pythonPath` | `python` | 引擎使用的解释器 |
| `defaultFolder` | 工作目录 | 文件浏览器起始目录 |

## 结构

```
index.js                 Host 侧：`visio` 工具 + 同源路由、引擎进程池
client.js                Client 侧：面板、浮窗、属性检查器、i18n
engine/vsdx_core.py      读写渲染核心（OPC + XML，纯标准库）
engine/visio_bridge.py   Host 调用的 JSON 行协议
engine/blank_doc.py      从零生成最小可用 .vsdx
engine/kinds.py          16 种内置图形（真实母版几何）
engine/stencil.py        .vssx/.vstx 导入
tests/                   引擎、客户端渲染、客户端契约、Host 契约
```

Host 按解释器各留一个引擎子进程，并**在任意 `engine/*.py` 变化时重启**（mtime + size 指纹），避免改完还跑旧代码。

## 开发与测试

```bash
python tests/test_engine.py          # 15 例：编辑、连线、模具、快照
node tests/test_client_render.mjs    # 无头渲染面板/检查器/新建对话框
node tests/test_client_contract.mjs  # 翻译键 + 槽位契约
node tests/test_host_contract.mjs    # 工具 schema + 路由 + 桥往返
node tests/make_uicheck.mjs          # 生成右栏布局页，可在真浏览器里量尺寸
```

## 已知限制

- SVG 预览对排版是近似（按宽度估算换行），和 Visio 不保证逐像素一致。
- 主题/母版对几何和颜色的处理是有的，但不是每条样式继承规则都实现。
- `.vsdm` 宏不执行。

## CI / CD

- `ci.yml`：push/PR 在 **Linux + Windows** 双矩阵跑语法检查、引擎 15 例、客户端契约、Host 契约，通过后产出整包 zip 附件。
- `release.yml`：打 `v*` tag 自动发 Release；**tag 与 `package.json` 版本不一致直接失败**。

## 许可

MIT，见 [LICENSE](LICENSE)。仓库不含第三方样例文件，测试自己生成文档。
