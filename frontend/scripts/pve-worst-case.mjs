// Run against the Vite dev server: node scripts/pve-worst-case.mjs
import assert from 'node:assert/strict'
import { spawn } from 'node:child_process'
import { mkdtemp, mkdir, writeFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'

const port = 9334
const profile = await mkdtemp(join(tmpdir(), 'mahjong-worst-case-'))
const chrome = spawn(process.env.CHROME_PATH || 'C:/Program Files/Google/Chrome/Application/chrome.exe', [
  '--headless=new', '--disable-gpu', '--no-first-run', '--no-default-browser-check',
  `--remote-debugging-port=${port}`, '--remote-allow-origins=*', `--user-data-dir=${profile}`, 'about:blank',
], { windowsHide: true, stdio: ['ignore', 'ignore', 'pipe'] })
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms))
const pending = new Map()
const browserErrors = []
let socket, requestId = 0
async function until(fn, timeout = 15000) {
  const end = Date.now() + timeout
  while (Date.now() < end) {
    const result = await fn()
    if (result) return result
    await sleep(25)
  }
  throw new Error('Worst-case browser fixture timed out')
}
const command = (method, params = {}) => new Promise((resolve, reject) => {
  const id = ++requestId
  pending.set(id, { resolve, reject })
  socket.send(JSON.stringify({ id, method, params }))
})
async function evaluate(expression) {
  const result = await command('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true })
  if (result.exceptionDetails) throw new Error(JSON.stringify(result.exceptionDetails))
  return result.result.value
}

try {
  const page = await until(async () => {
    try {
      const pages = await (await fetch(`http://127.0.0.1:${port}/json/list`)).json()
      return pages.find((item) => item.type === 'page')
    } catch { return null }
  })
  socket = new WebSocket(page.webSocketDebuggerUrl)
  await new Promise((resolve) => socket.addEventListener('open', resolve, { once: true }))
  socket.addEventListener('message', ({ data }) => {
    const msg = JSON.parse(data)
    if (msg.method === 'Runtime.exceptionThrown') browserErrors.push(msg.params.exceptionDetails)
    if (!pending.has(msg.id)) return
    const { resolve, reject } = pending.get(msg.id)
    pending.delete(msg.id)
    msg.error ? reject(new Error(msg.error.message)) : resolve(msg.result)
  })
  await command('Runtime.enable')
  await command('Page.enable')
  await command('Page.navigate', { url: process.env.PVE_URL || 'http://127.0.0.1:5173/worst-case.html' })
  await until(() => evaluate(`document.querySelectorAll('[data-position] .discard-river .mahjong-tile').length === 72`))
  await mkdir('tests/artifacts', { recursive: true })
  const results = []
  for (const [width, height] of [[375, 667], [390, 667], [412, 667], [390, 844], [412, 844]]) {
    await command('Emulation.setDeviceMetricsOverride', { width, height, deviceScaleFactor: 1, mobile: false })
    await sleep(120)
    const result = await evaluate(`(() => {
      const rect = (el) => el.getBoundingClientRect();
      const fits = (a,b) => a.left >= b.left - .5 && a.top >= b.top - .5 && a.right <= b.right + .5 && a.bottom <= b.bottom + .5;
      const overlaps = (a,b) => Math.max(0,Math.min(a.right,b.right)-Math.max(a.left,b.left))*Math.max(0,Math.min(a.bottom,b.bottom)-Math.max(a.top,b.top)) > 1;
      const box = (selector) => rect(document.querySelector(selector)).toJSON();
      const board = document.querySelector('.pve-table');
      const self = document.querySelector('.pve-self-controls');
      const seats = [...document.querySelectorAll('.opponent-seat')];
      const rivers = [...document.querySelectorAll('.discard-river')];
      const meldGroups = [...document.querySelectorAll('.opponent-seat [aria-label="副露牌组"], .compact-melds [aria-label="副露牌组"]')];
      const handTiles = [...document.querySelectorAll('.pve-self-hand button[role="listitem"]')];
      const failures=[];
      const page = {left:0,top:0,right:innerWidth,bottom:innerHeight};
      for (const selector of ['.pve-table','.table-center','.pve-ev-slot','.pve-self-controls','.pve-self-hand','.compact-melds','[aria-label="自家牌河"]']) {
        const el=document.querySelector(selector); if (!el || !fits(rect(el),page)) failures.push(selector+' outside viewport');
      }
      for (const seat of seats) {
        if (!fits(rect(seat),rect(board))) failures.push(seat.dataset.position+' outside table');
        if (seat.querySelectorAll('[aria-label="副露牌组"]').length !== 4) failures.push(seat.dataset.position+' meld count');
        if (seat.querySelectorAll('.concealed-hand .tile-back').length !== 1) failures.push(seat.dataset.position+' single concealed tile');
        const seatRiver=seat.querySelector('.discard-river');
        for (const group of seat.querySelectorAll('[aria-label="副露牌组"]')) if (overlaps(rect(group),rect(seatRiver))) failures.push(seat.dataset.position+' meld overlaps river');
      }
      for (const river of rivers) {
        const owner=river.closest('.opponent-seat') || self;
        if (river.children.length !== 24) failures.push(river.dataset.layout+' discard count');
        if (!fits(rect(river),rect(owner))) failures.push(river.dataset.layout+' river outside owner');
        for (const tile of river.children) if (!fits(rect(tile),rect(river))) { failures.push(river.dataset.layout+' discard clipped'); break; }
        const rows=new Set([...river.children].map(tile=>Math.round(rect(tile).top))).size;
        if (rows > (['left','right'].includes(river.dataset.layout) ? 6 : river.dataset.layout === 'top' ? 4 : 3)) failures.push(river.dataset.layout+' excess rows '+rows);
      }
      for (const group of meldGroups) {
        const owner=group.closest('.opponent-seat') || document.querySelector('.compact-melds');
        if (!fits(rect(group),rect(owner))) failures.push('meld group outside '+(owner.dataset.position || 'self'));
        if (group.querySelectorAll('.mahjong-tile').length !== 4) failures.push('meld group tile count');
      }
      const selfHand=rect(document.querySelector('.pve-self-hand'));
      const selfMelds=rect(document.querySelector('.compact-melds'));
      const selfRiver=rect(document.querySelector('[aria-label="自家牌河"]'));
      if (!(selfHand.top < selfMelds.top && selfMelds.top < selfRiver.top)) failures.push('self control order');
      if (overlaps(selfHand,selfMelds) || overlaps(selfHand,selfRiver) || overlaps(selfMelds,selfRiver)) failures.push('self controls overlap');
      if (handTiles.length !== 14 || handTiles.some(tile=>!fits(rect(tile),rect(document.querySelector('.pve-self-hand'))))) failures.push('hand clipped');
      const layers=['[aria-label="轮次状态"]','.pve-table','.pve-ev-slot','.pve-self-controls'].map(s=>rect(document.querySelector(s)));
      for (let i=1;i<layers.length;i++) if (layers[i].top < layers[i-1].bottom-.5) failures.push('main layers overlap');
      const center=rect(document.querySelector('.table-center'));
      for (const seat of seats.filter(s=>s.dataset.position!=='top')) if (overlaps(center,rect(seat))) failures.push('center overlaps '+seat.dataset.position);
      return {viewport:[innerWidth,innerHeight],scroll:[document.documentElement.scrollWidth,document.documentElement.clientWidth,document.documentElement.scrollHeight,document.documentElement.clientHeight],board:box('.pve-table'),ev:box('.pve-ev-slot'),self:box('.pve-self-controls'),riverHeights:rivers.map(r=>[r.dataset.layout,Math.round(rect(r).height)]),debug:rivers.map(r=>({layout:r.dataset.layout,grid:getComputedStyle(r).gridTemplateColumns,rows:getComputedStyle(r).gridTemplateRows,river:rect(r).toJSON(),tile:rect(r.firstElementChild).toJSON(),owner:rect(r.closest('.opponent-seat')||self).toJSON()})),meldDebug:meldGroups.slice(-4).map(g=>({group:rect(g).toJSON(),owner:rect(g.closest('.opponent-seat')||document.querySelector('.compact-melds')).toJSON()})),failures};
    })()`)
    const screenshot = await command('Page.captureScreenshot', { format: 'png' })
    await writeFile(`tests/artifacts/pve-worst-case-${width}x${height}.png`, Buffer.from(screenshot.data, 'base64'))
    if (result.failures.length) console.error(JSON.stringify(result, null, 2))
    assert.deepEqual(result.scroll, [width, width, height, height], `${width}x${height} page overflow`)
    assert.deepEqual(result.failures, [], `${width}x${height} clipped or overlapping content`)
    await evaluate('window.__setWorstCaseTurn(0)')
    const waiting = await evaluate(`(() => {
      const slot=document.querySelector('.pve-ev-slot').getBoundingClientRect();
      const placeholder=document.querySelector('.pve-ev-placeholder').getBoundingClientRect();
      const root=document.documentElement;
      return {slot:[slot.x,slot.y,slot.width,slot.height].map(n=>Math.round(n*100)/100),
        placeholderHeight:placeholder.height,scroll:[root.scrollWidth,root.clientWidth,root.scrollHeight,root.clientHeight]};
    })()`)
    assert.deepEqual(waiting.scroll, [width, width, height, height], `${width}x${height} waiting page overflow`)
    assert.equal(Math.round(waiting.placeholderHeight), Math.round(waiting.slot[3]), `${width}x${height} waiting EV slot height`)
    let stableSlots = null
    const slotSelectors = [
      '[aria-label="轮次状态"]', '.pve-table', '.opponent-seat.top', '.opponent-seat.left',
      '.opponent-seat.right', '.table-center', '.pve-ev-slot', '[aria-label="切牌推荐结果"]',
      '.pve-self-controls', '.pve-self-hand', '.compact-melds', '[aria-label="自家牌河"]',
      '.river--top', '.river--left', '.river--right', '.river--self',
    ]
    for (let turn = 1; turn <= 15; turn++) {
      await evaluate(`window.__setWorstCaseTurn(${turn})`)
      await sleep(35)
      const frame = await evaluate(`(() => {
        const selectors=${JSON.stringify(slotSelectors)};
        const rect=(el)=>el.getBoundingClientRect();
        const slots=Object.fromEntries(selectors.map(selector=>{const r=rect(document.querySelector(selector));return [selector,[r.x,r.y,r.width,r.height].map(n=>Math.round(n*100)/100)]}));
        const failures=[];
        for (const river of document.querySelectorAll('.discard-river')) for (const tile of river.children) {
          const a=rect(tile),b=rect(river);
          if (a.left<b.left-.5 || a.top<b.top-.5 || a.right>b.right+.5 || a.bottom>b.bottom+.5) {failures.push(river.dataset.layout+' tile outside fixed grid');break}
        }
        for (const group of document.querySelectorAll('[aria-label="副露牌组"]')) {
          const a=rect(group),b=rect(group.closest('.opponent-seat')||document.querySelector('.compact-melds'));
          if (a.left<b.left-.5 || a.top<b.top-.5 || a.right>b.right+.5 || a.bottom>b.bottom+.5) failures.push('meld outside fixed slot');
        }
        const ratios=[...document.querySelectorAll('.pve-table .mahjong-tile:not(.sideways),.pve-self-controls .mahjong-tile:not(.sideways)')].map(tile=>{const r=rect(tile);return r.width/r.height});
        if (ratios.some(r=>Math.abs(r-.75)>.012)) failures.push('tile aspect ratio');
        const root=document.documentElement;
        return {slots,failures,scroll:[root.scrollWidth,root.clientWidth,root.scrollHeight,root.clientHeight]};
      })()`)
      if (!stableSlots) stableSlots = frame.slots
      assert.deepEqual(frame.slots['.pve-ev-slot'], waiting.slot, `${width}x${height} waiting to EV layout shift`)
      assert.deepEqual(frame.slots, stableSlots, `${width}x${height} turn ${turn} layout shift`)
      assert.deepEqual(frame.failures, [], `${width}x${height} turn ${turn} tile clipping`)
      assert.deepEqual(frame.scroll, [width, width, height, height], `${width}x${height} turn ${turn} page overflow`)
    }
    const { debug, meldDebug, ...summary } = result
    results.push({ ...summary, stableTurns: 15 })
  }
  assert.deepEqual(browserErrors, [])
  console.log(JSON.stringify({ status: 'passed', results }, null, 2))
} finally {
  if (socket?.readyState === WebSocket.OPEN) {
    try { await command('Browser.close') } catch {}
    socket.close()
  }
  chrome.kill()
}
