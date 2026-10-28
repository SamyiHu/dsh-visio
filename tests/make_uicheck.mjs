// Build a static replica of the inspector row so the layout can be measured in a real browser.
import { readFileSync, writeFileSync } from 'node:fs'

const here = new URL('.', import.meta.url)
const src = readFileSync(new URL('../client.js', here), 'utf8')
const order = ['CSS', 'CSS_POLISH', 'CSS_FLOAT']
const blocks = order.map((name) => {
  const marker = 'const ' + name + ' = `'
  const start = src.indexOf(marker)
  if (start < 0) return ''
  const from = start + marker.length
  const end = src.indexOf('`', from)
  return end < 0 ? '' : src.slice(from, end)
})
if (!blocks.filter(Boolean).length) throw new Error('no css blocks found')

const html = `<!doctype html><meta charset="utf-8">
<style>${blocks.join('\n')}
html,body{margin:0;background:#fff;font:13px system-ui,sans-serif}
.frame{width:308px;padding:12px;box-sizing:border-box}
</style>
<div class="frame">
  <div class="dshv-section">
    <div class="dshv-sectionTitle">位置与大小</div>
    <div class="dshv-grid4">
      ${['X', 'Y', '宽', '高'].map((l, i) => `<div class="dshv-col">
        <div style="font-size:10px;color:#888;margin-bottom:2px">${l}</div>
        <input class="dshv-input" value="${['-0.574', '12.548', '10.693', '0.75'][i]}">
      </div>`).join('')}
    </div>
  </div>
  <div class="dshv-section">
    <div class="dshv-sectionTitle">文本</div>
    <textarea class="dshv-input" rows="3">整套烧录工具 整理
（库制作人）</textarea>
  </div>
</div>
<script>
  window.measure = () => {
    const q = (s) => Array.from(document.querySelectorAll(s))
    return JSON.stringify({
      inputs: q('.dshv-grid4 .dshv-input').map((e) => Math.round(e.getBoundingClientRect().width)),
      grid: Math.round(document.querySelector('.dshv-grid4').getBoundingClientRect().width),
      textarea: Math.round(document.querySelector('textarea').getBoundingClientRect().width),
      textareaH: Math.round(document.querySelector('textarea').getBoundingClientRect().height),
      overflow: document.documentElement.scrollWidth - document.documentElement.clientWidth,
    })
  }
</script>`

writeFileSync(new URL('./_uicheck.html', here), html)
console.log('wrote _uicheck.html, css bytes', blocks.join('').length)
