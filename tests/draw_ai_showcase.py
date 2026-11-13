# -*- coding: utf-8 -*-
"""Draw a professional 4-lane process map using ONLY the visio agent actions.

This is exactly the path an LLM takes: capabilities -> shape_list -> add_shape
-> connect -> align -> audit_full -> snapshot(review=true). No direct XML.
"""
import sys, io, os
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.path.insert(0, 'engine')
import visio_bridge as vb, blank_doc

P = os.path.abspath('tests/_out/showcase.vsdx')
OUT = os.path.abspath('tests/_out')
os.makedirs(OUT, exist_ok=True)
blank_doc.create(P, 16.54, 11.69, 'AI Showcase', 't')

def act(**kw):
    kw['path'] = P
    return vb.handle(kw)

def open_state():
    return vb.handle({'action': 'open', 'path': P})

def shape(x, y, w, h, kind, text='', **style):
    r = act(action='add_shape', x=x, y=y, w=w, h=h, kind=kind, text=text, **style)
    return r

def ids_after(n):
    return [s['id'] for s in open_state()['shapes']]

# 0. contract + library (what the model should do first)
g = vb.handle({'action': 'guide'})
lib = vb.handle({'action': 'shape_list'})
print('contract actions:', len(g['order']), '| library shapes:', lib['count'])

# 1. title / divider / version tag  (text shapes)
shape(0.85, 11.05, 9.5, 0.5, 'text', '外发插件审核与放行流程', font_size=24, font_color='#1B2A41', bold=True)
shape(0.85, 10.60, 13.0, 0.32, 'text', '示意图 V1.0  |  需求受理 → 库与 CDB 同步交付 → SVD 单出 → 插件验证 → 内部放行', font_size=11, font_color='#5A6B80')
shape(13.6, 11.05, 2.2, 0.32, 'text', '示意图  V1.0', font_size=11, font_color='#C55A1F', bold=True)
shape(0.6, 10.44, 15.35, 0.025, 'rect', '', fill='#B9C9DE', line='#B9C9DE')

# 2. four swimlane bands (light fills, library presets)
shape(0.6, 8.74, 15.35, 1.55, 'lane')
shape(0.6, 6.67, 15.35, 1.93, 'lane_warm')
shape(0.6, 4.19, 15.35, 2.34, 'lane_warm')
shape(0.6, 1.09, 15.35, 2.96, 'lane_green')
shape(0.85, 9.95, 4.2, 0.3, 'text', '需求与计划', font_size=13, font_color='#1B2A41', bold=True)
shape(3.6, 9.95, 6.0, 0.28, 'text', '| 市场需求端 · 市场 PM · 库制作人', font_size=9, font_color='#5A6B80')
shape(0.85, 8.28, 4.6, 0.3, 'text', 'MCU 库与 CDB（同步交付）', font_size=13, font_color='#1B2A41', bold=True)
shape(5.2, 8.28, 6.0, 0.28, 'text', '| 库制作人 · 库源数据审核人', font_size=9, font_color='#5A6B80')
shape(0.85, 6.21, 4.8, 0.3, 'text', 'SVD（依赖最新 H，单独交付）', font_size=13, font_color='#1B2A41', bold=True)
shape(5.6, 6.21, 6.0, 0.28, 'text', '| SVD 制作人 · SVD 审核人', font_size=9, font_color='#5A6B80')
shape(0.85, 3.73, 4.8, 0.3, 'text', '插件、验证与内部放行', font_size=13, font_color='#1B2A41', bold=True)
shape(5.2, 3.73, 6.0, 0.28, 'text', '| 烧录工具制作人 · 功能验证人 · 市场 PM', font_size=9, font_color='#5A6B80')

# 3. nodes (library presets: deep-blue step, orange gate, green release)
shape(0.85, 9.02, 2.15, 0.92, 'step', '市场需求提出' + '\n' + '需求端')
shape(3.55, 9.02, 2.45, 0.92, 'step', '需求确认与范围冻结' + '\n' + '型号 / 封装 / 版本 / 交期')
shape(6.55, 9.02, 2.45, 0.92, 'step', '交付计划与验收口径' + '\n' + '范围 / 里程碑 / 双方接口')
shape(9.5, 9.45, 5.9, 0.28, 'text', '输出：书面需求单、交付计划、验收口径与里程碑；', font_size=10, font_color='#5A6B80', text_bg=True)
shape(9.5, 9.10, 5.9, 0.28, 'text', '任一要素未书面确认，不进入制作。', font_size=10, font_color='#5A6B80')

shape(0.85, 7.05, 2.25, 0.92, 'step', 'MCU 库制作' + '\n' + '独立外发库 / 库制作人')
shape(3.55, 7.05, 2.25, 0.92, 'step', '库源数据审核' + '\n' + '库配置 / 容量映射 / 封装')
shape(6.35, 6.90, 1.35, 1.25, 'gate', '门 A' + '\n' + '通过?')
shape(8.15, 7.05, 2.55, 0.92, 'release', 'MCU 库 + CDB 冻结' + '\n' + '同步交付 / 版本号 / SHA-256')
shape(11.0, 7.55, 4.6, 0.28, 'text', '输出：MCU 库 + CDB 同步交付、', font_size=10, font_color='#5A6B80')
shape(11.0, 7.20, 4.6, 0.28, 'text', '源数据验证报告（含 SHA-256）', font_size=10, font_color='#5A6B80')

shape(0.85, 4.90, 2.05, 0.92, 'rect', '最新 H 文件' + '\n' + '需方提供 / 版本确认', fill='#EEF2F8', line='#D8E2EF', font_color='#1B2A41')
shape(3.35, 4.90, 2.25, 0.92, 'step', 'H 核对' + '\n' + '与 MCU 库配置逐项核对')
shape(6.05, 4.90, 2.55, 0.92, 'step', 'SVD 制作（阶段 0-3）' + '\n' + 'TRM/Excel → SVD + 11 项检查')
shape(9.05, 4.90, 2.25, 0.92, 'step', '阶段 4 裁剪/派生' + '\n' + '母体 → 新型号')
shape(11.75, 4.73, 1.35, 1.25, 'gate', '门 4' + '\n' + '通过?')
shape(13.45, 4.90, 2.15, 0.92, 'release', 'SVD 冻结' + '\n' + '版本 / 报告 / SHA-256')

shape(0.85, 1.60, 2.25, 0.92, 'step', '整套工具整理' + '\n' + '库 / SVD / CDB / Demo')
shape(3.55, 1.60, 2.25, 0.92, 'step', '插件打包' + '\n' + '烧录工具制作人')
shape(6.25, 1.60, 2.25, 0.92, 'step', '插件功能验证' + '\n' + '场景复现 / 记录 / 回归')
shape(9.15, 1.43, 1.35, 1.25, 'gate', '门 F' + '\n' + '通过?')
shape(10.95, 1.60, 2.45, 0.92, 'release', '证据归档' + '\n' + '内部放行 / 市场 PM')

# 4. legend / footer
shape(0.6, 0.42, 15.35, 0.025, 'rect', '', fill='#B9C9DE', line='#B9C9DE')
shape(0.85, 0.06, 0.9, 0.28, 'text', '图例', font_size=10, font_color='#1B2A41', bold=True)
shape(1.75, 0.11, 0.5, 0.10, 'rect', '', fill='#17365D', line='#17365D')
shape(2.35, 0.04, 1.5, 0.26, 'text', '正常流转', font_size=9, font_color='#5A6B80')
shape(4.0, 0.11, 0.5, 0.10, 'rect', '', fill='#B03A2E', line='#B03A2E')
shape(4.6, 0.04, 1.5, 0.26, 'text', '退回 / 返工', font_size=9, font_color='#5A6B80')
shape(6.3, 0.02, 0.32, 0.28, 'gate', '')
shape(6.75, 0.04, 3.2, 0.26, 'text', '确认门：未通过不得推进', font_size=9, font_color='#5A6B80')
shape(10.4, 0.04, 5.5, 0.26, 'text', '库与 CDB 同步交付；SVD 依赖最新 H、单独交付。', font_size=9, font_color='#5A6B80')

# 5. connect using ids resolved from open()
ids = [s['id'] for s in open_state()['shapes']]
print('total shapes before connectors:', len(ids))
def connect(a, b, label):
    r = act(action='connect', **{'from': str(a), 'to': str(b), 'label': label,
                                'line_width': 0.02, 'line_color': '#17365D'})
    return r['ok']

# chain rows (ids are sequential; first 4 are title/divider/version/divider...)
# resolve by text to be safe
def by_text(t):
    for s in open_state()['shapes']:
        if (s.get('text') or '').split('\n')[0] == t:
            return s['id']
    return None

pairs = [
 ('市场需求提出','需求确认与范围冻结',''), ('需求确认与范围冻结','交付计划与验收口径',''),
 ('MCU 库制作','库源数据审核',''), ('库源数据审核','门 A',''), ('门 A','MCU 库 + CDB 冻结','通过'),
 ('最新 H 文件','H 核对',''), ('H 核对','SVD 制作（阶段 0-3）',''),
 ('SVD 制作（阶段 0-3）','阶段 4 裁剪/派生',''), ('阶段 4 裁剪/派生','门 4',''),
 ('门 4','SVD 冻结','通过'),
 ('整套工具整理','插件打包',''), ('插件打包','插件功能验证',''),
 ('插件功能验证','门 F',''), ('门 F','证据归档','通过'),
]
ok = 0
for a,b,l in pairs:
    ia,ib = by_text(a), by_text(b)
    if ia and ib:
        try: ok += bool(connect(ia, ib, l))
        except Exception as ex: print('connect fail', a, b, str(ex)[:80])
    else: print('missing', a, ia, b, ib)
print('connectors:', ok, '/', len(pairs))

# 5b. cross-lane + rework links.  Every point list starts and ends on the
# real edge midpoint of its two shapes, with only H/V waypoints in between.
# connect_styled draws EXACTLY these points (no auto-routing), so no diagonals.
def styled(a, b, label, points, color, dashed=False):
    ia, ib = by_text(a), by_text(b)
    if not (ia and ib):
        print('missing for styled', a, ia, b, ib)
        return False
    r = act(action='connect_styled', **{'from': str(ia), 'to': str(ib), 'label': label,
                                       'points': points, 'line_color': color,
                                       'line_pattern': 2 if dashed else 1, 'text_bg': True,
                                       'line_width': 0.018})
    return r.get('ok')

# --- green cross-lane deliveries (top edge midpoint -> target top/bottom) ---
# CDB frozen (8.15..10.70, y 7.05..7.97) down to latest H (0.85..2.90, y 4.90..5.82)
styled('MCU 库 + CDB 冻结', '最新 H 文件', '交付后等待最新 H',
       [(9.42, 7.05), (9.42, 6.62), (1.87, 6.62), (1.87, 5.82)], '#2F6B4F')
# SVD frozen (13.45..15.60, 4.90..5.82) down to tool packaging (0.85..3.10, 1.60..2.52)
styled('SVD 冻结', '整套工具整理', 'SVD 冻结 → 整套工具整理',
       [(14.52, 4.90), (14.52, 4.12), (1.97, 4.12), (1.97, 2.52)], '#2F6B4F')

# --- red dashed rework returns ---
# gate A (6.35..7.70, 6.90..8.15) back to MCU library production
styled('门 A', 'MCU 库制作', '不通过：退回制作',
       [(7.02, 6.90), (7.02, 6.62), (1.97, 6.62), (1.97, 7.05)], '#B03A2E', dashed=True)
# gate 4 (11.75..13.10, 4.73..5.98) back to trimming (9.05..11.30, 4.90..5.82)
styled('门 4', '阶段 4 裁剪/派生', 'NG：重新裁剪',
       [(12.42, 4.73), (12.42, 4.50), (10.17, 4.50), (10.17, 4.90)], '#B03A2E', dashed=True)
# gate F (9.15..10.50, 1.43..2.68) back to packaging (3.55..5.80, 1.60..2.52)
styled('门 F', '插件打包', '缺陷退回：重新打包',
       [(9.82, 1.43), (9.82, 1.25), (4.67, 1.25), (4.67, 1.60)], '#B03A2E', dashed=True)

# --- slate spot-check: requirements down to trimming, right margin corridor ---
styled('交付计划与验收口径', '阶段 4 裁剪/派生', '抽查',
       [(7.77, 9.02), (7.77, 8.62), (15.82, 8.62), (15.82, 6.62),
        (10.17, 6.62), (10.17, 5.82)], '#5B6B7A')

# 6. check stage
audit = act(action='audit_full')
print('audit:', audit['counts'])
snap = vb.handle({'action': 'snapshot', 'path': P, 'out': OUT, 'dpi': 130, 'review': True})
print('png:', snap['files'])
print('DONE')
