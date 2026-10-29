window.__ModuleLoader__.load({
  id: '@local/dsh-visio',
  factory(require) {
    const React = require('react')
    const h = React.createElement
    const { useCallback, useEffect, useMemo, useRef, useState } = React

    const NS = '@local/dsh-visio'
    const ROUTE = 'dsh-visio'
    const PANEL_ID = 'dsh-visio'
    const POLL_MS = 2500
    // Bumped with every release: the footer shows it, so a stale bundle is obvious.
    const CLIENT_BUILD = '1.18.2'

    /* ------------------------------------------------------------- locale */

    const zh = {
      nav: 'Visio 图纸',
      title: 'Visio 图纸',
      subtitle: '读取、创建、修改 .vsdx，并实时预览',
      files: '图纸文件',
      shapes: '形状',
      pages: '页面',
      folder: '文件夹',
      chooseFolder: '选择文件夹',
      refresh: '刷新',
      newFile: '新建',
      openFile: '打开',
      noFiles: '这个文件夹里没有 .vsdx 文件',
      noDocTitle: '还没有打开图纸',
      noDocBody: '从左侧选择一个 .vsdx，或者新建一张空白图纸。预览、修改和保存都在这里完成，不需要安装 Visio。',
      emptyFolder: '（未选择文件夹）',
      page: '页',
      shape: '形状',
      connector: '连接线',
      textShape: '文本',
      noShapes: '这一页还没有形状',
      selectShape: '在预览或列表里点一个形状来编辑。',
      text: '文本',
      textPlaceholder: '形状文字（支持多行）',
      geometry: '位置与大小',
      outOfPage: '已超出页面范围',
      occlusion: '遮挡',
      textBg: '文字背景遮挡',
      textBgHint: '打开后文本框带白底，会遮住下面的连线',
      snapBack: '拉回页面',
      x: 'X',
      y: 'Y',
      width: '宽',
      height: '高',
      style: '外观',
      fill: '填充',
      line: '线条',
      weight: '线宽',
      shapeData: '形状数据',
      addProp: '添加属性',
      propName: '属性名',
      propValue: '值',
      deleteShape: '删除形状',
      connectTo: '连接到',
      connect: '加连接线',
      connectedTo: '已连接到 #{id}',
      duplicatedAs: '已复制并连接 #{id}',
      connectLabel: '连接线文字',
      tools: '添加形状',
      addRect: '矩形',
      addEllipse: '椭圆',
      addLine: '直线',
      addText: '文本',
      createTitle: '新建 Visio 图纸',
      createName: '文件名',
      createNameHint: '可以省略 .vsdx 后缀',
      createPage: '页面',
      createTitleField: '标题（可选）',
      createTitleHint: '会作为文本形状放在页面顶部',
      createCustom: '自定义',
      createIn: '保存到',
      create: '创建',
      cancel: '取消',
      sizeA4L: 'A4 横向 11.69 × 8.27',
      sizeA4P: 'A4 纵向 8.27 × 11.69',
      sizeA3L: 'A3 横向 16.54 × 11.69',
      sizeLetterL: 'Letter 横向 11 × 8.5',
      deleteConfirm: '删除形状 #{id}？这会同时删除与它相连的连接线。',
      saved: '已保存',
      busy: '正在处理…',
      refreshing: '正在刷新…',
      readOnlyHint: '每次保存都会在旁边留一份 .bak-时间戳 备份（保留最近 20 份）。',
      loadError: '无法读取图纸',
      createFailed: '新建失败',
      retry: '重试',
      pythonMissing: '找不到 Python 解释器，图纸引擎无法运行。请确认 python 在 PATH 中，或在插件配置里设置 pythonPath。',
      folderMissing: '默认文件夹不存在，请选择一个文件夹。',
      shapesCount: '{count} 个形状',
      pageOf: '第 {page} / {total} 页',
      selected: '已选中 #{id}',
      deselect: '取消选择',
      unnamed: '（未命名）',
      preview: '实时预览',
      lang: 'zh',
      stencil: '模具（.vssx）',
      stencilPlaceholder: '模具文件路径',
      stencilHint: '填一个 .vssx/.vstx 路径后点载入，即可把里面的母版插进图纸。',
      load: '载入',
      gridToggle: '网格：显示/隐藏（导出跟随此开关）',
      export: '导出',
      validate: '检查关系',
      validateClean: '关系检查通过：没有空关系或悬空端点',
      validateIssues: '关系检查：',
      exportPng: '导出 PNG',
      exported: '已导出',
      undo: '撤销',
      redo: '重做',
      undoHint: '撤销上一步 (Ctrl+Z)',
      redoHint: '重做 (Ctrl+Shift+Z / Ctrl+Y)',
      zoomIn: '放大（Ctrl+滚轮）',
      zoomOut: '缩小（Ctrl+滚轮）',
      zoomFit: '适应',
      handTool: '抓手（拖动平移）',
      toggleTree: '显示/隐藏左侧列表',
      toggleInspector: '显示/隐藏右侧属性',
      floatTip: '打开浮动画布窗口（可拖动、可改大小）',
      floatTitle: 'Visio 图纸 · 浮动画布',
      floatMove: '拖动移动',
      floatClose: '收起窗口',
      fixUnits: '修复单位',
      fixUnitsTip: '把文件里标错的单位（U=MM/PT）改回 Visio 内部单位，修正 Visio 打开时页面/字号/线宽异常',
      autosave: '自动保存',
      externalChanged: '文件已在别处更新，预览已刷新',
      opFailed: '操作失败',
    }

    const en = {
      nav: 'Visio drawings',
      title: 'Visio drawings',
      subtitle: 'Read, create and edit .vsdx with a live preview',
      files: 'Drawings',
      shapes: 'Shapes',
      pages: 'Pages',
      folder: 'Folder',
      chooseFolder: 'Choose folder',
      refresh: 'Refresh',
      newFile: 'New',
      openFile: 'Open',
      noFiles: 'No .vsdx files in this folder',
      noDocTitle: 'No drawing open',
      noDocBody: 'Pick a .vsdx on the left, or create a blank drawing. Preview, edits and saves all happen here — Visio is not required.',
      emptyFolder: '(no folder selected)',
      page: 'Page',
      shape: 'Shape',
      connector: 'Connector',
      textShape: 'Text',
      noShapes: 'This page has no shapes yet',
      selectShape: 'Click a shape in the preview or the list to edit it.',
      text: 'Text',
      textPlaceholder: 'Shape text (multi-line)',
      geometry: 'Position and size',
      outOfPage: 'Outside the page',
      occlusion: 'Occlusion',
      textBg: 'Opaque text background',
      textBgHint: 'Paints a white block behind the text so it hides lines underneath',
      snapBack: 'Bring back',
      x: 'X',
      y: 'Y',
      width: 'W',
      height: 'H',
      style: 'Appearance',
      fill: 'Fill',
      line: 'Line',
      weight: 'Weight',
      shapeData: 'Shape data',
      addProp: 'Add property',
      propName: 'Name',
      propValue: 'Value',
      deleteShape: 'Delete shape',
      connectTo: 'Connect to',
      connect: 'Add connector',
      connectedTo: 'Connected to #{id}',
      duplicatedAs: 'Duplicated and linked #{id}',
      connectLabel: 'Connector text',
      tools: 'Add shape',
      addRect: 'Rectangle',
      addEllipse: 'Ellipse',
      addLine: 'Line',
      addText: 'Text',
      createTitle: 'New Visio drawing',
      createName: 'File name',
      createNameHint: '.vsdx is added when omitted',
      createPage: 'Page',
      createTitleField: 'Title (optional)',
      createTitleHint: 'Drawn as a text shape at the top of the page',
      createCustom: 'Custom',
      createIn: 'Save to',
      create: 'Create',
      cancel: 'Cancel',
      sizeA4L: 'A4 landscape 11.69 × 8.27',
      sizeA4P: 'A4 portrait 8.27 × 11.69',
      sizeA3L: 'A3 landscape 16.54 × 11.69',
      sizeLetterL: 'Letter landscape 11 × 8.5',
      deleteConfirm: 'Delete shape #{id}? Its connectors are removed too.',
      saved: 'Saved',
      busy: 'Working…',
      refreshing: 'Refreshing…',
      readOnlyHint: 'Every save keeps a .bak-<timestamp> copy beside the file (last 20 kept).',
      loadError: 'Cannot read the drawing',
      createFailed: 'Create failed',
      retry: 'Retry',
      pythonMissing: 'Python was not found, so the drawing engine cannot run. Make python available on PATH or set pythonPath in the plugin config.',
      folderMissing: 'The default folder does not exist; choose one.',
      shapesCount: '{count} shapes',
      pageOf: 'Page {page} of {total}',
      selected: 'Selected #{id}',
      deselect: 'Clear selection',
      unnamed: '(unnamed)',
      preview: 'Live preview',
      lang: 'en',
      stencil: 'Stencil (.vssx)',
      stencilPlaceholder: 'Path to a .vssx',
      stencilHint: 'Load a .vssx/.vstx to insert its masters into the drawing.',
      load: 'Load',
      gridToggle: 'Grid on/off (export follows this)',
      export: 'Export',
      validate: 'Audit',
      validateClean: 'Relationship check passed: no empty links or floating endpoints',
      validateIssues: 'Relationship check: ',
      exportPng: 'Export PNG',
      exported: 'Exported',
      undo: 'Undo',
      redo: 'Redo',
      undoHint: 'Undo last step (Ctrl+Z)',
      redoHint: 'Redo (Ctrl+Shift+Z / Ctrl+Y)',
      zoomIn: 'Zoom in (Ctrl+wheel)',
      zoomOut: 'Zoom out (Ctrl+wheel)',
      zoomFit: 'Fit',
      handTool: 'Hand tool (drag to pan)',
      toggleTree: 'Show or hide the file/shape list',
      toggleInspector: 'Show or hide the inspector',
      floatTip: 'Open the floating Visio canvas (drag and resize)',
      floatTitle: 'Visio drawing · floating canvas',
      floatMove: 'Drag to move',
      floatClose: 'Close window',
      fixUnits: 'Fix units',
      fixUnitsTip: 'Rewrite mislabelled cell units (U=MM/PT) to Visio internal units so page size, font size and line weight match',
      autosave: 'Auto-save',
      externalChanged: 'The file changed elsewhere; preview refreshed',
      opFailed: 'Operation failed',
    }

    /* -------------------------------------------------------------- helpers */

    function apiPath(path) {
      const relative = String(path).replace(/^\/+/, '')
      return new URL(relative, document.baseURI).pathname
    }

    async function getJson(path) {
      const response = await fetch(apiPath(path), {
        headers: { accept: 'application/json' },
        credentials: 'same-origin',
      })
      const payload = await response.json().catch(() => null)
      if (!response.ok) throw new Error(payload?.error ?? `HTTP ${response.status}`)
      return payload
    }

    async function postJson(path, body) {
      const response = await fetch(apiPath(path), {
        method: 'POST',
        headers: { 'content-type': 'application/json', accept: 'application/json' },
        credentials: 'same-origin',
        body: JSON.stringify(body),
      })
      const payload = await response.json().catch(() => null)
      if (!response.ok || payload?.ok === false) {
        throw new Error(payload?.error ?? `HTTP ${response.status}`)
      }
      return payload
    }

    function fmtInches(value) {
      const n = Number(value)
      if (!Number.isFinite(n)) return '0'
      return String(Math.round(n * 1000) / 1000)
    }

    function shapeKindLabel(shape, t) {
      if (shape.connector) return t('connector')
      if (!shape.geometry || shape.geometry.length === 0) return t('textShape')
      if (shape.geometry.some((g) => String(g).includes('Ellipse'))) return 'Ellipse'
      if (shape.master) return shape.master
      if (shape.geometry.some((g) => String(g).includes('LineTo'))) return 'Rectangle'
      return t('shape')
    }

    function shapeTitle(shape, t) {
      const text = (shape.text || '').replace(/\s+/g, ' ').trim()
      return text || t('unnamed')
    }

    const SIZES = [
      { id: 'a4l', w: 11.6929, h: 8.2677, label: 'sizeA4L' },
      { id: 'a4p', w: 8.2677, h: 11.6929, label: 'sizeA4P' },
      { id: 'a3l', w: 16.5354, h: 11.6929, label: 'sizeA3L' },
      { id: 'letterl', w: 11, h: 8.5, label: 'sizeLetterL' },
    ]

    /* ------------------------------------------------------------------ CSS */

    const CSS_POLISH = `
/* ---- canvas: block scroller so zooming past the viewport can reach every edge */
.dshv-canvasOuter{min-width:0;overflow:hidden}
.dshv-canvasWrap{display:block;padding:0;overflow:auto;min-width:0;
  scrollbar-gutter:stable;
  background-color:var(--dsw-alias-bg-layer-2);
  background-position:0 0;
  background-attachment:local}
.dshv-canvasWrap::-webkit-scrollbar{width:12px;height:12px}
.dshv-canvasWrap::-webkit-scrollbar-thumb{background:var(--dsw-alias-border-l2);border-radius:6px;border:3px solid transparent;background-clip:content-box}
.dshv-canvasInner{display:flex;width:max-content;height:max-content;min-width:100%;min-height:100%;padding:24px;box-sizing:border-box}
.dshv-page svg{overflow:visible}
.dshv-page{margin:auto;max-width:none;box-shadow:0 8px 26px rgba(0,0,0,.16);border-radius:2px;background:transparent}

/* ---- header */
.dshv-head{padding:10px 16px;background:var(--dsw-alias-bg-layer-1);border-bottom:1px solid var(--dsw-alias-border-l2)}
.dshv-title{font-size:14px;font-weight:650;letter-spacing:.01em}
.dshv-sub{font-size:11.5px;color:var(--dsw-alias-label-secondary);margin-top:2px}
.dshv-actions{gap:8px;align-items:center}

/* ---- buttons */
.dshv-btn{height:30px;padding:0 12px;border-radius:7px;font-size:12.5px;font-weight:500;
  border-color:var(--dsw-alias-border-l2);background:var(--dsw-alias-bg-base);transition:background .12s,border-color .12s}
.dshv-btn:hover{background:var(--dsw-alias-bg-layer-2);border-color:var(--dsw-alias-brand-primary)}
.dshv-btn.ghost{color:var(--dsw-alias-label-secondary)}
.dshv-btn.ghost:hover{color:var(--dsw-alias-label-primary)}
.dshv-btn.primary{background:var(--dsw-alias-brand-primary);color:#fff;font-weight:600;box-shadow:0 1px 2px rgba(0,0,0,.12)}
.dshv-btn.small{height:26px;padding:0 9px;font-size:12px}

/* ---- panes */
.dshv-left{width:246px;flex:0 0 246px;background:var(--dsw-alias-bg-layer-1);border-right:1px solid var(--dsw-alias-border-l2)}
.dshv-right{width:308px;flex:0 0 308px;background:var(--dsw-alias-bg-layer-1);border-left:1px solid var(--dsw-alias-border-l2)}
.dshv-section{padding:12px 14px;border-bottom:1px solid var(--dsw-alias-border-l1)}
.dshv-sectionTitle{font-size:10.5px;letter-spacing:.08em;color:var(--dsw-alias-label-secondary);margin-bottom:8px}
.dshv-hint{font-size:11px;color:var(--dsw-alias-label-secondary);line-height:1.5}

/* ---- tabs + list */
.dshv-tabs{gap:2px;padding:6px 8px 0;border-bottom:1px solid var(--dsw-alias-border-l1)}
.dshv-tab{height:26px;padding:0 10px;border-radius:6px 6px 0 0;font-size:12px;color:var(--dsw-alias-label-secondary)}
.dshv-tab.active{color:var(--dsw-alias-label-primary);background:var(--dsw-alias-bg-base);border:1px solid var(--dsw-alias-border-l1);border-bottom-color:transparent}
.dshv-file{padding:6px 10px;border-radius:6px;margin:2px 6px;cursor:pointer}
.dshv-file:hover{background:var(--dsw-alias-bg-layer-2)}
.dshv-file.active{background:var(--dsw-alias-brand-primary);color:#fff}
.dshv-file.active .dshv-fileMeta{color:rgba(255,255,255,.8)}

/* ---- inputs */
.dshv-input{height:28px;border-radius:6px;border-color:var(--dsw-alias-border-l2);background:var(--dsw-alias-bg-base);font-size:12.5px}
.dshv-input:focus{outline:2px solid var(--dsw-alias-brand-primary);outline-offset:-1px}

/* ---- zoom toolbar */
.dshv-zoom{right:16px;bottom:16px;gap:2px;padding:4px;border-radius:11px;background:var(--dsw-alias-bg-base);
  border:1px solid var(--dsw-alias-border-l2);box-shadow:0 6px 20px rgba(0,0,0,.18)}
.dshv-zbtn{min-width:32px;height:30px;border-radius:7px;font-size:15px;font-weight:600;color:var(--dsw-alias-label-primary)}
.dshv-zbtn:hover{background:var(--dsw-alias-bg-layer-2)}
.dshv-zfit{min-width:64px;font-size:12px;font-weight:600;font-variant-numeric:tabular-nums;letter-spacing:.02em}
.dshv-zbtn.on{background:var(--dsw-alias-brand-primary);color:#fff}
.dshv-toggle{width:30px;height:30px;font-size:14px;border-color:var(--dsw-alias-border-l2);background:var(--dsw-alias-bg-base)}
.dshv-toggle.on{background:var(--dsw-alias-bg-layer-2);color:var(--dsw-alias-label-primary);border-color:var(--dsw-alias-border-l2)}
`

    const CSS = `
.dshv-root{display:flex;flex-direction:column;height:100%;min-height:0;background:var(--dsw-alias-bg-base);color:var(--dsw-alias-label-primary);
  font-family:system-ui,-apple-system,"Segoe UI","Microsoft YaHei",sans-serif;font-size:13px;line-height:1.45}
.dshv-head{display:flex;align-items:center;gap:10px;padding:12px 16px 10px;border-bottom:1px solid var(--dsw-alias-border-l1);flex:0 0 auto}
.dshv-headText{min-width:0;flex:1}
.dshv-title{font-size:15px;font-weight:600;letter-spacing:.01em;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.dshv-sub{font-size:12px;color:var(--dsw-alias-label-secondary);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.dshv-actions{display:flex;align-items:center;gap:6px;flex:0 0 auto}
.dshv-btn{display:inline-flex;align-items:center;gap:6px;height:28px;padding:0 10px;border-radius:6px;border:1px solid var(--dsw-alias-border-l2);
  background:var(--dsw-alias-bg-layer-1);color:var(--dsw-alias-label-primary);font:inherit;font-size:12px;cursor:pointer;white-space:nowrap}
.dshv-btn:hover{background:var(--dsw-alias-bg-layer-2)}
.dshv-btn:disabled{opacity:.5;cursor:default}
.dshv-btn.primary{background:var(--dsw-alias-brand-primary);border-color:transparent;color:#fff}
.dshv-btn.primary:hover{filter:brightness(1.06)}
.dshv-btn.ghost{border-color:transparent;background:transparent}
.dshv-btn.ghost:hover{background:var(--dsw-alias-bg-layer-2)}
.dshv-btn.danger{color:var(--dsw-alias-state-error-primary);border-color:var(--dsw-alias-border-l2)}
.dshv-btn.small{height:24px;padding:0 8px;font-size:11px}
.dshv-body{flex:1;display:flex;min-height:0}
.dshv-pane{display:flex;flex-direction:column;min-height:0;background:var(--dsw-alias-bg-base)}
.dshv-pane.dshv-left{overflow-y:auto;overflow-x:hidden}
.dshv-pane.dshv-left>*{flex:0 0 auto}
.dshv-pane.dshv-left .dshv-shapeList{flex:0 0 auto;max-height:34vh}
.dshv-pane.dshv-left .dshv-files{flex:0 0 auto}
.dshv-tabs{flex:0 0 auto;min-height:34px}
.dshv-tab{white-space:nowrap}
.dshv-left{width:238px;flex:0 0 238px;border-right:1px solid var(--dsw-alias-border-l1)}
.dshv-right{width:300px;flex:0 0 300px;border-left:1px solid var(--dsw-alias-border-l1);overflow:auto}
.dshv-center{flex:1;min-width:0;display:flex;flex-direction:column;background:var(--dsw-alias-bg-layer-2)}
.dshv-section{padding:10px 12px;border-bottom:1px solid var(--dsw-alias-border-l1)}
.dshv-sectionTitle{display:flex;align-items:center;justify-content:space-between;font-size:11px;font-weight:600;letter-spacing:.06em;
  text-transform:uppercase;color:var(--dsw-alias-label-secondary);margin-bottom:6px}
.dshv-field{display:flex;align-items:center;gap:6px;margin-bottom:6px}
.dshv-field label{flex:0 0 62px;font-size:12px;color:var(--dsw-alias-label-secondary)}
.dshv-input{flex:1;min-width:0;height:26px;padding:0 7px;border-radius:5px;border:1px solid var(--dsw-alias-border-l1);
  background:var(--dsw-alias-bg-layer-1);color:var(--dsw-alias-label-primary);font:inherit;font-size:12px}
.dshv-input:focus{outline:none;border-color:var(--dsw-alias-brand-primary)}
textarea.dshv-input{width:100%;box-sizing:border-box;height:auto;min-height:74px;padding:7px 8px;resize:vertical;line-height:1.5}
.dshv-check{display:flex;align-items:center;gap:6px;font-size:12px;margin-bottom:6px;cursor:pointer}
.dshv-check input{accent-color:var(--dsw-alias-brand-primary)}
.dshv-warn{display:flex;align-items:center;gap:8px;margin-top:6px;font-size:12px;color:var(--dsw-alias-state-error)}
.dshv-row{display:flex;gap:6px;align-items:center}
.dshv-grid4{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:6px;align-items:end}
.dshv-col{min-width:0;flex:1 1 0}
.dshv-col .dshv-input{width:100%;box-sizing:border-box}
.dshv-col{flex:1;min-width:0}
.dshv-grow{flex:1}
.dshv-hint{font-size:11px;color:var(--dsw-alias-label-secondary);line-height:1.5}
.dshv-files{overflow:auto;flex:1;min-height:0}
.dshv-file{display:flex;align-items:center;gap:8px;padding:6px 12px;cursor:pointer;border-left:2px solid transparent}
.dshv-file:hover{background:var(--dsw-alias-bg-layer-2)}
.dshv-file.active{border-left-color:var(--dsw-alias-brand-primary);background:var(--dsw-alias-bg-layer-2)}
.dshv-fileName{flex:1;min-width:0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;font-size:12px}
.dshv-fileMeta{font-size:10px;color:var(--dsw-alias-label-secondary)}
.dshv-shapeList{overflow:auto;flex:1;min-height:0}
.dshv-shapeRow{display:flex;align-items:center;gap:8px;padding:5px 12px;cursor:pointer;border-left:2px solid transparent}
.dshv-shapeRow:hover{background:var(--dsw-alias-bg-layer-2)}
.dshv-shapeRow.active{border-left-color:var(--dsw-alias-brand-primary);background:var(--dsw-alias-bg-layer-2)}
.dshv-shapeId{font:11px ui-monospace,Consolas,monospace;color:var(--dsw-alias-label-secondary);flex:0 0 24px}
.dshv-shapeText{flex:1;min-width:0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.dshv-shapeKind{font-size:10px;color:var(--dsw-alias-label-secondary);flex:0 0 auto}
.dshv-canvasOuter{position:relative;flex:1;min-height:0;min-width:0;display:flex;overflow:hidden}
.dshv-canvasWrap{flex:1;min-height:0;min-width:0;overflow:auto;padding:20px;display:flex;justify-content:center;align-items:center;position:relative}
.dshv-page{position:relative;background:transparent;box-shadow:0 8px 26px rgba(0,0,0,.16);border-radius:2px;max-width:100%}
.dshv-page svg{display:block;width:100%;height:auto}
.dshv-page [data-shape-id]{cursor:pointer}
.dshv-page [data-shape-id]:hover>*:first-child{stroke:var(--dsw-alias-brand-primary);stroke-width:.024}
.dshv-page [data-shape-id]:hover>rect[fill="transparent"]{stroke:none}
.dshv-overlay{position:absolute;inset:0;width:100%;height:100%;pointer-events:none;overflow:visible}
.dshv-empty{flex:1;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:10px;padding:40px;text-align:center;color:var(--dsw-alias-label-secondary)}
.dshv-empty h2{margin:0;font-size:16px;color:var(--dsw-alias-label-primary)}
.dshv-empty p{margin:0;max-width:380px;font-size:12px;line-height:1.6}
.dshv-badge{display:inline-flex;align-items:center;gap:4px;height:18px;padding:0 6px;border-radius:9px;font-size:10px;
  background:var(--dsw-alias-bg-layer-2);color:var(--dsw-alias-label-secondary)}
.dshv-status{flex:0 0 auto;display:flex;align-items:center;gap:10px;padding:5px 14px;border-top:1px solid var(--dsw-alias-border-l1);
  font-size:11px;color:var(--dsw-alias-label-secondary);background:var(--dsw-alias-bg-base);min-height:28px}
.dshv-status .err{color:var(--dsw-alias-state-error-primary)}
.dshv-status .dshv-ver{font-size:10.5px;color:var(--dsw-alias-label-secondary);opacity:.75}
.dshv-status .ok{color:var(--dsw-alias-state-success-primary)}
.dshv-spinner{width:11px;height:11px;border-radius:50%;border:2px solid var(--dsw-alias-border-l2);border-top-color:var(--dsw-alias-brand-primary);
  animation:dshv-spin .8s linear infinite;display:inline-block}
@keyframes dshv-spin{to{transform:rotate(360deg)}}
.dshv-overlayDialog{position:absolute;inset:0;background:rgba(0,0,0,.35);display:flex;align-items:center;justify-content:center;z-index:20}
.dshv-dialog{width:420px;max-width:calc(100% - 40px);background:var(--dsw-alias-bg-overlay);border:1px solid var(--dsw-alias-border-l1);
  border-radius:10px;box-shadow:0 12px 36px rgba(0,0,0,.3);padding:16px 18px}
.dshv-dialog h3{margin:0 0 12px;font-size:14px}
.dshv-dialog .dshv-field label{flex-basis:76px}
.dshv-dialogActions{display:flex;justify-content:flex-end;gap:8px;margin-top:14px}
.dshv-swatch{width:26px;height:24px;padding:0;border:1px solid var(--dsw-alias-border-l1);border-radius:5px;background:none;cursor:pointer}
.dshv-propRow{display:flex;gap:6px;align-items:center;margin-bottom:5px}
.dshv-propName{flex:0 0 96px;font-size:11px;color:var(--dsw-alias-label-secondary);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.dshv-tabs{display:flex;gap:2px;padding:8px 10px 0;border-bottom:1px solid var(--dsw-alias-border-l1)}
.dshv-tab{flex:1;height:26px;border:none;border-bottom:2px solid transparent;background:none;color:var(--dsw-alias-label-secondary);
  font:inherit;font-size:12px;cursor:pointer}
.dshv-tab.active{color:var(--dsw-alias-label-primary);border-bottom-color:var(--dsw-alias-brand-primary)}
`

    /* -------------------------------------------------------------- widgets */

    function Btn(props) {
      const { variant, small, children, ...rest } = props
      const cls = ['dshv-btn']
      if (variant) cls.push(variant)
      if (small) cls.push('small')
      return h('button', { type: 'button', ...rest, className: cls.join(' ') }, children)
    }

    function Field(props) {
      const { label, children } = props
      return h('div', { className: 'dshv-field' }, h('label', null, label), children)
    }

    /** Number input that only commits on blur / Enter. */
    function NumberField({ label, value, onCommit, step = 0.05 }) {
      const [draft, setDraft] = useState(fmtInches(value))
      const [focused, setFocused] = useState(false)
      useEffect(() => {
        if (!focused) setDraft(fmtInches(value))
      }, [value, focused])
      const commit = () => {
        const raw = String(draft).trim().replace(',', '.')
        const n = Number(raw)
        if (raw === '' || !Number.isFinite(n)) {
          setDraft(fmtInches(value))
          return
        }
        if (fmtInches(n) !== fmtInches(value)) onCommit(n)
        else setDraft(fmtInches(n))
      }
      return h('div', { className: 'dshv-col' },
        h('div', { style: { fontSize: 10, color: 'var(--dsw-alias-label-secondary)', marginBottom: 2 } }, label),
        h('input', {
          className: 'dshv-input',
          type: 'number',
          step,
          value: draft,
          onChange: (e) => setDraft(e.target.value),
          onFocus: () => setFocused(true),
          onBlur: () => { setFocused(false); commit() },
          onKeyDown: (e) => { if (e.key === 'Enter') e.currentTarget.blur() },
        }))
    }

    function ColorField({ label, value, onCommit }) {
      const hex = /^#[0-9a-fA-F]{6}$/.test(String(value ?? '')) ? String(value) : '#FFFFFF'
      const [draft, setDraft] = useState(hex)
      const timer = useRef(null)
      useEffect(() => { setDraft(hex) }, [hex])
      const change = (next) => {
        setDraft(next)
        if (timer.current) clearTimeout(timer.current)
        timer.current = setTimeout(() => onCommit(next), 250)
      }
      useEffect(() => () => { if (timer.current) clearTimeout(timer.current) }, [])
      return h(Field, { label },
        h('input', { className: 'dshv-swatch', type: 'color', value: draft, onChange: (e) => change(e.target.value) }),
        h('input', {
          className: 'dshv-input',
          value: draft,
          onChange: (e) => {
            const next = e.target.value
            setDraft(next)
            if (/^#[0-9a-fA-F]{6}$/.test(next)) change(next)
          },
          onBlur: () => { if (!/^#[0-9a-fA-F]{6}$/.test(draft)) setDraft(hex) },
        }))
    }

    function Icon(props) {
      const { size = 16 } = props
      return h('svg', {
        width: size,
        height: size,
        viewBox: '0 0 24 24',
        fill: 'none',
        stroke: 'currentColor',
        strokeWidth: 1.7,
        strokeLinejoin: 'round',
        strokeLinecap: 'round',
        'aria-hidden': 'true',
      },
      h('rect', { x: 3.2, y: 3.2, width: 7.6, height: 5.6, rx: 1.2 }),
      h('rect', { x: 13.2, y: 15.2, width: 7.6, height: 5.6, rx: 1.2 }),
      h('path', { d: 'M6.8 8.9v4.1h10.4v2.2' }),
      h('path', { d: 'M17.2 13.2l1.9 2 1.9-2' }))
    }

    function VisioIcon({ size }) {
      return h('span', { style: { display: 'inline-flex' } }, h(Icon, { size: size ?? 16 }))
    }

  /* ----------------------------------------------------------------- panel */

    function withSelection(svg, shape, pageHeight) {
      // Connector bounding boxes span their endpoints; a box around them would
      // cover half the page.  They get a stroke highlight instead (see CSS).
      if (!svg || !shape || !shape.bbox || shape.connector) return svg
      const box = shape.bbox
      const rect = '<rect x="' + box.x + '" y="' + (pageHeight - box.y - box.h).toFixed(4)
        + '" width="' + box.w + '" height="' + box.h
        + '" fill="none" stroke="#2F6FBF" stroke-width="1.6" vector-effect="non-scaling-stroke"'
        + ' stroke-dasharray="5 3" pointer-events="none"/>'
      // Guide arrows on the four sides: click = connect to an aligned neighbour,
      // or duplicate in that direction when nothing is there yet.
      const cx = box.x + box.w / 2
      const cy = box.y + box.h / 2
      const top = pageHeight - box.y - box.h
      const gap = 0.30
      const arm = 0.30
      const guides = [
        { dir: 'left', x: box.x - gap, y: top + box.h / 2, dx: -arm, dy: 0 },
        { dir: 'right', x: box.x + box.w + gap, y: top + box.h / 2, dx: arm, dy: 0 },
        { dir: 'up', x: cx, y: top - gap, dx: 0, dy: -arm },
        { dir: 'down', x: cx, y: top + box.h + gap, dx: 0, dy: arm },
      ].map((g) => {
        const tip = 'M ' + g.x + ' ' + g.y + ' L ' + (g.x - g.dx) + ' ' + (g.y - g.dy)
        const a = 'M ' + g.x + ' ' + g.y + ' L ' + (g.x - g.dx * 0.45 - g.dy * 0.32) + ' ' + (g.y - g.dy * 0.45 - g.dx * 0.32)
        const b = 'M ' + g.x + ' ' + g.y + ' L ' + (g.x - g.dx * 0.45 + g.dy * 0.32) + ' ' + (g.y - g.dy * 0.45 + g.dx * 0.32)
        return '<g data-guide="' + g.dir + '" data-guide-shape="' + shape.id + '" style="cursor:pointer">'
          + '<circle cx="' + g.x + '" cy="' + g.y + '" r="0.16" fill="#FFFFFF" fill-opacity="0.9" stroke="#8A94A6" stroke-width="1" vector-effect="non-scaling-stroke"/>'
          + '<path d="' + tip + '" stroke="#8A94A6" stroke-width="1.4" vector-effect="non-scaling-stroke" fill="none"/>'
          + '<path d="' + a + '" stroke="#8A94A6" stroke-width="1.2" vector-effect="non-scaling-stroke" fill="none"/>'
          + '<path d="' + b + '" stroke="#8A94A6" stroke-width="1.2" vector-effect="non-scaling-stroke" fill="none"/>'
          + '</g>'
      }).join('')
      const tag = '<g data-shape-id="' + shape.id + '">'
      const at = svg.indexOf(tag)
      if (at < 0) return svg
      return svg.slice(0, at + tag.length) + rect + guides + svg.slice(at + tag.length)
    }

    const LAST_DOC = 'dshv:lastDoc'

    const SHAPE_KINDS = [
      { kind: 'rect', glyph: '\u25AD', zh: '矩形', en: 'Process' },
      { kind: 'roundrect', glyph: '\u25A2', zh: '圆角', en: 'Rounded' },
      { kind: 'terminator', glyph: '\u2B2D', zh: '端点', en: 'Terminator' },
      { kind: 'ellipse', glyph: '\u25CB', zh: '椭圆', en: 'Ellipse' },
      { kind: 'diamond', glyph: '\u25C7', zh: '判定', en: 'Decision' },
      { kind: 'triangle', glyph: '\u25B3', zh: '三角', en: 'Triangle' },
      { kind: 'parallelogram', glyph: '\u25B1', zh: '数据', en: 'Data' },
      { kind: 'trapezoid', glyph: '\u23E2', zh: '梯形', en: 'Trapezoid' },
      { kind: 'hexagon', glyph: '\u2B21', zh: '六边形', en: 'Hexagon' },
      { kind: 'chevron', glyph: '\u276F', zh: '燕尾', en: 'Chevron' },
      { kind: 'arrow_right', glyph: '\u2794', zh: '右箭头', en: 'Arrow right' },
      { kind: 'arrow_left', glyph: '\u2B05', zh: '左箭头', en: 'Arrow left' },
      { kind: 'arrow_up', glyph: '\u2B06', zh: '上箭头', en: 'Arrow up' },
      { kind: 'arrow_down', glyph: '\u2B07', zh: '下箭头', en: 'Arrow down' },
      { kind: 'text', glyph: 'T', zh: '文本', en: 'Text' },
      { kind: 'line', glyph: '\u2571', zh: '直线', en: 'Line' },
    ]

    function VisioPanel(props) {
      const { t, pickFolder } = props
      const [config, setConfig] = useState(null)
      const [configError, setConfigError] = useState('')
      const [folder, setFolder] = useState(() => {
        try { return window.localStorage.getItem('dsh-visio.folder') || '' } catch (err) { return '' }
      })
      const [folderDraft, setFolderDraft] = useState('')
      const [files, setFiles] = useState([])
      const [filesBusy, setFilesBusy] = useState(false)
      const [filesError, setFilesError] = useState('')
      const [doc, setDoc] = useState(null)
      const [selected, setSelected] = useState(null)
      const [busy, setBusy] = useState(false)
      const [error, setError] = useState('')
      const [notice, setNotice] = useState('')
      const [tab, setTab] = useState('shapes')
      const [showGrid, setShowGrid] = useState(true)
      const [stencilOpen, setStencilOpen] = useState(false)
      const [createOpen, setCreateOpen] = useState(false)
      const [treeOpen, setTreeOpen] = useState(true)
      const [inspectorOpen, setInspectorOpen] = useState(true)
      const [pane, setPane] = useState({ w: 0, h: 0 })
      const isZh = t('lang') === 'zh'
      const [stencilPath, setStencilPath] = useState('')
      const [stencilFile, setStencilFile] = useState('')
      const [stencilMasters, setStencilMasters] = useState([])
      const [stencilError, setStencilError] = useState('')
      const [zoom, setZoom] = useState(null)
      const [tool, setTool] = useState('select')
      const toolRef = useRef('select')
      toolRef.current = tool
      const pageRef = useRef(null)
      const panRef = useRef(null)
      const tipRef = useRef(null)
      const rootRef = useRef(null)
      const canvasBox = useRef(null)
      useEffect(() => {
        // Measure the outer frame, never the scroller: its content box shrinks
        // when a scrollbar appears, which would feed back into the fit size.
        const node = canvasBox.current && (canvasBox.current.parentElement || canvasBox.current)
        if (!node || typeof ResizeObserver === 'undefined') return undefined
        const observer = new ResizeObserver((entries) => {
          const rect = entries[0].contentRect
          const w = Math.round(rect.width)
          const h = Math.round(rect.height)
          // A scrollbar appearing/disappearing must not re-fit the page, or the
          // layout oscillates: fit -> overflow -> scrollbar -> smaller fit -> ...
          setPane((prev) => (Math.abs(prev.w - w) < 2 && Math.abs(prev.h - h) < 2 ? prev : { w, h }))
        })
        observer.observe(node)
        return () => observer.disconnect()
      }, [doc])

      useEffect(() => {
        const wrap = canvasBox.current
        if (!wrap) return undefined
        const onWheel = (event) => {
          const hand = toolRef.current === 'hand'
          if (!event.ctrlKey && !event.metaKey && !hand) return
          event.preventDefault()
          const page = pageRef.current
          const before = page ? page.getBoundingClientRect() : null
          const fx = before && before.width ? (event.clientX - before.left) / before.width : 0.5
          const fy = before && before.height ? (event.clientY - before.top) / before.height : 0.5
          setZoom((value) => {
            const base = value ?? 1
            const next = Math.min(8, Math.max(0.15, base * (event.deltaY > 0 ? 0.9 : 1.1)))
            return Math.round(next * 1000) / 1000
          })
          if (before) {
            requestAnimationFrame(() => {
              const after = pageRef.current
              if (!after) return
              const rect = after.getBoundingClientRect()
              wrap.scrollLeft += rect.left + fx * rect.width - event.clientX
              wrap.scrollTop += rect.top + fy * rect.height - event.clientY
            })
          }
        }
        wrap.addEventListener('wheel', onWheel, { passive: false })
        return () => wrap.removeEventListener('wheel', onWheel)
      }, [doc])
      const seqRef = useRef(0)
      const docRef = useRef(null)
      const selectedRef = useRef(null)
      useEffect(() => { docRef.current = doc }, [doc])
      useEffect(() => { selectedRef.current = selected }, [selected])

      const runOp = useCallback(async (payload, options = {}) => {
        const seq = ++seqRef.current
        if (!options.quiet) setBusy(true)
        setError('')
        try {
          const state = await postJson(`${ROUTE}/op`, payload)
          if (seq !== seqRef.current) return null
          if (options.light && state && state.svg === undefined) {
            setDoc((prev) => (prev ? {
              ...prev,
              mtime: state.mtime ?? prev.mtime,
              canUndo: state.canUndo ?? prev.canUndo,
              canRedo: state.canRedo ?? prev.canRedo,
              saved: true,
            } : prev))
            setNotice(state.notice || '')
            return state
          }
          setDoc(state)
          setNotice(state.notice || options.notice || '')
          if (state.detail) setSelected(state.detail.id)
          else if (payload.action === 'delete') setSelected(null)
          return state
        } catch (err) {
          if (seq === seqRef.current) setError(err instanceof Error ? err.message : String(err))
          return null
        } finally {
          if (seq === seqRef.current) setBusy(false)
        }
      }, [])

      const undoTo = useCallback((action) => {
        const current = docRef.current
        if (!current) return
        runOp({ action, path: current.path, page: current.page })
      }, [runOp])


      const loadFolder = useCallback(async (target) => {
        if (!target) return
        setFilesBusy(true)
        setFilesError('')
        try {
          const result = await postJson(`${ROUTE}/op`, { action: 'list', dir: target })
          setFiles(result.files || [])
          const next = result.dir || target
          setFolder(next)
          try { window.localStorage.setItem('dsh-visio.folder', next) } catch (err) { /* ignore */ }
          setFolderDraft(result.dir || target)
          try { window.localStorage.setItem('dsh-visio.folder', result.dir || target) } catch { /* ignore */ }
        } catch (err) {
          setFiles([])
          setFilesError(err instanceof Error ? err.message : String(err))
        } finally {
          setFilesBusy(false)
        }
      }, [])

      useEffect(() => {
        let cancelled = false
        ;(async () => {
          try {
            const result = await getJson(`${ROUTE}/config`)
            if (cancelled) return
            setConfig(result)
            let last = result.defaultFolder
            try { last = window.localStorage.getItem('dsh-visio.folder') || last } catch { /* ignore */ }
            setFolderDraft(last || '')
            if (last) await loadFolder(last)
          } catch (err) {
            if (!cancelled) setConfigError(err instanceof Error ? err.message : String(err))
          }
        })()
        return () => { cancelled = true }
      }, [loadFolder])

      const openFile = useCallback(async (path, page) => {
        try { window.localStorage.setItem(LAST_DOC, path) } catch (err) { /* ignore */ }
        setSelected(null)
        const state = await runOp({ action: 'open', path, page: page ?? 1 })
        if (state) {
          setDoc(state)
          try { window.localStorage.setItem('dsh-visio.folder', state.folder) } catch { /* ignore */ }
          if (state.folder !== folder) setFolder(state.folder)
        }
        return state
      }, [runOp, folder])

      const openSelected = useCallback(async (shapeId, page) => {
        const current = docRef.current
        if (!current) return
        setSelected(shapeId)
        const state = await runOp({ action: 'render', path: current.path, page: page ?? current.page, selected: shapeId }, { quiet: true })
        if (state) setDoc(state)
      }, [runOp])

      // Another panel instance (the floating window) starts empty: reopen the
      // drawing this profile last had open, so both windows show the same file.
      useEffect(() => {
        if (doc) return
        let last = ''
        try { last = window.localStorage.getItem(LAST_DOC) || '' } catch (err) { last = '' }
        if (last) openFile(last, 1)
      }, [doc, openFile])

      // Keep the preview honest when the file is edited by the agent or another app.
      useEffect(() => {
        if (!doc) return undefined
        const timer = setInterval(async () => {
          if (busy || !docRef.current) return
          const active = typeof document !== 'undefined' ? document.activeElement : null
          if (active && active.closest && active.closest('.dshv-right')) return
          try {
            const stat = await postJson(`${ROUTE}/op`, { action: 'stat', path: docRef.current.path })
            if (stat.mtime && docRef.current && Math.abs(stat.mtime - docRef.current.mtime) > 0.5) {
              const page = docRef.current.page
              const keep = selectedRef.current
              const fresh = await postJson(`${ROUTE}/op`, {
                action: 'render', path: docRef.current.path, page, selected: keep ?? undefined,
              })
              setDoc(fresh)
              setNotice(t('externalChanged'))
            }
          } catch {
            /* polling is best-effort */
          }
        }, POLL_MS)
        return () => clearInterval(timer)
      }, [doc?.path, busy, t])

      const chooseFolder = useCallback(async () => {
        try {
          const picked = await pickFolder()
          if (picked) await loadFolder(picked)
        } catch (err) {
          setFilesError(err instanceof Error ? err.message : String(err))
        }
      }, [pickFolder, loadFolder])

      const shape = useMemo(() => {
        if (!doc || !selected) return null
        return (doc.shapes || []).find((s) => s.id === selected) || null
      }, [doc, selected])

      const detail = doc?.detail && doc.detail.id === selected ? doc.detail : null

      const commitText = useCallback((text) => {
        const current = docRef.current
        if (!current || !selectedRef.current) return
        runOp({ action: 'set_text', path: current.path, page: current.page, shape_id: selectedRef.current, text })
      }, [runOp])

      const commitCell = useCallback((cells) => {
        const current = docRef.current
        if (!current || !selectedRef.current) return
        runOp({ action: 'set_cells', path: current.path, page: current.page, shape_id: selectedRef.current, cells })
      }, [runOp])

      const commitMove = useCallback((geometry) => {
        const current = docRef.current
        if (!current || !selectedRef.current) return
        runOp({ action: 'move', path: current.path, page: current.page, shape_id: selectedRef.current, ...geometry })
      }, [runOp])

      const addShape = useCallback((kind) => {
        const current = docRef.current
        if (!current) return
        const { w: pageW, h: pageH } = current.pageSize
        const base = { action: 'add_shape', path: current.path, page: current.page, kind }
        if (kind === 'text') {
          runOp({ ...base, x: 0.6, y: pageH - 1.2, w: Math.max(2, pageW - 1.2), h: 0.7, text: t('textShape') })
        } else if (kind === 'line') {
          runOp({ ...base, x: pageW / 2 - 1, y: pageH / 2, w: 2, h: 1.2 })
        } else {
          runOp({ ...base, x: pageW / 2 - 0.9, y: pageH / 2 - 0.45, w: 1.8, h: 0.9, text: kind === 'ellipse' ? 'Ellipse' : 'Rectangle' })
        }
      }, [runOp, t])

      const audit = useCallback(async () => {
        const current = docRef.current
        if (!current) return
        setError('')
        try {
          const result = await postJson(`${ROUTE}/op`, { action: 'validate', path: current.path, page: current.page })
          if (!result.ok) throw new Error(result.error || 'validate failed')
          const bad = (result.issues || []).filter((item) => item.level !== 'info')
          if (!bad.length) {
            setNotice(t('validateClean'))
          } else {
            const head = bad.slice(0, 3).map((item) => `#${item.shape} ${item.message}`).join('；')
            setError(`${t('validateIssues')}${bad.length} · ${head}`)
          }
        } catch (cause) {
          setError(messageOf(cause))
        }
      }, [postJson, t])

      const exportPng = useCallback(async () => {
        const current = docRef.current
        if (!current) return
        try {
          const result = await postJson(`${ROUTE}/op`, {
            action: 'export', path: current.path, page: current.page, format: 'png', grid: showGrid,
          })
          setNotice(`${t('exported')}: ${result.path}`)
          setError('')
        } catch (error) {
          setError(error instanceof Error ? error.message : String(error))
        }
      }, [showGrid, t])

      const loadStencil = useCallback(async () => {
        const file = stencilPath.trim()
        if (!file) return
        setStencilError('')
        try {
          const result = await postJson(`${ROUTE}/op`, { action: 'stencils', file })
          setStencilMasters(result.masters || [])
          setStencilFile(result.file || file)
        } catch (error) {
          setStencilMasters([])
          setStencilError(error instanceof Error ? error.message : String(error))
        }
      }, [stencilPath])

      const insertMaster = useCallback((master) => {
        const current = docRef.current
        if (!current || !stencilFile) return
        const { w: pageW, h: pageH } = current.pageSize
        runOp({
          action: 'stencil_add',
          path: current.path,
          page: current.page,
          file: stencilFile,
          master: master.id,
          x: pageW / 2 - 1,
          y: pageH / 2 - 0.6,
        })
      }, [runOp, stencilFile])

      const removeShape = useCallback((options = {}) => {
        const current = docRef.current
        if (!current || !selectedRef.current) return
        if (options.confirm !== false && !window.confirm(t('deleteConfirm', { id: selectedRef.current }))) return
        runOp({ action: 'delete', path: current.path, page: current.page, shape_id: selectedRef.current })
      }, [runOp, t])

      useEffect(() => {
        const onKey = (event) => {
          const root = rootRef.current
          const active = document.activeElement
          if (root && event.target && !root.contains(event.target) && !root.contains(active)) return
          const tag = active ? active.tagName : ''
          const typing = tag === 'INPUT' || tag === 'TEXTAREA' || (active && active.isContentEditable)
          if (typing) return
          const key = String(event.key || '').toLowerCase()
          if ((event.ctrlKey || event.metaKey) && (key === 'z' || key === 'y')) {
            event.preventDefault()
            undoTo(key === 'y' || event.shiftKey ? 'redo' : 'undo')
            return
          }
          if (event.ctrlKey || event.metaKey || event.altKey) return
          if (key === 'delete' || key === 'backspace') {
            if (!selectedRef.current) return
            event.preventDefault()
            removeShape({ confirm: false })
            return
          }
          if (key === 'escape') {
            event.preventDefault()
            setSelected(null)
          }
        }
        window.addEventListener('keydown', onKey)
        return () => window.removeEventListener('keydown', onKey)
      }, [undoTo, removeShape])

      const useGuide = useCallback(async (direction) => {
        const current = docRef.current
        const id = selectedRef.current
        if (!current || !id) return
        setBusy(true)
        try {
          const probe = await postJson(`${ROUTE}/op`, {
            action: 'probe', path: current.path, page: current.page, shape_id: id, direction,
          })
          if (probe && probe.target) {
            await postJson(`${ROUTE}/op`, {
              action: 'connect', path: current.path, page: current.page,
              from: id, to: probe.target,
            })
            setNotice(t('connectedTo', { id: probe.target }))
          } else {
            const made = await postJson(`${ROUTE}/op`, {
              action: 'duplicate', path: current.path, page: current.page,
              shape_id: id, direction, connect: true,
            })
            setNotice(t('duplicatedAs', { id: made && made.shape_id ? made.shape_id : '' }))
          }
          const fresh = await runOp({
            action: 'render', path: current.path, page: current.page, selected: id,
          }, { quiet: true })
          if (fresh) setDoc(fresh)
        } catch (err) {
          setError(String(err && err.message ? err.message : err))
        } finally {
          setBusy(false)
        }
      }, [runOp, t])

      const connectTo = useCallback((targetId, label) => {
        const current = docRef.current
        if (!current || !selectedRef.current || !targetId) return
        runOp({ action: 'connect', path: current.path, page: current.page, from: selectedRef.current, to: targetId, label })
      }, [runOp])

      const setProp = useCallback((name, value) => {
        const current = docRef.current
        if (!current || !selectedRef.current) return
        runOp({ action: 'set_prop', path: current.path, page: current.page, shape_id: selectedRef.current, name, value })
      }, [runOp])

      const viewBox = doc ? `0 0 ${doc.pageSize.w} ${doc.pageSize.h}` : '0 0 1 1'

      const onCanvasClick = (event) => {
        const node = event.target instanceof Element ? event.target.closest('[data-shape-id]') : null
        if (node) {
          const id = node.getAttribute('data-shape-id')
          if (id) openSelected(id)
          return
        }
        setSelected(null)
      }

      const dragRef = useRef(null)

      const SNAP = 0.35           // inches; about one grid cell at 100% zoom

      const snapEdges = (bbox, shapes, id) => {
        const xs = []
        const ys = []
        for (const other of shapes) {
          if (other.id === id || other.connector || !other.bbox) continue
          const o = other.bbox
          xs.push(o.x, o.x + o.w, o.x + o.w / 2)
          ys.push(o.y, o.y + o.h, o.y + o.h / 2)
        }
        return { xs, ys }
      }

      const nearest = (value, list) => {
        let best = null
        let dist = SNAP
        for (const v of list) {
          const d = Math.abs(v - value)
          if (d <= dist) { best = v; dist = d }
        }
        return best
      }

      const moveDrag = (event) => {
        const drag = dragRef.current
        if (!drag) return
        const dxPx = event.clientX - drag.startX
        const dyPx = event.clientY - drag.startY
        if (!drag.moved && Math.abs(dxPx) + Math.abs(dyPx) < 3) return
        drag.moved = true
        drag.dx = dxPx / drag.scale
        drag.dy = dyPx / drag.scale
        // alignment snapping: edges and centre lines of the other shapes win
        if (!drag.isConn && drag.cands) {
          const b = drag.bbox
          const nx = b.x + drag.dx
          const ny = b.y - drag.dy
          const leftHit = nearest(nx, drag.cands.xs)
          const rightHit = nearest(nx + b.w, drag.cands.xs)
          const centreXHit = nearest(nx + b.w / 2, drag.cands.xs)
          if (leftHit !== null) drag.dx = leftHit - b.x
          else if (rightHit !== null) drag.dx = rightHit - b.w - b.x
          else if (centreXHit !== null) drag.dx = centreXHit - b.w / 2 - b.x
          const topHit = nearest(ny + b.h, drag.cands.ys)
          const bottomHit = nearest(ny, drag.cands.ys)
          const centreYHit = nearest(ny + b.h / 2, drag.cands.ys)
          if (topHit !== null) drag.dy = b.y + b.h - topHit
          else if (bottomHit !== null) drag.dy = b.y - bottomHit
          else if (centreYHit !== null) drag.dy = b.y + b.h / 2 - centreYHit
          drag.snapped = (leftHit !== null || rightHit !== null || centreXHit !== null
            || topHit !== null || bottomHit !== null || centreYHit !== null)
          drag.snapX = (leftHit !== null) ? leftHit : ((rightHit !== null) ? rightHit
            : ((centreXHit !== null) ? centreXHit : null))
          drag.snapY = (topHit !== null) ? topHit : ((bottomHit !== null) ? bottomHit
            : ((centreYHit !== null) ? centreYHit : null))
          // nothing aligned: fall back to the 0.25in grid, unless Alt is held
          if (!event.altKey) {
            if (drag.snapX === null) {
              const gx = Math.round((b.x + drag.dx) * 4) / 4
              if (Math.abs(gx - (b.x + drag.dx)) < 0.13) {
                drag.dx = gx - b.x
                drag.snapX = gx
              }
            }
            if (drag.snapY === null) {
              const gy = Math.round((b.y - drag.dy) * 4) / 4
              if (Math.abs(gy - (b.y - drag.dy)) < 0.13) {
                drag.dy = b.y - gy
                drag.snapY = gy
              }
            }
          }
          const svgEl = drag.svg
          if (svgEl) {
            const H = drag.pageH || 0
            const drawLine = (id, x1, y1, x2, y2) => {
              let el = svgEl.querySelector('#' + id)
              if (!el) {
                el = document.createElementNS('http://www.w3.org/2000/svg', 'line')
                el.setAttribute('id', id)
                el.setAttribute('stroke', '#E5484D')
                el.setAttribute('stroke-width', '1')
                el.setAttribute('vector-effect', 'non-scaling-stroke')
                el.setAttribute('stroke-dasharray', '4 3')
                el.setAttribute('pointer-events', 'none')
                svgEl.appendChild(el)
              }
              el.setAttribute('x1', x1.toFixed(4)); el.setAttribute('y1', y1.toFixed(4))
              el.setAttribute('x2', x2.toFixed(4)); el.setAttribute('y2', y2.toFixed(4))
              el.style.display = ''
            }
            if (drag.snapX !== null) drawLine('dshv-snap-x', drag.snapX, 0, drag.snapX, H)
            else { const e = svgEl.querySelector('#dshv-snap-x'); if (e) e.style.display = 'none' }
            if (drag.snapY !== null) drawLine('dshv-snap-y', 0, H - drag.snapY, drag.pageW, H - drag.snapY)
            else { const e = svgEl.querySelector('#dshv-snap-y'); if (e) e.style.display = 'none' }
          }
        }
        const label = drag.isConn && drag.textNode
        if (label) {
          drag.textNode.setAttribute('transform',
            `translate(${drag.dx.toFixed(4)} ${drag.dy.toFixed(4)})`)
        } else {
          drag.node.setAttribute('transform',
            `translate(${(drag.base.x + drag.dx).toFixed(4)} ${(drag.base.y + drag.dy).toFixed(4)})`)
          drag.node.style.opacity = '0.85'
        }
        const tip = tipRef.current
        if (tip && tip.parentElement) {
          const box = tip.parentElement.getBoundingClientRect()
          tip.style.display = 'block'
          tip.style.left = `${event.clientX - box.left + 14}px`
          tip.style.top = `${event.clientY - box.top - 30}px`
          const tipX = (drag.bbox.x + drag.dx).toFixed(3)
          const tipY = (drag.bbox.y - drag.dy).toFixed(3)
          tip.textContent = `X ${tipX}   Y ${tipY}${drag.snapped ? '   [snap]' : ''}`
        }
      }

      const upDrag = () => {
        const drag = dragRef.current
        dragRef.current = null
        window.removeEventListener('pointermove', moveDrag)
        window.removeEventListener('pointerup', upDrag)
        window.removeEventListener('pointercancel', upDrag)
        window.removeEventListener('blur', upDrag)
        if (tipRef.current) tipRef.current.style.display = 'none'
        const svgEl = drag && drag.svg
        if (svgEl) {
          for (const gid of ['dshv-snap-x', 'dshv-snap-y']) {
            const el = svgEl.querySelector('#' + gid)
            if (el) el.remove()
          }
        }
        if (!drag) return
        drag.node.style.opacity = ''
        if (!drag.moved) {
          drag.node.removeAttribute('transform')
          if (drag.textNode) drag.textNode.removeAttribute('transform')
          return
        }
        const current = docRef.current
        if (!current) return
        if (drag.isConn && drag.textNode) {
          runOp({
            action: 'move_label', path: current.path, page: current.page, shape_id: drag.id,
            dx: Math.round(drag.dx * 1000) / 1000, dy: Math.round(-drag.dy * 1000) / 1000,
          }, { quiet: true }).then((saved) => {
            if (drag.textNode) drag.textNode.removeAttribute('transform')
            return saved
          })
          return
        }
        const pageSize = current.pageSize || { w: 11, h: 8.5 }
        const x = Math.round(Math.min(Math.max(0, drag.bbox.x + drag.dx), Math.max(0, pageSize.w - drag.bbox.w)) * 1000) / 1000
        const y = Math.round(Math.min(Math.max(0, drag.bbox.y - drag.dy), Math.max(0, pageSize.h - drag.bbox.h)) * 1000) / 1000
        // The shape already sits where it was dropped: commit the box locally and
        // persist in the background, then reconcile the SVG once the file is saved.
        setDoc((prev) => (prev ? {
          ...prev,
          shapes: prev.shapes.map((item) => (item.id === drag.id ? { ...item, bbox: { ...item.bbox, x, y } } : item)),
        } : prev))
        runOp(
          { action: 'move', path: current.path, page: current.page, shape_id: drag.id, x, y, light: true },
          { quiet: true, light: true },
        ).then((saved) => {
          if (!saved) return undefined
          return postJson(`${ROUTE}/op`, {
            action: 'render', path: current.path, page: current.page, selected: drag.id,
          }).then((res) => {
            if (!res || !res.svg) return
            setDoc((prev) => (prev ? {
              ...prev,
              svg: res.svg,
              mtime: res.mtime ?? prev.mtime,
              canUndo: res.canUndo ?? prev.canUndo,
              canRedo: res.canRedo ?? prev.canRedo,
              saved: true,
            } : prev))
          })
        }).catch(() => {})
      }

      const onCanvasPointerDown = (event) => {
        if (event.button !== 0) return
        if (tool === 'hand') {
          const wrap = canvasBox.current
          if (!wrap) return
          event.preventDefault()
          panRef.current = { x: event.clientX, y: event.clientY, left: wrap.scrollLeft, top: wrap.scrollTop }
          const move = (e) => {
            const pan = panRef.current
            if (!pan) return
            wrap.scrollLeft = pan.left - (e.clientX - pan.x)
            wrap.scrollTop = pan.top - (e.clientY - pan.y)
          }
          const up = () => {
            panRef.current = null
            window.removeEventListener('pointermove', move)
            window.removeEventListener('pointerup', up)
          }
          window.addEventListener('pointermove', move)
          window.addEventListener('pointerup', up)
          return
        }
        const guide = event.target instanceof Element ? event.target.closest('[data-guide]') : null
        if (guide) {
          event.preventDefault()
          event.stopPropagation()
          useGuide(guide.getAttribute('data-guide'))
          return
        }
        const current = docRef.current
        const node = event.target instanceof Element ? event.target.closest('[data-shape-id]') : null
        if (!current || !node) return
        const id = node.getAttribute('data-shape-id')
        const target = current.shapes.find((item) => item.id === id)
        const svg = event.currentTarget.querySelector('svg')
        if (!target || !svg) return
        const box = svg.getBoundingClientRect()
        const viewWidth = svg.viewBox && svg.viewBox.baseVal ? svg.viewBox.baseVal.width : 0
        const scale = viewWidth > 0 && box.width > 0 ? box.width / viewWidth : 96
        event.preventDefault()
        const applied = node.getAttribute('transform') || ''
        const matched = /translate\(([-\d.]+)[ ,]+([-\d.]+)\)/.exec(applied)
        dragRef.current = {
          id, node, bbox: target.bbox,
          startX: event.clientX, startY: event.clientY,
          base: matched ? { x: Number(matched[1]), y: Number(matched[2]) } : { x: 0, y: 0 },
          scale, dx: 0, dy: 0, moved: false,
          isConn: !!target.connector,
          cands: target.connector ? null : snapEdges(target.bbox, current.shapes, id),
          svg: svg,
          pageH: current.pageSize ? current.pageSize.h : 0,
          pageW: current.pageSize ? current.pageSize.w : 0,
          onText: event.target instanceof Element && event.target.tagName.toLowerCase() === 'text',
          textNode: event.target instanceof Element && event.target.tagName.toLowerCase() === 'text' ? event.target : null,
        }
        window.addEventListener('pointermove', moveDrag)
        window.addEventListener('pointerup', upDrag)
        // A release outside the window (or an OS-level cancel) used to leave the
        // shape at 0.85 opacity, mid-transform, with a stale selection box.
        window.addEventListener('pointercancel', upDrag)
        window.addEventListener('blur', upDrag)
      }

      const ratio = doc ? doc.pageSize.h / doc.pageSize.w : 1
      const availW = pane.w > 0 ? pane.w - 40 : 0
      const availH = pane.h > 0 ? pane.h - 40 : 0
      const naturalW = doc ? Math.round(doc.pageSize.w * 96) : 0
      const fitW = availW > 80 ? availW : naturalW
      const fitH = availH > 80 && ratio > 0 ? Math.round(availH / ratio) : fitW
      const fitBox = doc ? Math.max(120, Math.round(Math.min(fitW, fitH, naturalW))) : 0
      const pageBox = Math.round(fitBox * (zoom ?? 1))
      const gridUnit = Math.max(6, Math.round(18 * (zoom ?? 1)))
      const gridSize = `${gridUnit}px ${gridUnit}px, ${gridUnit}px ${gridUnit}px, `
        + `${gridUnit * 4}px ${gridUnit * 4}px, ${gridUnit * 4}px ${gridUnit * 4}px`

      const pythonBroken = config && config.pythonOk === false
      const nothingOpen = !doc

      return h('div', { className: 'dshv-root', ref: rootRef },
        h('style', null, CSS),
        h('style', null, CSS_POLISH),
        h('div', { className: 'dshv-head' },
          h('div', { className: 'dshv-headText' },
            h('div', { className: 'dshv-title' }, doc ? doc.name : t('title')),
            h('div', { className: 'dshv-sub' },
              doc
                ? `${doc.path} · ${t('pageOf', { page: doc.page, total: doc.pageCount })} · ${t('shapesCount', { count: doc.shapes.length })}`
                : t('subtitle'))),
          h('div', { className: 'dshv-actions' },
            h('button', { type: 'button',
              className: `dshv-toggle${treeOpen ? ' on' : ''}`,
              title: t('toggleTree'),
              onClick: () => setTreeOpen((value) => !value),
            }, '☰'),
            h('button', { type: 'button',
              className: `dshv-toggle${inspectorOpen ? ' on' : ''}`,
              title: t('toggleInspector'),
              onClick: () => setInspectorOpen((value) => !value),
            }, '▤'),
            h(Btn, {
              variant: 'ghost',
              onClick: () => undoTo('undo'),
              title: t('undoHint'),
              disabled: busy || !(doc && doc.canUndo),
            }, `${String.fromCharCode(8630)} ${t('undo')}`),
            h(Btn, {
              variant: 'ghost',
              onClick: () => undoTo('redo'),
              title: t('redoHint'),
              disabled: busy || !(doc && doc.canRedo),
            }, `${String.fromCharCode(8631)} ${t('redo')}`),
            doc ? h(Btn, { variant: 'ghost', onClick: exportPng, title: t('exportPng'), disabled: busy }, t('export')) : null,
            h(Btn, {
              variant: 'ghost',
              onClick: () => loadFolder(folder || folderDraft),
              title: t('refresh'),
              disabled: !folder,
            }, t('refresh')),
            doc ? h(Btn, { variant: 'ghost', onClick: audit, title: t('validate') }, t('validate')) : null,
            doc ? h(Btn, {
              variant: 'ghost',
              title: t('fixUnitsTip'),
              onClick: () => runOp({ action: 'normalize', path: doc.path, page: doc.page }),
            }, t('fixUnits')) : null,
            h(Btn, { onClick: () => setCreateOpen(true), disabled: !folder && !config?.defaultFolder }, t('newFile')))),
        h('div', { className: 'dshv-body' },
          h('div', { className: 'dshv-pane dshv-left', style: treeOpen ? undefined : { display: 'none' } },
            h('div', { className: 'dshv-section' },
              h('div', { className: 'dshv-sectionTitle' }, t('folder')),
              h('div', { className: 'dshv-row' },
                h('input', {
                  className: 'dshv-input',
                  value: folderDraft,
                  spellCheck: false,
                  onChange: (e) => setFolderDraft(e.target.value),
                  onKeyDown: (e) => { if (e.key === 'Enter') loadFolder(e.currentTarget.value) },
                }),
                h(Btn, { small: true, onClick: chooseFolder, title: t('chooseFolder') }, '…'),
                h(Btn, { small: true, onClick: () => loadFolder(folderDraft), disabled: filesBusy }, t('openFile')))),
            h('div', { className: 'dshv-tabs' },
              h('button', { type: 'button', className: `dshv-tab${tab === 'shapes' ? ' active' : ''}`, onClick: () => setTab('shapes') }, t('shapes')),
              h('button', { type: 'button', className: `dshv-tab${tab === 'pages' ? ' active' : ''}`, onClick: () => setTab('pages') }, `${t('pages')}${doc && Array.isArray(doc.pages) ? ` (${doc.pages.length})` : ''}`)),
            tab === 'pages'
              ? h('div', { className: 'dshv-files' },
                  doc && Array.isArray(doc.pages) && doc.pages.length
                    ? doc.pages.map((page) => h('div', {
                        key: page.index,
                        className: `dshv-file${page.index === doc.page ? ' active' : ''}`,
                        onClick: () => openFile(doc.path, page.index),
                      },
                      h('div', { className: 'dshv-fileName' }, `${page.index}. ${page.name || t('page')}`),
                      h('div', { className: 'dshv-fileMeta' }, `${fmtInches(page.width)}×${fmtInches(page.height)}`)))
                    : h('div', { className: 'dshv-hint', style: { padding: 12 } }, t('noDocBody')))
              : h('div', { className: 'dshv-shapeList' },
                  doc
                    ? (doc.shapes.length
                        ? doc.shapes.map((item) => h('div', {
                            key: item.id,
                            className: `dshv-shapeRow${item.id === selected ? ' active' : ''}`,
                            onClick: () => openSelected(item.id),
                            title: `${shapeKindLabel(item, t)} #${item.id}`,
                          },
                          h('span', { className: 'dshv-shapeId' }, `#${item.id}`),
                          h('span', { className: 'dshv-shapeText' }, shapeTitle(item, t)),
                          h('span', { className: 'dshv-shapeKind' }, shapeKindLabel(item, t))))
                        : h('div', { className: 'dshv-hint', style: { padding: 12 } }, t('noShapes')))
                    : h('div', { className: 'dshv-hint', style: { padding: 12 } }, t('emptyFolder'))),
            h('div', { className: 'dshv-section', style: { marginTop: 'auto' } },
              h('div', { className: 'dshv-sectionTitle' }, t('files')),
              h('div', { className: 'dshv-files', style: { maxHeight: 180 } },
                filesBusy
                  ? h('div', { className: 'dshv-hint' }, t('refreshing'))
                  : files.length
                    ? files.map((file) => h('div', {
                        key: file.path,
                        className: `dshv-file${doc && doc.path === file.path ? ' active' : ''}`,
                        onClick: () => openFile(file.path, 1),
                        title: file.path,
                      },
                      h('div', { className: 'dshv-fileName' }, file.name),
                      h('div', { className: 'dshv-fileMeta' }, `${Math.max(1, Math.round(file.size / 1024))} KB`)))
                    : h('div', { className: 'dshv-hint' }, filesError || t('noFiles'))),
              h('div', { className: 'dshv-hint', style: { marginTop: 6 } }, t('readOnlyHint'))),
            h('div', { className: 'dshv-section' },
              h('div', { className: 'dshv-sectionTitle' }, t('tools')),
              h('div', { className: 'dshv-kinds' },
                SHAPE_KINDS.map((item) => h('button', { type: 'button',
                  key: item.kind,
                  className: 'dshv-kind',
                  title: isZh ? item.zh : item.en,
                  disabled: !doc,
                  onClick: () => addShape(item.kind),
                }, h('span', { className: 'dshv-kindGlyph' }, item.glyph), h('span', null, isZh ? item.zh : item.en))))),
            h('div', { className: 'dshv-section' },
              h('button', { type: 'button',
                className: 'dshv-sectionTitle dshv-fold',
                onClick: () => setStencilOpen((v) => !v),
              },
              h('span', { className: 'dshv-foldIcon' }, stencilOpen ? '\u25BE' : '\u25B8'),
              h('span', null, t('stencil'))),
              stencilOpen ? h('div', null,
              h('div', { className: 'dshv-row' },
                h('input', {
                  className: 'dshv-input',
                  placeholder: t('stencilPlaceholder'),
                  value: stencilPath,
                  onChange: (event) => setStencilPath(event.target.value),
                }),
                h(Btn, { small: true, disabled: !stencilPath.trim(), onClick: loadStencil }, t('load'))),
              stencilMasters.length
                ? h('div', { className: 'dshv-kinds', style: { marginTop: 8 } },
                    stencilMasters.map((master) => h('button', { type: 'button',
                      key: master.id,
                      className: 'dshv-kind',
                      title: `${master.name} (#${master.id})`,
                      disabled: !doc,
                      onClick: () => insertMaster(master),
                    }, h('span', { className: 'dshv-kindGlyph' }, '\u25C8'), h('span', null, master.name))))
                : h('div', { className: 'dshv-hint', style: { marginTop: 6 } }, t('stencilHint'))) : null)),

          h('div', { className: 'dshv-pane dshv-center' },
            nothingOpen
              ? h('div', { className: 'dshv-empty' },
                  h(Icon, { size: 40 }),
                  h('h2', null, t('noDocTitle')),
                  h('p', null, pythonBroken ? t('pythonMissing') : t('noDocBody')),
                  h('div', { className: 'dshv-row', style: { marginTop: 8 } },
                    h(Btn, { onClick: () => setCreateOpen(true), disabled: !folder && !config?.defaultFolder }, t('newFile')),
                    h(Btn, { variant: 'ghost', onClick: chooseFolder }, t('chooseFolder'))))
              : h('div', { className: 'dshv-canvasOuter' },
                  h('div', {
                    className: `dshv-canvasWrap${tool === 'hand' ? ' dshv-hand' : ''}`,
                    ref: canvasBox,
                    style: {
                      backgroundImage: showGrid ? [
                        'linear-gradient(to right, rgba(120,132,150,0.22) 1px, transparent 1px)',
                        'linear-gradient(to bottom, rgba(120,132,150,0.22) 1px, transparent 1px)',
                        'linear-gradient(to right, rgba(120,132,150,0.42) 1px, transparent 1px)',
                        'linear-gradient(to bottom, rgba(120,132,150,0.42) 1px, transparent 1px)',
                      ].join(',') : 'none',
                      backgroundSize: gridSize,
                    },
                  },
                    h('div', { className: 'dshv-canvasInner' },
                      h('div', { ref: pageRef, className: 'dshv-page', style: { aspectRatio: `${doc.pageSize.w} / ${doc.pageSize.h}`, width: `${pageBox}px` } },
                      h('div', {
                        className: 'dshv-svgHost',
                        onClick: onCanvasClick,
                        onPointerDown: onCanvasPointerDown,
                        dangerouslySetInnerHTML: { __html: withSelection(doc.svg, shape, doc.pageSize.h) },
                        style: { width: '100%', height: '100%' },
                      }),
                      ))),
                  h('div', { className: 'dshv-dragtip', ref: tipRef, style: { display: 'none' } }),
                  h('div', { className: 'dshv-zoom' },
                    h('button', { type: 'button', className: 'dshv-zbtn', title: t('zoomOut'), onClick: () => setZoom((v) => Math.max(0.15, Math.round((v ?? 1) * 0.8 * 1000) / 1000)) }, '\u2212'),
                    h('button', { type: 'button', className: 'dshv-zbtn dshv-zfit', title: t('zoomFit'), onClick: () => setZoom(null) }, zoom ? `${Math.round(zoom * 100)}%` : t('zoomFit')),
                    h('button', { type: 'button', className: 'dshv-zbtn', title: t('zoomIn'), onClick: () => setZoom((v) => Math.min(8, Math.round((v ?? 1) * 1.25 * 1000) / 1000)) }, '+'),
                    h('button', { type: 'button',
                      className: `dshv-zbtn${tool === 'hand' ? ' on' : ''}`,
                      title: t('handTool'),
                      onClick: () => setTool((v) => (v === 'hand' ? 'select' : 'hand')),
                    }, '\u270B'),
                    h('button', { type: 'button',
                      className: `dshv-zbtn${showGrid ? ' on' : ''}`,
                      title: t('gridToggle'),
                      onClick: () => setShowGrid((v) => !v),
                    }, '▦')))),

          h('div', { className: 'dshv-pane dshv-right', style: inspectorOpen ? undefined : { display: 'none' } },
            detail
              ? h(ShapeInspector, {
                  t,
                  doc,
                  shape,
                  detail,
                  onCommitText: commitText,
                  onCommitCell: commitCell,
                  onCommitMove: commitMove,
                  onSetProp: setProp,
                  onDelete: removeShape,
                  onConnect: connectTo,
                  onDeselect: () => setSelected(null),
                })
              : h('div', { className: 'dshv-empty', style: { padding: 24 } },
                  h('p', null, doc ? t('selectShape') : t('noDocBody'))))),

        h('div', { className: 'dshv-status' },
          busy ? h('span', { className: 'dshv-row' }, h('span', { className: 'dshv-spinner' }), t('busy')) : null,
          error ? h('span', { className: 'err' }, error) : null,
          !error && notice ? h('span', { className: 'ok' }, notice) : null,
          !error && !notice && !busy ? h('span', null, doc ? doc.path : t('preview')) : null,
          config && config.pythonOk === false ? h('span', { className: 'err' }, t('pythonMissing')) : null,
          configError ? h('span', { className: 'err' }, configError) : null,
          h('span', { className: 'dshv-grow' }),
          h('span', { className: 'dshv-ver', title: 'client build' }, 'v' + CLIENT_BUILD),
          doc ? h('span', { className: 'dshv-badge' }, t('autosave')) : null),

        createOpen
          ? h(CreateDialog, {
              t,
              initialFolder: folder || folderDraft || config?.defaultFolder || '',
              pickFolder,
              onCancel: () => setCreateOpen(false),
              onCreate: async (payload) => {
                const state = await runOp({ action: 'create', ...payload })
                if (state) {
                  setCreateOpen(false)
                  setFolder(state.folder)
                  setFolderDraft(state.folder)
                  await loadFolder(state.folder)
                }
              },
              error,
            })
          : null)
    }

    /* ------------------------------------------------------------ inspector */

    function ShapeInspector({ t, doc, shape, detail, onCommitText, onCommitCell, onCommitMove, onSetProp, onDelete, onConnect, onDeselect }) {
      const [text, setText] = useState(detail.text || '')
      const [propName, setPropName] = useState('')
      const [propValue, setPropValue] = useState('')
      const [connectTarget, setConnectTarget] = useState('')
      const [connectLabel, setConnectLabel] = useState('')
      const textTimer = useRef(null)
      const shapeId = detail.id

      useEffect(() => {
        setText(detail.text || '')
        setPropName('')
        setPropValue('')
        setConnectTarget('')
        setConnectLabel('')
      }, [shapeId])

      // Commit on blur only: a debounce used to fire mid-IME-composition and the
      // controlled textarea then dropped characters while the user was typing.
      const commitText = () => {
        if (text !== (detail.text || '')) onCommitText(text)
      }

      const bbox = shape?.bbox || { x: 0, y: 0, w: 0, h: 0 }
      const page = (doc && doc.pageSize) || { w: 11, h: 8.5 }
      const clampBox = (patch) => {
        const w = Math.min(Math.max(0.05, patch.w ?? bbox.w), page.w)
        const h = Math.min(Math.max(0.05, patch.h ?? bbox.h), page.h)
        return {
          w,
          h,
          x: Math.min(Math.max(0, patch.x ?? bbox.x), Math.max(0, page.w - w)),
          y: Math.min(Math.max(0, patch.y ?? bbox.y), Math.max(0, page.h - h)),
        }
      }
      const outOfPage = bbox.x < -0.001 || bbox.y < -0.001
        || bbox.x + bbox.w > page.w + 0.001 || bbox.y + bbox.h > page.h + 0.001
      const style = detail.style || {}
      const candidates = (doc.shapes || []).filter((item) => item.id !== shapeId && !item.connector)
      const props = Object.entries(detail.props || {})

      return h('div', null,
        h('div', { className: 'dshv-section' },
          h('div', { className: 'dshv-sectionTitle' },
            h('span', null, `${t('shape')} #${detail.id}`),
            h(Btn, { small: true, variant: 'ghost', onClick: onDeselect }, t('deselect'))),
          h('div', { className: 'dshv-hint' },
            [detail.master || (shape ? shapeKindLabel(shape, t) : ''),
             detail.type,
             shape && shape.connects && shape.connects.length ? `→ ${shape.connects.map((c) => '#' + c.to).join(', ')}` : '']
              .filter(Boolean).join(' · '))),

        h('div', { className: 'dshv-section' },
          h('div', { className: 'dshv-sectionTitle' }, t('text')),
          h('textarea', {
            className: 'dshv-input',
            rows: 3,
            value: text,
            placeholder: t('textPlaceholder'),
            onChange: (e) => setText(e.target.value),
            onBlur: commitText,
            onKeyDown: (e) => { if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) e.currentTarget.blur() },
          })),

        h('div', { className: 'dshv-section' },
          h('div', { className: 'dshv-sectionTitle' }, t('geometry')),
          h('div', { className: 'dshv-grid4' },
            h(NumberField, { label: t('x'), value: bbox.x, onCommit: (x) => onCommitMove(clampBox({ x })) }),
            h(NumberField, { label: t('y'), value: bbox.y, onCommit: (y) => onCommitMove(clampBox({ y })) }),
            h(NumberField, { label: t('width'), value: bbox.w, onCommit: (w) => onCommitMove(clampBox({ w })) }),
            h(NumberField, { label: t('height'), value: bbox.h, onCommit: (h) => onCommitMove(clampBox({ h })) })),
          outOfPage
            ? h('div', { className: 'dshv-warn' },
                h('span', null, t('outOfPage')),
                h(Btn, { small: true, variant: 'ghost', onClick: () => onCommitMove(clampBox({})) }, t('snapBack')))
            : null),

        h('div', { className: 'dshv-section' },
          h('div', { className: 'dshv-sectionTitle' }, t('style')),
          h('label', { className: 'dshv-check', title: t('textBgHint') },
            h('input', {
              type: 'checkbox',
              checked: Number(detail.cells && detail.cells.TextBkgnd ? detail.cells.TextBkgnd : 0) !== 0,
              onChange: (e) => onCommitCell({ TextBkgnd: e.target.checked ? 1 : 0 }),
            }),
            h('span', null, t('textBg'))),
          h(ColorField, { label: t('fill'), value: style.fill, onCommit: (v) => onCommitCell({ FillForegnd: v, FillBkgnd: v }) }),
          h(ColorField, { label: t('line'), value: style.line, onCommit: (v) => onCommitCell({ LineColor: v }) }),
          h(Field, { label: t('weight') },
            h('input', {
              className: 'dshv-input',
              type: 'number',
              step: 0.25,
              defaultValue: (() => {
                const weight = Number(style.weight)
                return Number.isFinite(weight) && weight > 0 ? Math.round(weight * 72 * 4) / 4 : 0.75
              })(),
              key: `${shapeId}-weight`,
              onBlur: (e) => {
                const pt = Number(e.target.value)
                if (Number.isFinite(pt) && pt >= 0) onCommitCell({ LineWeight: pt / 72 })
              },
              onKeyDown: (e) => { if (e.key === 'Enter') e.currentTarget.blur() },
            }))),

        h('div', { className: 'dshv-section' },
          h('div', { className: 'dshv-sectionTitle' }, t('shapeData')),
          props.length
            ? props.map(([name, value]) => h('div', { className: 'dshv-propRow', key: name },
                h('span', { className: 'dshv-propName', title: name }, name),
                h('input', {
                  className: 'dshv-input',
                  defaultValue: value,
                  onBlur: (e) => { if (e.target.value !== value) onSetProp(name, e.target.value) },
                  onKeyDown: (e) => { if (e.key === 'Enter') e.currentTarget.blur() },
                })))
            : h('div', { className: 'dshv-hint' }, '—'),
          h('div', { className: 'dshv-propRow', style: { marginTop: 6 } },
            h('input', { className: 'dshv-input', placeholder: t('propName'), value: propName, onChange: (e) => setPropName(e.target.value) }),
            h('input', { className: 'dshv-input', placeholder: t('propValue'), value: propValue, onChange: (e) => setPropValue(e.target.value) }),
            h(Btn, {
              small: true,
              disabled: !propName.trim(),
              onClick: () => {
                onSetProp(propName.trim(), propValue)
                setPropName('')
                setPropValue('')
              },
            }, t('addProp')))),

        h('div', { className: 'dshv-section' },
          h('div', { className: 'dshv-sectionTitle' }, t('connectTo')),
          h('div', { className: 'dshv-row' },
            h('select', {
              className: 'dshv-input',
              value: connectTarget,
              onChange: (e) => setConnectTarget(e.target.value),
            },
            h('option', { value: '' }, '—'),
            candidates.map((item) => h('option', { key: item.id, value: item.id }, `#${item.id} ${shapeTitle(item, t)}`))),
            h(Btn, { small: true, disabled: !connectTarget, onClick: () => onConnect(connectTarget, connectLabel) }, t('connect'))),
          h('input', {
            className: 'dshv-input',
            style: { marginTop: 6 },
            placeholder: t('connectLabel'),
            value: connectLabel,
            onChange: (e) => setConnectLabel(e.target.value),
          })),

        h('div', { className: 'dshv-section' },
          h(Btn, { variant: 'danger', onClick: onDelete }, t('deleteShape'))))
    }

    /* --------------------------------------------------------------- dialog */

    function CreateDialog({ t, initialFolder, pickFolder, onCancel, onCreate, error }) {
      const [name, setName] = useState('drawing')
      const [sizeId, setSizeId] = useState('a4l')
      const [customW, setCustomW] = useState('11')
      const [customH, setCustomH] = useState('8.5')
      const [title, setTitle] = useState('')
      const [folder, setFolder] = useState(initialFolder || '')
      const [busy, setBusy] = useState(false)

      const submit = async () => {
        const preset = SIZES.find((item) => item.id === sizeId)
        const width = preset ? preset.w : Number(customW)
        const height = preset ? preset.h : Number(customH)
        if (!Number.isFinite(width) || !Number.isFinite(height) || width <= 0 || height <= 0) return
        setBusy(true)
        try {
          await onCreate({ dir: folder, name: name.trim() || 'drawing', width, height, title: title.trim() })
        } finally {
          setBusy(false)
        }
      }

      return h('div', { className: 'dshv-overlayDialog', onMouseDown: (e) => { if (e.target === e.currentTarget) onCancel() } },
        h('div', { className: 'dshv-dialog' },
          h('h3', null, t('createTitle')),
          h(Field, { label: t('createName') },
            h('input', { className: 'dshv-input', value: name, onChange: (e) => setName(e.target.value), autoFocus: true })),
          h('div', { className: 'dshv-hint', style: { margin: '-2px 0 8px 82px' } }, t('createNameHint')),
          h(Field, { label: t('createPage') },
            h('select', { className: 'dshv-input', value: sizeId, onChange: (e) => setSizeId(e.target.value) },
              SIZES.map((item) => h('option', { key: item.id, value: item.id }, t(item.label))),
              h('option', { value: 'custom' }, t('createCustom')))),
          sizeId === 'custom'
            ? h('div', { className: 'dshv-row', style: { marginLeft: 82, marginBottom: 6 } },
                h('input', { className: 'dshv-input', type: 'number', value: customW, onChange: (e) => setCustomW(e.target.value) }),
                h('span', { className: 'dshv-hint' }, '×'),
                h('input', { className: 'dshv-input', type: 'number', value: customH, onChange: (e) => setCustomH(e.target.value) }))
            : null,
          h(Field, { label: t('createTitleField') },
            h('input', { className: 'dshv-input', value: title, onChange: (e) => setTitle(e.target.value) })),
          h('div', { className: 'dshv-hint', style: { margin: '-2px 0 8px 82px' } }, t('createTitleHint')),
          h(Field, { label: t('createIn') },
            h('input', { className: 'dshv-input', value: folder, onChange: (e) => setFolder(e.target.value) }),
            h(Btn, {
              small: true,
              onClick: async () => {
                const picked = await pickFolder()
                if (picked) setFolder(picked)
              },
            }, '…')),
          error ? h('div', { className: 'dshv-hint', style: { color: 'var(--dsw-alias-state-error-primary)', marginTop: 8 } }, error) : null,
          h('div', { className: 'dshv-dialogActions' },
            h(Btn, { variant: 'ghost', onClick: onCancel }, t('cancel')),
            h(Btn, { variant: 'primary', disabled: busy || !folder, onClick: submit }, t('create')))))
    }

    /* ------------------------------------------------------------------ css */

    const FLOAT_GEOM = 'dsh-visio.float.geom.v2'

    const CSS_FLOAT = `
.dshv-fab{pointer-events:auto;position:fixed;right:20px;bottom:20px;z-index:2147482000;display:flex;align-items:center;gap:6px;
  padding:8px 13px;border-radius:999px;background:var(--dsw-alias-bg-overlay);color:var(--dsw-alias-label-primary);
  border:1px solid var(--dsw-alias-border-l2);box-shadow:0 8px 22px rgba(0,0,0,.18);cursor:pointer;font-size:12px;
  font-weight:600;font-family:inherit;user-select:none}
.dshv-fab:hover{border-color:var(--dsw-alias-brand-primary)}
.dshv-fab.active{background:var(--dsw-alias-brand-primary);color:#fff;border-color:transparent}
.dshv-float{pointer-events:auto;position:fixed;z-index:2147482100;display:flex;flex-direction:column;background:var(--dsw-alias-bg-base);
  border:1px solid var(--dsw-alias-border-l2);border-radius:12px;overflow:hidden;
  box-shadow:0 24px 60px rgba(0,0,0,.26), 0 2px 8px rgba(0,0,0,.12)}
.dshv-floatBar{height:34px;flex:0 0 34px;display:flex;align-items:center;justify-content:space-between;gap:8px;
  padding:0 6px 0 12px;background:var(--dsw-alias-bg-layer-2);border-bottom:1px solid var(--dsw-alias-border-l1);
  cursor:move;user-select:none;touch-action:none}
.dshv-floatTitle{font-size:12px;font-weight:600;color:var(--dsw-alias-label-primary);overflow:hidden;white-space:nowrap;text-overflow:ellipsis}
.dshv-floatClose{width:24px;height:24px;border:0;border-radius:6px;background:transparent;color:var(--dsw-alias-label-secondary);
  font-size:16px;line-height:1;cursor:pointer}
.dshv-floatClose:hover{background:var(--dsw-alias-bg-layer-1);color:var(--dsw-alias-label-primary)}
.dshv-floatBody{flex:1;min-height:0;overflow:hidden;display:flex}
.dshv-floatBody > .dshv-root{flex:1;min-width:0;height:100%}
.dshv-floatMove{position:absolute;left:6px;top:50%;transform:translateY(-50%);width:14px;height:44px;
  display:flex;align-items:center;justify-content:center;flex-direction:column;gap:2px;font-size:9px;line-height:1;
  color:var(--dsw-alias-label-secondary);opacity:.55;cursor:move;user-select:none;touch-action:none;border-radius:6px}
.dshv-floatMove:hover{opacity:1;background:var(--dsw-alias-bg-layer-1)}
.dshv-floatGrip{position:absolute;right:0;bottom:0;width:18px;height:18px;cursor:nwse-resize;touch-action:none;
  background:linear-gradient(135deg, transparent 50%, var(--dsw-alias-border-l2) 50%)}
.dshv-svgHost [data-shape-id]{cursor:move}
.dshv-hand .dshv-svgHost [data-shape-id],.dshv-hand .dshv-svgHost{cursor:grab}
.dshv-zoom{position:absolute;right:14px;bottom:14px;display:flex;gap:4px;padding:4px;border-radius:9px;
  background:var(--dsw-alias-bg-overlay);border:1px solid var(--dsw-alias-border-l2);box-shadow:0 4px 14px rgba(0,0,0,.16);z-index:5}
.dshv-zbtn{min-width:28px;height:26px;padding:0 8px;border:0;border-radius:6px;background:transparent;cursor:pointer;
  color:var(--dsw-alias-label-primary);font-size:12px;font-family:inherit}
.dshv-zbtn:hover{background:var(--dsw-alias-bg-layer-1)}
.dshv-zbtn.on{background:var(--dsw-alias-brand-primary);color:#fff}
.dshv-zfit{min-width:52px}
.dshv-kinds{display:grid;grid-template-columns:repeat(3,1fr);gap:5px;margin-top:6px}
.dshv-fold{display:flex;align-items:center;gap:5px;width:100%;border:none;background:none;padding:0;cursor:pointer;font-family:inherit;text-align:left}
.dshv-foldIcon{font-size:9px;color:var(--dsw-alias-label-secondary)}
.dshv-kind{display:flex;flex-direction:column;align-items:center;gap:2px;padding:6px 2px;border-radius:7px;
  border:1px solid var(--dsw-alias-border-l1);background:var(--dsw-alias-bg-base);cursor:pointer;
  color:var(--dsw-alias-label-secondary);font-size:10.5px;font-family:inherit;line-height:1.1}
.dshv-kind:hover:not(:disabled){border-color:var(--dsw-alias-brand-primary);color:var(--dsw-alias-label-primary)}
.dshv-kind:disabled{opacity:.45;cursor:default}
.dshv-kindGlyph{font-size:15px;line-height:1;color:var(--dsw-alias-label-primary)}
.dshv-dragtip{position:absolute;pointer-events:none;z-index:6;padding:3px 8px;border-radius:6px;
  background:var(--dsw-alias-bg-overlay);border:1px solid var(--dsw-alias-border-l2);font-size:11px;
  color:var(--dsw-alias-label-primary);box-shadow:0 2px 8px rgba(0,0,0,.16);white-space:nowrap}
.dshv-toggle{width:26px;height:26px;border-radius:6px;border:1px solid var(--dsw-alias-border-l1);background:transparent;
  color:var(--dsw-alias-label-secondary);cursor:pointer;font-size:13px;line-height:1;padding:0}
.dshv-toggle.on{color:var(--dsw-alias-label-primary);background:var(--dsw-alias-bg-layer-1)}
`

    const FAB_POS = 'dsh-visio.fab.pos.v1'

    function FloatingVisio(props) {
      const { t } = props
      const [open, setOpen] = useState(false)
      // the launcher itself is draggable; a drag must not toggle the window
      const [fab, setFab] = useState(() => {
        try {
          const saved = JSON.parse(window.localStorage.getItem(FAB_POS) || 'null')
          if (saved && Number.isFinite(saved.x) && Number.isFinite(saved.y)) return saved
        } catch (err) { /* ignore */ }
        return null
      })
      const fabRef = useRef(fab)
      const moveFab = (next) => {
        fabRef.current = next
        setFab(next)
        try { window.localStorage.setItem(FAB_POS, JSON.stringify(next)) } catch (err) { /* ignore */ }
      }
      const startFabDrag = (event) => {
        if (event.button !== 0) return
        const start = { x: event.clientX, y: event.clientY, fab: fabRef.current, moved: false }
        const move = (e) => {
          const dx = e.clientX - start.x
          const dy = e.clientY - start.y
          if (!start.moved && Math.abs(dx) + Math.abs(dy) < 4) return
          start.moved = true
          const vw = window.innerWidth || 1280
          const vh = window.innerHeight || 800
          const w = 96
          const h = 34
          moveFab({
            x: Math.min(Math.max(8, (start.fab ? start.fab.x : vw - w - 20) + dx), vw - w - 8),
            y: Math.min(Math.max(8, (start.fab ? start.fab.y : vh - h - 20) + dy), vh - h - 8),
          })
        }
        const up = () => {
          window.removeEventListener('pointermove', move)
          window.removeEventListener('pointerup', up)
          if (!start.moved) setOpen((value) => !value)
        }
        window.addEventListener('pointermove', move)
        window.addEventListener('pointerup', up)
      }
      const [geom, setGeom] = useState(() => {
        let saved = null
        try { saved = JSON.parse(window.localStorage.getItem(FLOAT_GEOM) || 'null') } catch (err) { saved = null }
        if (saved && Number(saved.w) >= 360 && Number(saved.h) >= 280) return saved
        const vw = window.innerWidth || 1280
        const vh = window.innerHeight || 800
        const w = Math.min(1280, Math.max(620, Math.round(vw * 0.66)))
        const h = Math.min(840, Math.max(460, Math.round(vh * 0.82)))
        return { x: Math.max(16, vw - w - 24), y: 72, w, h }
      })
      const geomRef = useRef(geom)
      const remember = (next) => {
        geomRef.current = next
        setGeom(next)
        try { window.localStorage.setItem(FLOAT_GEOM, JSON.stringify(next)) } catch (err) { /* ignore */ }
      }
      const track = (event, build) => {
        if (event.button !== 0) return
        event.preventDefault()
        event.stopPropagation()
        const start = { x: event.clientX, y: event.clientY, geom: geomRef.current }
        const move = (e) => remember(build(start, e))
        const up = () => {
          window.removeEventListener('pointermove', move)
          window.removeEventListener('pointerup', up)
        }
        window.addEventListener('pointermove', move)
        window.addEventListener('pointerup', up)
      }
      const [restoreGeom, setRestoreGeom] = useState(null)
      const maximize = () => {
        const vw = window.innerWidth || 1280
        const vh = window.innerHeight || 800
        if (!restoreGeom) {
          setRestoreGeom(geomRef.current)
          remember({ x: 18, y: 18, w: vw - 36, h: vh - 36 })
        } else {
          remember(restoreGeom)
          setRestoreGeom(null)
        }
      }
      const startDrag = (event) => track(event, (start, e) => ({
        ...start.geom,
        x: Math.min(Math.max(120 - start.geom.w, start.geom.x + e.clientX - start.x), window.innerWidth - 160),
        y: Math.min(Math.max(0, start.geom.y + e.clientY - start.y), window.innerHeight - 90),
      }))
      const startResize = (event) => track(event, (start, e) => ({
        ...start.geom,
        w: Math.max(460, Math.min(window.innerWidth - 16, start.geom.w + e.clientX - start.x)),
        h: Math.max(340, Math.min(window.innerHeight - 16, start.geom.h + e.clientY - start.y)),
      }))

      return h(React.Fragment, null,
        h('style', null, CSS_FLOAT),
        h('div', {
          className: `dshv-fab${open ? ' active' : ''}`,
          title: t('floatTip'),
          style: fab ? { left: fab.x, top: fab.y, right: 'auto', bottom: 'auto' } : undefined,
          onPointerDown: startFabDrag,
        }, h(Icon, { size: 15 }), h('span', null, t('nav'))),
        open
          ? h('div', { className: 'dshv-float', style: { left: geom.x, top: geom.y, width: geom.w, height: geom.h } },
              h('div', { className: 'dshv-floatBar', onPointerDown: startDrag, onDoubleClick: maximize },
                h('span', { className: 'dshv-floatTitle' }, t('floatTitle')),
                h('button', { type: 'button',
                  className: 'dshv-floatClose',
                  title: t('floatClose'),
                  onClick: (event) => { event.stopPropagation(); setOpen(false) },
                }, '\u00d7')),
              h('div', { className: 'dshv-floatBody' }, h(VisioPanel, props)),
              h('div', { className: 'dshv-floatMove', title: t('floatMove'), onPointerDown: startDrag },
                '\u22ee\u22ee'),
              h('div', { className: 'dshv-floatGrip', onPointerDown: startResize }))
          : null)
    }

    return {

      inject: ['slots', 'locale'],
      apply(ctx) {
        ctx.effect(() => ctx.locale.register(NS, { zh, en }), `${NS}: dictionaries`)
        const t = ctx.locale.bind(NS)

        const pickFolder = async () => {
          const uiWorkspace = ctx.get('uiWorkspace')
          if (uiWorkspace && typeof uiWorkspace.pickDirectory === 'function') {
            return await uiWorkspace.pickDirectory()
          }
          return null
        }

        ctx.slots.inject('main', () => ctx.slots.inject('sidebar.panellist', () => {
          const stopMain = ctx.slots.register({
            name: 'main',
            key: PANEL_ID,
            locale: NS,
            inject: () => ({ t, pickFolder }),
          }, VisioPanel)
          let stopIcon
          try {
            stopIcon = ctx.slots.register({
              name: 'sidebar.panellist',
              id: PANEL_ID,
              order: 33,
              label: () => t('nav'),
              locale: NS,
            }, VisioIcon)
          } catch (error) {
            stopMain?.()
            throw error
          }
          return () => {
            stopIcon?.()
            stopMain?.()
          }
        }))

        ctx.slots.inject('shell.overlay', () => ctx.slots.register({
          name: 'shell.overlay',
          id: 'dsh-visio-float',
          order: 40,
          locale: NS,
          inject: () => ({ t, pickFolder }),
        }, FloatingVisio))
      },
    }
  },
})
