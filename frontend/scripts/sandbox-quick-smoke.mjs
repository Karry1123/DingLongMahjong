import assert from 'node:assert/strict'
import { spawn } from 'node:child_process'
import { mkdtemp, writeFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'

// UI integration test: the recommendation endpoint is intentionally mocked.
const profile = await mkdtemp(join(tmpdir(), 'sandbox-reference-'))
const chrome = spawn(process.env.CHROME_PATH || 'C:/Program Files/Google/Chrome/Application/chrome.exe', [
  '--headless=new', '--disable-gpu', '--no-sandbox', '--no-first-run', '--no-default-browser-check',
  '--remote-debugging-pipe', `--user-data-dir=${profile}`, 'about:blank',
], { windowsHide: true, stdio: ['ignore', 'ignore', 'pipe', 'pipe', 'pipe'] })
let sequence = 0, buffer = '', sessionId
let browserErrors = ''
chrome.stderr.on('data', chunk => { browserErrors = (browserErrors + chunk).slice(-4000) })
const pending = new Map()
chrome.stdio[4].on('data', chunk => {
  buffer += chunk.toString()
  let end
  while ((end = buffer.indexOf('\0')) >= 0) {
    const raw = buffer.slice(0, end)
    buffer = buffer.slice(end + 1)
    if (!raw) continue
    const message = JSON.parse(raw), entry = pending.get(message.id)
    if (!entry) continue
    pending.delete(message.id)
    clearTimeout(entry.timeout)
    message.error ? entry.reject(new Error(message.error.message)) : entry.resolve(message.result)
  }
})
function command(method, params = {}, attached = true) {
  return new Promise((resolve, reject) => {
    const id = ++sequence
    const timeout = setTimeout(() => { pending.delete(id); reject(new Error(`CDP timed out: ${method}\n${browserErrors}`)) }, 15000)
    pending.set(id, { resolve, reject, timeout })
    chrome.stdio[3].write(JSON.stringify({ id, method, params, ...(attached && sessionId ? { sessionId } : {}) }) + '\0')
  })
}
async function evaluate(expression) {
  const response = await command('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true })
  if (response.exceptionDetails) throw new Error(JSON.stringify(response.exceptionDetails))
  return response.result.value
}
async function until(expression) {
  for (let i = 0; i < 300; i++) {
    if (await evaluate(expression)) return
    await new Promise(resolve => setTimeout(resolve, 50))
  }
  throw new Error(`UI timed out: ${expression}\n${JSON.stringify(await evaluate('({url:location.href, text:document.body.innerText.slice(0,1200), errors:window.__uiErrors})'))}`)
}
const click = text => evaluate(`Array.from(document.querySelectorAll('button')).find(b => b.textContent.trim() === ${JSON.stringify(text)})?.click()`)
const key = tile => evaluate(`document.querySelector('[data-key-tile="${tile}"]').click()`)
const handCount = () => evaluate('document.querySelectorAll(".reference-hand button").length')

try {
  const { targetId } = await command('Target.createTarget', { url: 'about:blank' }, false)
  ;({ sessionId } = await command('Target.attachToTarget', { targetId, flatten: true }, false))
  await command('Page.enable')
  await command('Runtime.enable')
  await command('Emulation.setDeviceMetricsOverride', { width: 390, height: 844, deviceScaleFactor: 1, mobile: true })
  await command('Page.addScriptToEvaluateOnNewDocument', { source: `
    localStorage.setItem('dl.auth.token', 'sandbox-smoke-only');
    window.__requests = []; window.__failNext = false; window.__uiErrors = [];
    window.addEventListener('error', event => window.__uiErrors.push(event.message));
    window.addEventListener('unhandledrejection', event => window.__uiErrors.push(String(event.reason)));
    const realFetch = window.fetch.bind(window);
    window.fetch = (url, init) => {
      if (String(url).endsWith('/api/me')) return Promise.resolve(new Response(JSON.stringify({id:1, display_name:'Smoke'})));
      if (String(url).endsWith('/api/recommend')) {
        const body = JSON.parse(init.body); window.__requests.push(body);
        if (window.__failNext) { window.__failNext = false; return Promise.resolve(new Response('test unavailable', {status:503})); }
        return new Promise(resolve => setTimeout(() => resolve(new Response(JSON.stringify({
          best_tile:body.hand_tiles[0], shanten:1, effective_count:12,
          candidates:[{tile:body.hand_tiles[0], effective_count:12}]
        }))), 80));
      }
      return realFetch(url, init);
    };
  ` })
  await command('Page.navigate', { url: `${process.env.SMOKE_URL || 'http://127.0.0.1:5173'}/#/sandbox` })
  await until('!!document.querySelector(".sandbox-reference")')
  const opening = ['1m', '1m', '1m', '1m', '2m', '3m', '4m', '5p', '6p', '7p', '2s', '3s', '4s', 'E']
  for (const [index, tile] of opening.entries()) {
    await key(tile)
    if (index === 3) {
      assert.equal(await evaluate('document.querySelector("[data-key-tile=\\"1m\\"]").disabled'), true, 'four-copy limit before full hand')
      assert.equal(await evaluate('document.querySelector("[data-key-tile=\\"2m\\"]").disabled'), false)
      assert.equal(await evaluate('window.__requests.length'), 0, 'no request for incomplete hand')
    }
  }
  await until('document.querySelector(".reference-summary").textContent.includes("12")')
  assert.equal(await handCount(), 14)
  assert.equal(await evaluate('window.__requests.length'), 1)
  assert.equal(await evaluate('document.querySelector("[data-key-tile=\\"1m\\"]").disabled'), true)
  assert.equal(await evaluate('document.querySelectorAll(".reference-hand .marked").length'), 4)
  await evaluate('document.querySelector(".reference-candidates summary").click()')
  assert.equal(await evaluate('document.querySelectorAll(".reference-candidates li").length'), 1)
  await evaluate('document.querySelector(".reference-candidates summary").click()')
  await evaluate('document.querySelector(".reference-hand button").click()')
  assert.equal(await handCount(), 13)
  await key('N')
  await until('window.__requests.length === 2 && document.querySelector(".reference-summary").textContent.includes("12")')
  assert.equal(await handCount(), 14)
  assert.deepEqual(await evaluate('window.__requests.at(-1).discards'), ['1m'])
  await click('撤销上一步')
  assert.equal(await handCount(), 13)
  await click('撤销上一步')
  assert.equal(await handCount(), 14)
  await until('!document.querySelector(".reference-summary").textContent.includes("正在")')

  await click('吃碰杠')
  await evaluate('document.querySelectorAll(".reference-hand button").forEach((b,i) => { if(i < 4) b.click() })')
  await click('确认杠')
  assert.equal(await handCount(), 10)
  await key('N')
  await until('window.__requests.at(-1).melds.length === 1 && document.querySelector(".reference-summary").textContent.includes("12")')
  const kong = await evaluate('window.__requests.at(-1)')
  assert.equal(kong.hand_tiles.length + kong.melds.length * 3, 14)
  assert.equal(kong.melds[0].tiles.length, 4)

  await evaluate('document.querySelector(".reference-public summary").click()')
  await click('用键盘录已见牌')
  await key('S')
  await until('window.__requests.at(-1).discarded_tiles.includes("S")')
  assert.deepEqual(await evaluate('window.__requests.at(-1).opponents'), [])
  await click('回到手牌')
  await evaluate('document.querySelector(".reference-settings button").click()')
  await key('F')
  await until('window.__requests.at(-1).dealer_tile === "F"')
  await click('重置')
  assert.equal(await handCount(), 0)
  assert.equal(await evaluate('document.querySelector(".reference-settings button").textContent.includes("发")'), true)
  await click('撤销上一步')
  assert.equal(await handCount(), 11)
  await evaluate('window.__failNext = true; document.querySelector(".reference-dealer input").click()')
  await until('!!document.querySelector("[role=alert]")')
  await click('重试')
  await until('document.querySelector(".reference-summary").textContent.includes("12")')

  for (const width of [320, 360, 390, 1280]) {
    await command('Emulation.setDeviceMetricsOverride', { width, height: 844, deviceScaleFactor: 1, mobile: width < 600 })
    assert.equal(await evaluate('document.documentElement.scrollWidth <= innerWidth'), true, `overflow at ${width}`)
    assert.equal(await evaluate('Array.from(document.querySelectorAll(".reference-keys button, .reference-hand button, .reference-tools button")).every(b => { const r=b.getBoundingClientRect(); return r.width >= 44 && r.height >= 44 })'), true, `touch size at ${width}`)
  }
  await command('Emulation.setDeviceMetricsOverride', { width: 390, height: 844, deviceScaleFactor: 1, mobile: true })
  const screenshot = await command('Page.captureScreenshot', { format: 'png', captureBeyondViewport: true })
  const screenshotPath = join(profile, 'sandbox-reference.png')
  await writeFile(screenshotPath, Buffer.from(screenshot.data, 'base64'))
  await click('高级：全景推演 ↗')
  await until('!!document.querySelector(".god-view")')
  await click('← 返回实战参考（独立牌局）')
  await until('!!document.querySelector(".sandbox-reference")')
  assert.equal(await evaluate('document.querySelector(".reference-settings button").textContent.includes("发")'), true)
  assert.deepEqual(await evaluate('window.__uiErrors'), [])
  await command('Page.navigate', { url: `${process.env.SMOKE_URL || 'http://127.0.0.1:5173'}/?preview=design` })
  await until('document.body.textContent.includes("Design system")')
  console.log('PASS: mocked 14 → recommend → discard → draw → recommend; undo, kong, seen tiles, settings, reset, retry, advanced, responsive 320/360/390/1280 and design preview.')
  console.log(`Screenshot: ${screenshotPath}`)
} finally {
  for (const entry of pending.values()) { clearTimeout(entry.timeout); entry.reject(new Error('Browser closed')) }
  chrome.kill()
}
