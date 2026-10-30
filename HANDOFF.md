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

## 3. 当前的核心问题

连接线手动编辑（句柄拖动、端点重连、落点预览、对齐辅助）**已全部在真实面板里验证通过**
（见第 5 节，2026-10-30）。本轮新增并验证的：

1. 走线**默认绕开图形**：单拖连接点后不会再从图形背面穿过去（26 种组合 12 → 0 穿模）。
2. 落点**所见即所得**：绿色落点标记、提示坐标、实际写入坐标三者一致。
3. 拖动线段有**对齐辅助**（蓝虚线 + `[对齐]`，Alt 临时关闭）。

已知未做（用户尚未要求）：连接线穿越**已绕开**，但多条线彼此交叉仍不处理；
图形内部连接点（非四边中点）在无 `Connection` 行的形状上仍是四边中点回退。

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

## 5. 已解决（2026-10-29，有浏览器实测证据）

原来的四个疑点全部验证过了，结论如下（证据方式：真浏览器里跑真实 `client.js` + 真实引擎，
见第 7 节的可视化调试环境）：

1. **pointerdown 命中**：`closest()` 能正常向上找到 `<g data-route-end>` / `<g data-route-handle>`，
   抓取带 `<line data-route-band>` 也能命中。**不是命中问题。**
2. **`currentTarget.querySelector('svg')`**：能拿到，`box`/`vb` 正常。**不是这个原因。**
3. **选中重渲染冲掉句柄**：存在，但只在提交后发生，拖动过程中不重渲染，不影响手势。
4. **真正的原因（四个，全部已修）**：
   - 拖线身时 `move_segment` 的 `shape_id` 传的是 `null`（代码读的是 `data-route-handle`，
     而抓取带上是 `data-route-band`）→ 引擎直接报错，表现就是「拖线完全没反应」。
   - 拖端点落点算错：指针映射按 viewBox 从原点起算，但引擎给 viewBox 加了 0.25in 边距，
     所有落点整体偏移 → 明明拖到 C，却吸到了旁边的 B。
   - `reglue` 只改胶合行和 Begin/End 单元格，不改手绘折线 → 松手后画面上的线停在旧位置。
   - `move_segment` 会连相邻拐角一起平移，贴着端点的那段把端点也拖走了；2 点直线只出 3 点
     且非轴对齐 → 「拖了线，端点跑了」。
   另外两处界面问题：zoom 工具条浮在画布上会盖住靠近底边的句柄；手绘 2 点折线会被自动布线夺回。

### 5.1 2026-10-30 第二轮（用户截图「线穿过红框」+「要直线对齐辅助」+「走线要绕开模型」）

5. **走线穿框**：`route_grammar.assign()` 在自带 `Connection` 行的形状上抛 `StopIteration`，
   整个布线返回空 → 每条连接线都退化成两点直线横穿页面。改用节点真实锚点排序后恢复。
6. **单拖连接点后从背面走线**：候选只做 0.3in 微调，两端在框两侧时无路可绕；且手绘 Geometry
   优先级高于布线器，拖出来的穿框线会被永久保留。现在布线器增加**框外通道线**候选，
   `reglue` 检测到手绘线穿框就丢弃它交给布线器重排。实测 26 种单拖组合：穿模 12 → **0**。
7. **落点所见即所得**：绿色落点标记走了第二套坐标换算（把 viewBox 原点又算了一遍），
   标记比实际落点偏 0.25in；且前端用 bbox 四边中点猜端口，与引擎真实 `Connection` 行不一致。
   现在引擎下发 `ports`、前端直接用，提示里给出确切坐标。
8. **对齐辅助**：拖动连接线段时吸附附近图形的边线与中线，蓝虚线显示对齐目标，提示带 `[对齐]`，
   按住 Alt 自由拖动。图形拖动复用同一套参考线代码。
9. **零长度连接线**：两端重合时只画出一个悬空箭头、无法抓取。改为红色虚线标记 + 保留点击区，
   `set_route` 直接拒绝创建退化走线。
10. **微台阶**：布线落在端口旁 0.017in 处留下台阶，高倍放大看着像折角，还多给一个没用的段句柄。
    `_simplify` 现在会吸收 <0.02in 的台阶，且**两端不动**。
11. **渲染与句柄一致**：SVG 改为直接画 `drawn_points()`，不再画原始 Geometry 行。

## 6. 回归测试（新增，别删）

- `python tests/test_engine.py` → **31 tests**（原 15 + 新增 16），覆盖 `reglue` / `move_segment` /
  `_simplify` / `drawn_points` / 退化连接线 / 渲染一致性 / **单拖连接点不穿模**。
  做过反向验证：把引擎实现换回旧版，多条新测试会红。
- `tests/interactive.html` + `tests/serve_engine.py` → **真浏览器交互测试 15 条全 PASS**：
  句柄出现、线身/蓝点拖动只平移该段且两端不动、红框拖到哪个形状就胶到哪个、落点贴在目标边上、
  zoom 条不遮句柄。跑法：
  ```
  python tests/make_fixture.py
  python tests/serve_engine.py 8933
  浏览器打开 http://127.0.0.1:8933/_harness.html?live=1&spec=1   → window.__SPEC__ 全 PASS
  ```
  （注意：`_harness.html` 必须挂在根路径，面板的 `apiPath()` 是按 `document.baseURI` 解析的。）
- `node tests/test_client_render.mjs` / `node tests/test_client_contract.mjs` 仍全绿。
- `node tests/test_host_contract.mjs` 在本机沙箱下会红：Node 里 spawn python 被拒（`spawn EPERM`），
  是环境限制不是代码问题；在正常 shell 下跑得通。

## 7. 可视化调试环境（重要，已打通）

Electron 曾不可用，已用 junction 修好：
```
C:\Users\SOC\.dsh\profiles\desktop\node_modules\electron\dist
  → junction → C:\Users\SOC\.dsh\electron
```
`dsh_browser_*` 工具可用。

**DSH Web UI 有会话鉴权**，直接开 `http://127.0.0.1:<port>` 会得到
`dsh web authentication required`（入口是 `/?token=<launchToken>`，token 只在启动进程里，拿不到）。
所以：

- 不要试图截真实面板（会浪费大量轮次）
- 正确做法是第 6 节那套：`tests/serve_engine.py` 把真引擎挂成 HTTP，`tests/interactive.html`
  在根路径 `/_harness.html` 渲染真面板 → `dsh_browser_execute` 派发 PointerEvent 做真实交互断言

## 8. 硬约束（别破坏）

- **线宽不许改文件数值**（用户明确要求）；细线只在渲染时按 1 屏幕像素画
- **不要测试写用户的真实图纸**，用 `examples/` 里的样例或 `tests/fixtures/` 的临时副本
- 敏感信息不入库：不要出现 `C:\Users\SOC` 路径、真实业务图纸
- 术语：报告里用「异常」，不用「必改」
- 平时不改 `package.json` 版本号，只在准备发布时改

## 9. 完成标准

用户能在面板里做到这三件事，并有截图证据：

1. 选中连接线 → **看得到**两端红方块和段中点蓝点
2. 把端点移到另一个形状 → 松手后端点**贴在该形状的边上**，线跟着变
3. 把一条水平段上下拖 → 整段平移，两端不动

三条都已在真浏览器里通过（`tests/interactive.html?spec=1` 的 15 条断言 + `docs/connector-edit.png`），
剩下的只有用户在**真实面板**里的最终确认。
