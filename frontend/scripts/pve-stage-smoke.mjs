import assert from 'node:assert/strict'
import { spawn } from 'node:child_process'
import { mkdtemp } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { northDiscardDeal } from '../tests/pveFixture.js'

const port = 9336
const profile = await mkdtemp(join(tmpdir(), 'mahjong-stage-'))
const chrome = spawn(process.env.CHROME_PATH || 'C:/Program Files/Google/Chrome/Application/chrome.exe', [
  '--headless=new', '--disable-gpu', '--no-first-run', '--no-default-browser-check',
  `--remote-debugging-port=${port}`, '--remote-allow-origins=*', `--user-data-dir=${profile}`, 'about:blank',
], { windowsHide: true, stdio: ['ignore', 'ignore', 'pipe'] })
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms))
const pending = new Map()
let socket, id = 0
async function until(fn, timeout = 20000) {
  const deadline = Date.now() + timeout
  while (Date.now() < deadline) {
    const value = await fn()
    if (value) return value
    await sleep(25)
  }
  throw new Error('Stage browser test timed out')
}
const command = (method, params = {}) => new Promise((resolve, reject) => {
  const requestId = ++id
  pending.set(requestId, { resolve, reject })
  socket.send(JSON.stringify({ id: requestId, method, params }))
})
async function evaluate(expression) {
  const response = await command('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true })
  if (response.exceptionDetails) throw new Error(JSON.stringify(response.exceptionDetails))
  return response.result.value
}

try {
  const page = await until(async () => {
    try { return (await (await fetch(`http://127.0.0.1:${port}/json/list`)).json()).find((entry) => entry.type === 'page') }
    catch { return null }
  })
  socket = new WebSocket(page.webSocketDebuggerUrl)
  await new Promise((resolve) => socket.addEventListener('open', resolve, { once: true }))
  socket.addEventListener('message', ({ data }) => {
    const msg = JSON.parse(data)
    const waiter = pending.get(msg.id)
    if (!waiter) return
    pending.delete(msg.id)
    msg.error ? waiter.reject(new Error(msg.error.message)) : waiter.resolve(msg.result)
  })
  await command('Runtime.enable')
  await command('Page.enable')
  await command('Page.addScriptToEvaluateOnNewDocument', { source: `
    const realFetch=window.fetch.bind(window);
    window.fetch=(url,init)=>String(url).endsWith('/game/auto-deal')
      ? Promise.resolve(new Response(JSON.stringify(${JSON.stringify(northDiscardDeal())}),{headers:{'Content-Type':'application/json'}}))
      : realFetch(url,init);
  ` })
  await command('Page.navigate', { url: process.env.PVE_URL || 'http://127.0.0.1:5173/' })
  await until(() => evaluate(`!![...document.querySelectorAll('button')].find(button=>button.textContent.includes('人机对战'))`))
  await evaluate(`[...document.querySelectorAll('button')].find(button=>button.textContent.includes('人机对战')).click()`)
  await until(() => evaluate(`!![...document.querySelectorAll('button')].find(button=>button.textContent.includes('开始对战'))`))
  await evaluate(`document.querySelector('[aria-label="人机对战设置"] input[type="checkbox"]').click()`)
  await evaluate(`[...document.querySelectorAll('button')].find(button=>button.textContent.includes('开始对战')).click()`)
  await until(() => evaluate(`!!document.querySelector('.pve-self-hand')`))
  await evaluate(`document.querySelector('#app').__vue_app__._instance.setupState.enableEV=true`)
  await until(() => evaluate(`!!document.querySelector('.pve-discard-hud .hud-tile')`))

  const viewports = [[390, 844, true], [844, 390, true], [1366, 768, false]]
  const results = []
  for (const [width, height, mobile] of viewports) {
    await command('Emulation.setDeviceMetricsOverride', { width, height, deviceScaleFactor: 1, mobile })
    await sleep(700)
    const result = await evaluate(`(() => {
      const rect=(el)=>el.getBoundingClientRect();
      const inside=(a,b)=>a.left>=b.left-3&&a.top>=b.top-3&&a.right<=b.right+3&&a.bottom<=b.bottom+3;
      const viewport={left:0,top:0,right:innerWidth,bottom:innerHeight};
      const stage=rect(document.querySelector('.game-stage'));
      const board=rect(document.querySelector('.pve-table'));
      const hand=rect(document.querySelector('.pve-self-hand'));
      const hud=rect(document.querySelector('.pve-discard-hud'));
      const tiles=[...document.querySelectorAll('.pve-self-hand button[role="listitem"]')];
      const hudTiles=[...document.querySelectorAll('.pve-discard-hud .hud-tile')];
      const rivers=[...document.querySelectorAll('.discard-river')].map(rect);
      const melds=[...document.querySelectorAll('.meld-area')].map(rect);
      const transform=getComputedStyle(document.querySelector('.game-stage')).transform;
      const hit=(element)=>{const r=rect(element);return document.elementFromPoint((r.left+r.right)/2,(r.top+r.bottom)/2)?.closest('button')===element};
      return {viewport:[innerWidth,innerHeight],stage:stage.toJSON(),hand:hand.toJSON(),hud:hud.toJSON(),
        transform,tiles:tiles.length,rivers:rivers.length,melds:melds.length,stageFits:inside(stage,viewport),boardFits:inside(board,stage),handFits:inside(hand,stage),hudFits:inside(hud,viewport),
        riversFit:rivers.every(river=>inside(river,viewport)),meldsFit:melds.every(meld=>inside(meld,viewport)),hintRemoved:!document.body.innerText.includes('建议横屏使用'),
        tilesFit:tiles.every(tile=>inside(rect(tile),hand)&&inside(rect(tile),viewport)),hudTiles:hudTiles.length,
        clickTargets:tiles.every(hit)&&hudTiles.every(hit)};
    })()`)
    assert.ok(result.transform.startsWith('matrix('), `${width}x${height}: missing stage transform`)
    assert.ok(result.stageFits && result.boardFits && result.handFits && result.hudFits && result.tilesFit && result.riversFit && result.meldsFit && result.hintRemoved && result.clickTargets,
      `${width}x${height}: stage or hand clipped / click target drifted: ${JSON.stringify(result)}`)
    assert.equal(result.tiles, 14)
    results.push({ viewport: result.viewport, stage: result.stage, hand: result.hand, tiles: result.tiles })
  }
  console.log(JSON.stringify({ status: 'passed', viewports: results }, null, 2))
} finally {
  if (socket?.readyState === WebSocket.OPEN) {
    try { await command('Browser.close') } catch {}
    socket.close()
  }
  chrome.kill()
}
