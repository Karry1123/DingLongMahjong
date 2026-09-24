// Real Chromium + real API smoke test. Run Vite/backend first; only the deal is seeded.
import assert from 'node:assert/strict'
import { spawn } from 'node:child_process'
import { mkdtemp, mkdir, writeFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { northDiscardDeal } from '../tests/pveFixture.js'
import { checkPveVisuals } from './pve-visual-check.mjs'

const profile = await mkdtemp(join(tmpdir(), 'mahjong-pve-'))
const chrome = spawn(process.env.CHROME_PATH || 'C:/Program Files/Google/Chrome/Application/chrome.exe', [
  '--headless=new', '--disable-gpu', '--no-first-run', '--no-default-browser-check',
  '--remote-debugging-port=9333', '--remote-allow-origins=*', `--user-data-dir=${profile}`, 'about:blank',
], { windowsHide: true, stdio: ['ignore', 'ignore', 'pipe'] })
chrome.stderr.on('data', (data) => { if (process.env.CDP_DEBUG) process.stderr.write(data) })
const sleep = (ms) => new Promise((r) => setTimeout(r, ms))
let socket, id = 0
const pending = new Map(), errors = []
async function until(fn, timeout = 20000) {
  const deadline = Date.now() + timeout
  while (Date.now() < deadline) {
    const result = await fn()
    if (result) return result
    await sleep(20)
  }
  throw new Error('Browser smoke timed out')
}
const command = (method, params = {}) => new Promise((resolve, reject) => {
  const request = ++id
  pending.set(request, { resolve, reject })
  socket.send(JSON.stringify({ id: request, method, params }))
})
const evaluate = async (expression) => {
  const result = await command('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true })
  if (result.exceptionDetails) throw new Error(JSON.stringify(result.exceptionDetails))
  return result.result.value
}
try {
  const pages = await until(async () => {
    try {
      const targets = await (await fetch('http://127.0.0.1:9333/json/list')).json()
      return targets.find((target) => target.type === 'page' && !target.url.startsWith('chrome-extension:'))
    } catch { return null }
  })
  socket = new WebSocket(pages.webSocketDebuggerUrl)
  socket.addEventListener('close', (event) => {
    for (const { reject } of pending.values()) reject(new Error(`CDP closed: ${event.code} ${event.reason}`))
    pending.clear()
  })
  socket.addEventListener('error', (event) => console.error('CDP error', event.message))
  await new Promise((resolve) => socket.addEventListener('open', resolve, { once: true }))
  socket.addEventListener('message', ({ data }) => {
    const message = JSON.parse(data)
    if (message.method === 'Runtime.exceptionThrown') errors.push(message.params.exceptionDetails)
    if (pending.has(message.id)) {
      const { resolve, reject } = pending.get(message.id)
      pending.delete(message.id)
      message.error ? reject(new Error(message.error.message)) : resolve(message.result)
    }
  })
  await command('Runtime.enable')
  await command('Page.enable')
  await command('Emulation.setDeviceMetricsOverride', { width: 1440, height: 1000, deviceScaleFactor: 1, mobile: false })
  await command('Page.addScriptToEvaluateOnNewDocument', { source: `
    const realFetch = window.fetch.bind(window);
    window.__pveRequests = [];
    Math.random = () => 0.34;
    window.fetch = async (url, init) => {
      const body = JSON.parse(init?.body || '{}');
      if (String(url).endsWith('/game/auto-deal')) return new Response(JSON.stringify(${JSON.stringify(northDiscardDeal())}), { headers: {'Content-Type': 'application/json'} });
      const log = {url: String(url), seat: body.seat_wind, event: body.event, start: performance.now()};
      window.__pveRequests.push(log);
      const response = await realFetch(url, init);
      log.duration = performance.now() - log.start; log.status = response.status;
      return response;
    };
  ` })
  await command('Page.navigate', { url: process.env.PVE_URL || 'http://127.0.0.1:5178/' })
  await until(() => evaluate(`Array.from(document.querySelectorAll('button')).some(b => b.textContent.includes('人机对战'))`))
  await evaluate(`Array.from(document.querySelectorAll('button')).find(b => b.textContent.includes('人机对战')).click()`)
  await until(() => evaluate(`!!document.querySelector('[aria-label="手牌槽位"]') && document.querySelector('[aria-label="实时 EV 推荐"]').textContent.includes('Net EV')`))
  await sleep(500)
  await command('Emulation.setDeviceMetricsOverride', { width: 1366, height: 768, deviceScaleFactor: 1, mobile: false })
  await sleep(100)
  const recommendationView = await evaluate(`(() => { const aside=document.querySelector('[aria-label="实时 EV 推荐"]'); const rows=[...aside.querySelectorAll('[aria-label="切牌推荐结果"] [role="list"] > li')]; return {count:rows.length,fourthBottom:rows[3]?.getBoundingClientRect().bottom,viewport:innerHeight,internalScroll:aside.scrollTop}; })()`)
  assert.ok(recommendationView.count >= 4)
  assert.ok(recommendationView.fourthBottom <= recommendationView.viewport)
  assert.equal(recommendationView.internalScroll, 0)
  await command('Emulation.setDeviceMetricsOverride', { width: 1440, height: 1000, deviceScaleFactor: 1, mobile: false })
  const desktop = await evaluate(`(() => {
    const work = document.querySelector('[aria-label="自家操作工作台"]');
    const left = work.querySelector('[aria-label="自家手牌与副露"]').getBoundingClientRect();
    const right = work.querySelector('[aria-label="实时 EV 推荐"]').getBoundingClientRect();
    const text = document.body.innerText;
    return {left: left.toJSON(), right: right.toJSON(), editors: ['添加副露','清空副露','清空重选','选牌键盘'].filter(t => text.includes(t))};
  })()`)
  assert.deepEqual(desktop.editors, [])
  assert.ok(desktop.right.x >= desktop.left.right)
  assert.ok(Math.abs(desktop.left.y - desktop.right.y) < 2)
  await mkdir('tests/artifacts', { recursive: true })
  await evaluate(`document.querySelector('[aria-label="自家操作工作台"]').scrollIntoView({block:'start'})`)
  await sleep(100)
  let shot = await command('Page.captureScreenshot', { format: 'png' })
  await writeFile('tests/artifacts/pve-desktop.png', Buffer.from(shot.data, 'base64'))
  await evaluate(`window.__pveStart = performance.now(); document.querySelector('[aria-label="手牌槽位"] button[title="打出 北"]').click()`)
  await until(() => evaluate(`document.querySelector('[data-seat="S"] .thinking-indicator')?.textContent.includes('思考中')`))
  assert.equal(await evaluate(`document.querySelector('[data-seat="S"] [aria-label="弃牌"]').children.length`), 0)
  await until(() => evaluate(`document.querySelector('[data-seat="S"] [aria-label="弃牌"]').children.length > 0`))
  await until(() => evaluate(`window.__pveRequests.some(r => r.event?.actor_seat === 'S' && r.event?.event_type === 'DISCARD' && r.status === 200)`))
  const result = await evaluate(`({elapsed: performance.now()-window.__pveStart, requests: window.__pveRequests.filter(r=>r.start>=window.__pveStart), errors: [...document.querySelectorAll('[role="alert"]')].map(n=>n.textContent)})`)
  assert.deepEqual(result.errors, [])
  assert.ok(result.requests.some((r) => r.url.endsWith('/recommend') && r.seat === 'S' && r.status === 200))
  const secondRound = await evaluate(`(async () => {
    const app = document.querySelector('#app').__vue_app__;
    await app._instance.setupState.startNextRound(null, false, {isDraw: true});
    const table = document.querySelector('.pve-table');
    return {
      self: document.querySelector('[aria-label="自家信息"]').innerText,
      lowerSeat: table.querySelector('[data-seat="E"] header').innerText,
      dealer: document.querySelector('[aria-label="轮次状态"]').innerText,
    };
  })()`)
  assert.match(secondRound.self, /自家 · 北风/)
  assert.match(secondRound.lowerSeat, /下家 · 东风.*庄/)
  assert.match(secondRound.dealer, /当前庄家：下家 · 东风/)
  await command('Emulation.setDeviceMetricsOverride', { width: 390, height: 844, deviceScaleFactor: 1, mobile: false })
  await sleep(100)
  const mobile = await evaluate(`(() => {
    const left = document.querySelector('[aria-label="自家手牌与副露"]').getBoundingClientRect();
    const right = document.querySelector('[aria-label="实时 EV 推荐"]').getBoundingClientRect();
    return { stacked: right.y >= left.bottom, overflow: document.documentElement.scrollWidth > innerWidth };
  })()`)
  assert.ok(mobile.stacked)
  assert.equal(mobile.overflow, false)
  await evaluate(`document.querySelector('[aria-label="自家操作工作台"]').scrollIntoView({block:'start'})`)
  shot = await command('Page.captureScreenshot', { format: 'png' })
  await writeFile('tests/artifacts/pve-mobile.png', Buffer.from(shot.data, 'base64'))
  assert.deepEqual(errors, [])
  console.log(JSON.stringify({ recommendationView, desktop, mobile, northDiscard: result, secondRound, browserErrors: errors }, null, 2))
  await writeFile('tests/artifacts/pve-smoke.json', JSON.stringify({ recommendationView, desktop, mobile, northDiscard: result, secondRound, browserErrors: errors }, null, 2))
  assert.ok(result.elapsed >= 3000, `South acted before the three-second thinking timer: ${result.elapsed.toFixed(0)}ms`)
  const circleReview = await evaluate(`(async () => {
    const session = document.querySelector('#app').__vue_app__._instance.setupState;
    await session.startNextRound(null, false, {isDraw: true});
    await session.startNextRound(null, false, {isDraw: true});
    await session.declareDraw('一圈末局结算时序测试');
    return {
      gameOverVisible: !!document.querySelector('[aria-label="对局结束结算"]'),
      summaryVisible: !!document.querySelector('[aria-label="本圈对局总结"]'),
      action: document.querySelector('[aria-label="对局结束结算"] footer button')?.innerText,
    };
  })()`)
  assert.equal(circleReview.gameOverVisible, true)
  assert.equal(circleReview.summaryVisible, false)
  assert.match(circleReview.action, /查看本圈总结/)
  await evaluate(`document.querySelector('[aria-label="对局结束结算"] footer button').click()`)
  await until(() => evaluate(`!!document.querySelector('[aria-label="本圈对局总结"]')`))
  const summaryAfterReview = await evaluate(`({
    gameOverVisible: !!document.querySelector('[aria-label="对局结束结算"]'),
    summaryVisible: !!document.querySelector('[aria-label="本圈对局总结"]'),
  })`)
  assert.deepEqual(summaryAfterReview, { gameOverVisible: false, summaryVisible: true })
  console.log(JSON.stringify({ circleReview, summaryAfterReview }, null, 2))
  await checkPveVisuals({ command, evaluate, until, sleep })
} catch (e) {
  if (socket?.readyState === WebSocket.OPEN) {
    console.error(JSON.stringify({ errors, page: await evaluate('document.body.innerText'), url: await evaluate('location.href') }, null, 2))
  }
  throw e
} finally {
  if (socket?.readyState === WebSocket.OPEN) {
    try { await command('Browser.close') } catch {}
    socket.close()
  }
  chrome.kill()
}
