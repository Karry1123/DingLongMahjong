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
  await command('Page.navigate', { url: process.env.PVE_URL || 'http://127.0.0.1:5173/' })
  await until(() => evaluate(`Array.from(document.querySelectorAll('button')).some(b => b.textContent.includes('人机对战'))`))
  await evaluate(`Array.from(document.querySelectorAll('button')).find(b => b.textContent.includes('人机对战')).click()`)
  await until(() => evaluate(`Array.from(document.querySelectorAll('button')).some(b => b.textContent.includes('开始对战'))`))
  await evaluate(`Array.from(document.querySelectorAll('button')).find(b => b.textContent.includes('开始对战')).click()`)
  await until(() => evaluate(`!!document.querySelector('[aria-label="手牌槽位"]') && !!document.querySelector('.pve-discard-hud .hud-tile')`))
  await sleep(500)
  await command('Emulation.setDeviceMetricsOverride', { width: 1366, height: 768, deviceScaleFactor: 1, mobile: false })
  await sleep(100)
  const recommendationView = await evaluate(`(() => { const aside=document.querySelector('[aria-label="实时决策看板"]'); const rows=[...aside.querySelectorAll('.hud-tile')]; return {count:rows.length,top:aside.getBoundingClientRect().top,bottom:aside.getBoundingClientRect().bottom,heroBottom:aside.querySelector('.pve-discard-hud')?.getBoundingClientRect().bottom,viewport:innerHeight,internalScroll:aside.scrollTop,pageScroll:window.scrollY}; })()`)
  assert.equal(recommendationView.count, 2)
  assert.ok(recommendationView.top >= 0 && recommendationView.bottom <= recommendationView.viewport)
  assert.ok(recommendationView.heroBottom <= recommendationView.viewport)
  assert.equal(recommendationView.internalScroll, 0)
  assert.equal(recommendationView.pageScroll, 0)
  await command('Emulation.setDeviceMetricsOverride', { width: 1440, height: 1000, deviceScaleFactor: 1, mobile: false })
  const desktop = await evaluate(`(() => {
    const work = document.querySelector('[aria-label="自家操作工作台"]');
    const left = work.querySelector('[aria-label="自家手牌与副露"]').getBoundingClientRect();
    const right = work.querySelector('[aria-label="实时决策看板"]').getBoundingClientRect();
    const hand = work.querySelector('.pve-self-hand').getBoundingClientRect();
    const meld = work.querySelector('.compact-melds').getBoundingClientRect();
    const text = document.body.innerText;
    return {left: left.toJSON(), right: right.toJSON(), hand: hand.toJSON(), meld: meld.toJSON(), editors: ['添加副露','清空副露','清空重选','选牌键盘'].filter(t => text.includes(t))};
  })()`)
  assert.deepEqual(desktop.editors, [])
  assert.ok(desktop.right.bottom <= desktop.hand.top + 1)
  assert.ok(desktop.meld.bottom <= desktop.hand.top + 1)
  assert.ok(desktop.hand.bottom <= 1000)
  await command('Emulation.setDeviceMetricsOverride', { width: 1366, height: 768, deviceScaleFactor: 1, mobile: false })
  await sleep(80)
  const callDock = await evaluate(`(async () => {
    const session=document.querySelector('#app').__vue_app__._instance.setupState;
    const aside=document.querySelector('[aria-label="实时决策看板"]');
    const before={scrollY:window.scrollY,rect:aside.getBoundingClientRect().toJSON()};
    const saved={phase:session.currentPhase,result:session.lastStepResult,seat:session.lastDiscardSeat};
    session.lastDiscardSeat='N';
    session.currentPhase='OPPONENT_DISCARD_ACTION';
    session.lastStepResult={...saved.result,need_self_action:true,call_decision:{
      recommended_action:{action_type:'chi',tiles:['4p','5p','6p'],provider_seat:'N'},
      reason:'保留两面搭子',candidates:[
        {action:{action_type:'chi',tiles:['4p','5p','6p'],provider_seat:'N'},net_ev:24},
        {action:{action_type:'pong',tiles:['4p','4p','4p'],provider_seat:'N'},net_ev:10},
        {action:{action_type:'ming_gang',tiles:['4p','4p','4p','4p'],provider_seat:'N'},net_ev:9},
        {action:{action_type:'hu',tiles:['4p'],provider_seat:'N'},net_ev:8},
        {action:{action_type:'pass',tiles:['4p'],provider_seat:'N'},net_ev:3},
      ],
    }};
    await new Promise(resolve=>setTimeout(resolve,50));
    const dock=aside.querySelector('.action-prompt-docked');
    const buttons=[...dock?.querySelectorAll('[aria-label="可选响应动作"] button')||[]];
    const panelBody=dock?.querySelector('.action-prompt-panel > div:last-child');
    const active={scrollY:window.scrollY,rect:aside.getBoundingClientRect().toJSON(),bodyOverflow:panelBody ? panelBody.scrollHeight-panelBody.clientHeight : -1,
      dockInside:!!dock && aside.contains(dock),strayPrompt:!!document.querySelector('.pve-self-controls .action-prompt-wrap'),
      buttons:buttons.map(button=>({type:button.dataset.action,shortcut:button.getAttribute('aria-keyshortcuts'),bottom:button.getBoundingClientRect().bottom})),
      recommended:!!dock?.querySelector('button[data-action="chi"]')?.textContent.includes('荐')};
    window.__restoreCallDock=async()=>{session.currentPhase=saved.phase;session.lastStepResult=saved.result;session.lastDiscardSeat=saved.seat;await new Promise(resolve=>setTimeout(resolve,50));};
    return {before,active};
  })()`)
  await mkdir('tests/artifacts', { recursive: true })
  const callShot = await command('Page.captureScreenshot', { format: 'png' })
  await writeFile('tests/artifacts/pve-call-dock.png', Buffer.from(callShot.data, 'base64'))
  await command('Emulation.setDeviceMetricsOverride', { width: 390, height: 844, deviceScaleFactor: 1, mobile: false })
  await sleep(80)
  const mobileCall = await evaluate(`(() => {const panel=document.querySelector('.pve-ev-slot .action-prompt-panel').getBoundingClientRect();const root=document.documentElement;return {top:panel.top,bottom:panel.bottom,scroll:[root.scrollWidth,root.clientWidth,root.scrollHeight,root.clientHeight]}})()`)
  assert.ok(mobileCall.top >= 0 && mobileCall.bottom <= 844)
  assert.deepEqual(mobileCall.scroll, [390,390,844,844])
  await command('Emulation.setDeviceMetricsOverride', { width: 1024, height: 768, deviceScaleFactor: 1, mobile: false })
  await sleep(80)
  const laptopCall = await evaluate(`(() => {const aside=document.querySelector('.pve-ev-slot').getBoundingClientRect();const buttons=[...document.querySelectorAll('.pve-ev-slot [aria-label="可选响应动作"] button')].map(el=>el.getBoundingClientRect());const center=document.querySelector('.table-center .mahjong-tile').getBoundingClientRect();const table=document.querySelector('.pve-table').getBoundingClientRect();return {dockBottom:aside.bottom,buttonBottom:Math.max(...buttons.map(r=>r.bottom)),centerVisible:center.top>=table.top&&center.bottom<=table.bottom,scrollY:window.scrollY}})()`)
  assert.ok(laptopCall.dockBottom <= 768 && laptopCall.buttonBottom <= 768)
  assert.equal(laptopCall.centerVisible, true)
  assert.equal(laptopCall.scrollY, 0)
  await command('Emulation.setDeviceMetricsOverride', { width: 1366, height: 768, deviceScaleFactor: 1, mobile: false })
  await evaluate('window.__restoreCallDock()')
  assert.equal(callDock.active.scrollY, callDock.before.scrollY)
  assert.equal(await evaluate('window.scrollY'), callDock.before.scrollY)
  assert.ok(callDock.active.rect.bottom < 768)
  assert.ok(callDock.active.rect.top < callDock.before.rect.top)
  assert.equal(callDock.active.dockInside, true)
  assert.equal(callDock.active.strayPrompt, false)
  assert.equal(callDock.active.recommended, true)
  assert.ok(callDock.active.bodyOverflow <= 1)
  assert.deepEqual(callDock.active.buttons.map(button=>button.type), ['chi','pong','ming_gang','hu','pass'])
  assert.deepEqual(callDock.active.buttons.map(button=>button.shortcut), ['1','2','3','4','5'])
  assert.ok(callDock.active.buttons.every(button=>button.bottom <= 768))
  assert.equal(await evaluate(`!!document.querySelector('[aria-label="实时决策看板"] .pve-discard-hud')`), true)
  await command('Emulation.setDeviceMetricsOverride', { width: 1440, height: 1000, deviceScaleFactor: 1, mobile: false })
  await mkdir('tests/artifacts', { recursive: true })
  await evaluate(`document.querySelector('[aria-label="自家操作工作台"]').scrollIntoView({block:'start'})`)
  await sleep(100)
  let shot = await command('Page.captureScreenshot', { format: 'png' })
  await writeFile('tests/artifacts/pve-desktop.png', Buffer.from(shot.data, 'base64'))
  await command('Emulation.setDeviceMetricsOverride', { width: 390, height: 844, deviceScaleFactor: 1, mobile: false })
  await sleep(150)
  const mobileDecision = await evaluate(`(() => {
    const hand=document.querySelector('[aria-label="手牌槽位"]');
    const controls=document.querySelector('[aria-label="自家手牌与副露"]');
    const tile=hand.querySelector('button[title="打出 北"]');
    const before=hand.querySelectorAll('button[role="listitem"]').length;
    tile.click();
    return {before,after:hand.querySelectorAll('button[role="listitem"]').length,river:!!document.querySelector('[aria-label="自家牌河"]'),drawerButton:!!document.querySelector('.hud-more'),tilesFit:[...hand.querySelectorAll('button[role="listitem"]')].every(el=>el.getBoundingClientRect().right<=controls.getBoundingClientRect().right+1)};
  })()`)
  assert.equal(mobileDecision.before, 14)
  assert.equal(mobileDecision.after, 14)
  await sleep(50)
  assert.equal(await evaluate(`document.querySelector('[aria-label="手牌槽位"] button[title="确认打出 北"]').classList.contains('hand-tile-selected')`), true)
  assert.equal(mobileDecision.river, false)
  assert.equal(mobileDecision.drawerButton, true)
  assert.equal(mobileDecision.tilesFit, true)
  const centerLayout = await evaluate(`(() => {const c=document.querySelector('.table-center');return {center:c.getBoundingClientRect().toJSON(),children:[...c.children].map(el=>({tag:el.tagName,text:el.textContent?.slice(0,12),rect:el.getBoundingClientRect().toJSON(),display:getComputedStyle(el).display}))}})()`)
  assert.ok(centerLayout.children.some(c => c.rect.width > 15 && c.rect.height > 20 && c.rect.top >= centerLayout.center.top && c.rect.bottom <= centerLayout.center.bottom), 'fortune tile visible inside table center')
  await evaluate(`document.querySelector('.hud-more').click()`)
  assert.equal(await evaluate(`!!document.querySelector('.hud-drawer')`), true)
  await evaluate(`document.querySelector('.hud-more').click()`)
  shot = await command('Page.captureScreenshot', { format: 'png' })
  await writeFile('tests/artifacts/pve-mobile-decision.png', Buffer.from(shot.data, 'base64'))
  for (const [width, height] of [[320, 568], [430, 932]]) {
    await command('Emulation.setDeviceMetricsOverride', { width, height, deviceScaleFactor: 1, mobile: false })
    await sleep(70)
    const fit = await evaluate(`(() => {
      const hand=document.querySelector('[aria-label="自家手牌与副露"]').getBoundingClientRect();
      const board=document.querySelector('.pve-table').getBoundingClientRect();
      const ev=document.querySelector('[aria-label="实时决策看板"]').getBoundingClientRect();
      return {scrollX:document.documentElement.scrollWidth-innerWidth,scrollY:document.documentElement.scrollHeight-innerHeight,handRight:hand.right,handBottom:hand.bottom,boardBottom:board.bottom,evBottom:ev.bottom,tiles:[...document.querySelectorAll('[aria-label="手牌槽位"] button[role="listitem"]')].filter(el=>el.getBoundingClientRect().right<=hand.right+1).length};
    })()`)
    assert.ok(fit.scrollX <= 0 && fit.scrollY <= 0, `${width}x${height} page scroll`)
    assert.ok(fit.handRight <= width+1 && fit.handBottom <= height+1 && fit.boardBottom <= height+1 && fit.evBottom <= height+1, `${width}x${height} clipped game layer`)
    assert.equal(fit.tiles, 14, `${width}x${height} visible hand tiles`)
  }
  await command('Emulation.setDeviceMetricsOverride', { width: 1440, height: 1000, deviceScaleFactor: 1, mobile: false })
  await evaluate(`window.__pveStart = performance.now(); document.querySelector('[aria-label="手牌槽位"] button[title$="北"]').click()`)
  await until(() => evaluate(`!!document.querySelector('[aria-label="自家牌河"]')`))
  const selfOrder = await evaluate(`(() => {const work=document.querySelector('[aria-label="自家操作工作台"]');const hand=work.querySelector('.pve-self-hand').getBoundingClientRect();const meld=work.querySelector('.compact-melds').getBoundingClientRect();const river=work.querySelector('[aria-label="自家牌河"]').getBoundingClientRect();return {hand:hand.top, meld:meld.top, river:river.top}})()`)
  assert.ok(selfOrder.river < selfOrder.hand && selfOrder.meld < selfOrder.hand)
  await until(() => evaluate(`document.querySelector('[data-seat="S"] .thinking-indicator')?.textContent.includes('思考中')`))
  const waitingDock = await evaluate(`(() => {const aside=document.querySelector('.pve-ev-slot');return {placeholder:!!aside.querySelector('.pve-ev-placeholder'),scrollY:window.scrollY,dockHeight:aside.getBoundingClientRect().height}})()`)
  assert.equal(waitingDock.placeholder, true)
  assert.equal(waitingDock.scrollY, 0)
  assert.ok(waitingDock.dockHeight >= 0 && waitingDock.dockHeight < 100)
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
  await sleep(400)
  const mobile = await evaluate(`(() => {
    const box = (selector) => document.querySelector(selector).getBoundingClientRect().toJSON();
    return {
      shell: box('.pve-portrait-shell'),
      board: box('.pve-table'),
      hand: box('[aria-label="自家手牌与副露"]'),
      recommend: box('[aria-label="实时决策看板"]'),
      viewport: {width: innerWidth, height: innerHeight},
      pageScroll: {width: document.documentElement.scrollWidth, height: document.documentElement.scrollHeight},
      rotated: getComputedStyle(document.querySelector('.pve-portrait-shell')).transform !== 'none',
      visibleHandTiles: (() => {const hand=document.querySelector('[aria-label="自家手牌与副露"]').getBoundingClientRect(); return [...document.querySelectorAll('[aria-label="手牌槽位"] button[role="listitem"]')].filter(el => {const r=el.getBoundingClientRect();return r.left >= hand.left && r.right <= hand.right && r.top >= hand.top && r.bottom <= hand.bottom && getComputedStyle(el.querySelector('.tile-face')).display !== 'none'}).length})(),
    };
  })()`)
  assert.equal(mobile.rotated, false)
  assert.ok(mobile.pageScroll.width <= mobile.viewport.width)
  assert.ok(mobile.pageScroll.height <= mobile.viewport.height)
  assert.equal(mobile.visibleHandTiles, 13)
  for (const key of ['board', 'hand', 'recommend']) {
    assert.ok(mobile[key].left >= -1 && mobile[key].right <= mobile.viewport.width + 1, `${key} horizontal overflow`)
    assert.ok(mobile[key].top >= -1 && mobile[key].bottom <= mobile.viewport.height + 1, `${key} vertical overflow`)
  }
  await sleep(400)
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
