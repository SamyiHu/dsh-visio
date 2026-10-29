# 交接任务：修好 Visio 面板里「连接线」的手动编辑

> 给接手的新 agent。这份文件只写事实、已验证的部分、和没验证的部分。
> 不要相信任何「测试全绿」就代表功能可用——本项目的历史教训正是这个。

## 1. 项目位置与环境

- 插件仓库：`C:\Users\SOC\Documents\visio-plugin`
- 通过 desktop profile 的 `link:` 安装为 `@local/dsh-visio`
- 宿主：DeepSeek Harness 桌面版（Windows）
- 版本号：`package.json` 为 **1.20.0**。**用户要求：平时不改版本号，只在准备发布时改。**
- 推送：`git push origin master`，GitHub 网络时好时坏，失败就稍后重试，不要改写历史

### 结构
```
index.js                Host 半：visio 工具 + 同源路由 /dsh-visio/op
client.js               Client 半：面板、浮窗、属性检查器、i18n（zh/en 两套字典）
engine/vsdx_core.py     读写渲染核心（OPC + XML，纯 stdlib）
engine/visio_bridge.py  JSON 行协议，ACTIONS 表分发（37 个 action）
engine/route_grammar.py 关系图布线 + 语法检查
engine/svg_raster.py    SVG→PNG（面板与导出一致）
tests/                  test_engine.py(15) / test_client_render.mjs /
                        test_client_contract.mjs / test_host_contract.mjs
```

## 2. 用户是谁、怎么验收

- SamyiHu，中文，要求**结论先行、简洁、有证据**，极度反感「说修好了但其实没好」
- 他在真实面板里操作验证，截图反馈
- 他明确说过：**「测试也不知道测的什么，完全没有一样的」**——因为现有测试只验证函数能跑，不验证交互

## 3. 当前的核心问题（未解决）

**连接线的手动编辑在真实面板里不工作。** 具体表现（用户原话）：

1. 「单拖红框，完全没反馈，就只有气泡显示坐标。松手线不动」
2. 「图形落点这个还是没显示」
3. 「只有蓝色可以（拖），红框不行」
4. 之前还有：拖线段纹丝不动

## 4. 已经做了什么（都提交了，但**没有一条被真实验证过**）

句柄体系（`client.js` 的 `withSelection()`，约 560–630 行）：

| 标记 | 外观 | 语义 | 处理器位置 |
|---|---|---|---|
| `data-route-band` | 透明 14px 抓取带 | 拖动整段 | `onCanvasPointerDown` ~1444 行 |
| `data-route-handle` | 蓝点（每段中点） | 拖动该段 | 同上 |
| `data-route-end` | 红方块（两端） | 重新胶合端点 | ~1343 行 |

对应引擎方法（`vsdx_core.py`）：
- `move_segment(shape_id, index, delta, page)` — 平移一段，端点不动
- `reglue(shape_id, end, to_id, x, y, page)` — 改端点并写**页面级 `<Connects>`**
- `bend()` / `set_route()` / `clear_route()` / `route_style()`
- `drawn_points()` — 返回**实际渲染**的折线（已做共线点简化）

已修复过的真实 bug（有据可查）：
1. 句柄曾被拼在 `</svg>` **外面**，浏览器根本不渲染 → 已改到内部
2. 句柄坐标曾用存储的 `Begin/End` 两点，而画面画的是自动布线折线 → 已改用 `drawn_points()`
3. `move_segment` 曾从两点直线开始，一拖就把自动布线覆盖掉 → 已改用 `drawn_points()`
4. 拖拽轴向曾用鼠标轴向，横向拖水平线等于没动 → 已改为按段方向取轴
5. 自动布线留下共线冗余点，拖一段只动一部分 → 已在 `_simplify()` 里删掉
6. `shapes()` ↔ `drawn_points()` ↔ `page_routes()` 曾互相递归爆栈 → 已用 `_no_points` 标志打断

## 5. 还没验证 / 高度可疑的地方（请从这里开始）

**不要继续盲改。先取得证据。**

1. **pointerdown 到底命中了什么**
   现在 `onCanvasPointerDown` 的分支顺序是：`hand 工具` → `data-route-end` → `data-route-band`/`data-route-handle` → `data-guide` → 形状。
   `event.target.closest()` 在 SVG 里对 `<rect>`/`<circle>` 应能向上找到 `<g data-route-*>`，但**没有实测过**。

2. **`event.currentTarget.querySelector('svg')` 是否拿得到**
   处理器绑定在 `.dshv-svgHost` div 上，SVG 是用 `dangerouslySetInnerHTML` 注入的。若取不到 svg，`box`/`vb` 全错，整个分支直接 return（**静默失败**，正是用户看到的「完全没反馈」）。

3. **选中重渲染会不会把句柄冲掉**
   每次 `setDoc` 都重新注入 SVG，若拖动中途触发了一次 render，句柄节点会被替换，`pointermove` 的 `drag.node` 就指向已销毁的节点。

4. **`runOp` 的 `seq` 竞态**
   `runOp` 用 `seqRef` 丢弃过期响应；拖动后立刻 `setDoc` 可能与轮询冲突。

## 6. 建议的接手方式

### 第一步：拿到真实证据（不要改代码）
在 `onCanvasPointerDown` 最开头加一行可见诊断，把命中结果写到面板状态栏（用户截图就能看到）：

```js
const hit = event.target instanceof Element
  ? (event.target.closest('[data-route-end]') ? 'end'
    : event.target.closest('[data-route-band]') ? 'band'
    : event.target.closest('[data-route-handle]') ? 'dot'
    : event.target.closest('[data-shape-id]') ? 'shape' : 'other')
  : 'none'
setNotice('hit: ' + hit)
```

让用户拖一次红框、截图。**一次就能定位**是「没命中」还是「命中了但提交失败」。

### 第二步：如果拖拽不可靠，就换交互
用户已被拖拽坑了 5 轮。可靠的替代方案：

**点端点 → 再点目标形状**（两步式，全用 click 事件）：
1. 选中连接线，端点显示红方块
2. 点红方块 → 进入「等待目标」状态（端点变绿、状态栏提示）
3. 点任意形状 → 调 `reglue(shape_id, end, to, x, y)`，落点取该形状最近的四边中点
4. 点空白 / Esc → 取消

`reglue` 引擎侧已验证可用：
```
reglue('12','end','2', x=1.75, y=6.35) →
  文件里 EndX=1.75 EndY=6.35
  Connects: [{'to':'5','cell':'BeginX'}, {'to':'3','cell':'EndX'}]   ✓
```

### 第三步：补真正有意义的测试
现有 4 套测试**不覆盖交互**。至少补：

- **引擎级**：`reglue` 后端点落在目标四边中点之一；`move_segment` 后两端点坐标不变；`_simplify` 不丢拐角
- **交互级**：用 `tests/make_uicheck.mjs` 的思路（把真实 CSS + 组件渲染进一个静态页），在**真浏览器**里用 `dsh_browser_*` 模拟 pointerdown/move/up，断言最终调用参数
- 浏览器已验证可用（见第 7 节）

## 7. 可视化调试环境（重要，已打通）

Electron 曾不可用，已用 junction 修好：
```
C:\Users\SOC\.dsh\profiles\desktop\node_modules\electron\dist
  → junction → C:\Users\SOC\.dsh\electron
```
`dsh_browser_*` 工具现已可用。

**但 DSH Web UI 有会话鉴权**，直接开 `http://127.0.0.1:60764` 会得到
`dsh web authentication required`。所以：

- 不要试图截真实面板（会浪费大量轮次）
- 正确做法：用 `node tests/make_uicheck.mjs` 生成静态页 → `python -m http.server 8931` 起在 `tests/` → 用 `dsh_browser_open http://127.0.0.1:8931/_uicheck.html` 打开 → `dsh_browser_screenshot` + `dsh_browser_execute` 做真实交互断言

## 8. 硬约束（别破坏）

- **线宽不许改文件数值**（用户明确要求）；细线只在渲染时按 1 屏幕像素画
- **不要测试写用户的真实图纸**，用 `examples/` 里的样例或临时副本
- 敏感信息不入库：不要出现 `C:\Users\SOC` 路径、真实业务图纸
- 术语：报告里用「异常」，不用「必改」

## 9. 完成标准

用户能在面板里做到这三件事，并有截图证据：
1. 选中连接线 → **看得到**两端红方块和段中点蓝点
2. 把端点移到另一个形状 → 松手后端点**贴在该形状的边上**，线跟着变
3. 把一条水平段上下拖 → 整段平移，两端不动

在拿到这些之前，**不要向用户报告「已修复」**。
