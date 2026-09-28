import assert from 'node:assert/strict'
import { spawn } from 'node:child_process'
import { mkdir, mkdtemp, writeFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'

const url = process.env.PVP_URL || 'http://127.0.0.1:5178/'
const browsers = [], clients = []
const sleep = ms => new Promise(resolve => setTimeout(resolve, ms))
async function until(fn) {
  for (let i = 0; i < 180; i++) { const value = await fn(); if (value) return value; await sleep(100) }
  throw new Error('Browser test timed out')
}
async function launch(port) {
  const profile = await mkdtemp(join(tmpdir(), 'dinglong-room-window-'))
  const process = spawn('C:/Program Files/Google/Chrome/Application/chrome.exe', [
    '--headless=new', '--disable-gpu', '--no-first-run', '--no-default-browser-check',
    `--remote-debugging-port=${port}`, '--remote-allow-origins=*', `--user-data-dir=${profile}`, 'about:blank',
  ], { windowsHide: true, stdio: 'ignore' })
  browsers.push(process)
  const page = await until(async () => { try { return (await (await fetch(`http://127.0.0.1:${port}/json/list`)).json()).find(p => p.type === 'page') } catch { return null } })
  const socket = new WebSocket(page.webSocketDebuggerUrl), pending = new Map(); let id = 0
  await new Promise(resolve => socket.addEventListener('open', resolve, { once: true }))
  socket.addEventListener('message', ({ data }) => { const msg = JSON.parse(data), waiter = pending.get(msg.id); if (!waiter) return; pending.delete(msg.id); msg.error ? waiter.reject(new Error(msg.error.message)) : waiter.resolve(msg.result) })
  const command = (method, params = {}) => new Promise((resolve, reject) => { const requestId = ++id; pending.set(requestId, { resolve, reject }); socket.send(JSON.stringify({ id: requestId, method, params })) })
  async function evaluate(expression) { const result = await command('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true }); if (result.exceptionDetails) throw new Error(JSON.stringify(result.exceptionDetails)); return result.result.value }
  const client = { socket, command, evaluate }; clients.push(client)
  await command('Page.enable'); await command('Emulation.setDeviceMetricsOverride', { width:1280, height:900, deviceScaleFactor:1, mobile:false }); await command('Page.navigate', { url })
  await until(() => evaluate(`!!document.querySelector('[data-mode="pvp"]')`))
  return client
}
async function click(client, selector) { await client.evaluate(`(()=>{const el=document.querySelector(${JSON.stringify(selector)});if(!el||el.disabled)throw new Error('Unavailable button: '+${JSON.stringify(selector)});el.click()})()`); await sleep(70) }
async function input(client, selector, value) { await client.evaluate(`(()=>{const el=document.querySelector(${JSON.stringify(selector)});el.value=${JSON.stringify(value)};el.dispatchEvent(new Event('input',{bubbles:true}));})()`); await sleep(30) }
async function enterLobby(client, name) { await click(client, '[data-mode="pvp"]'); await until(() => client.evaluate(`!!document.querySelector('#pvp-nickname')`)); await input(client, '#pvp-nickname', name); await click(client, '.lobby-dialog button[type="submit"]') }
async function createRoom(client, capacity = 2) {
  await click(client, '.entry-action:first-child'); await click(client, `.capacity-options button:nth-child(${capacity - 1})`); await click(client, '.lobby-dialog button[type="submit"]')
  await until(() => client.evaluate(`!!document.querySelector('.ready-button')&&!document.querySelector('.ready-button').disabled`))
  return client.evaluate(`document.querySelector('.room-number').textContent.trim()`)
}
async function joinRoom(client, roomId) {
  await click(client, '.entry-action:nth-child(2)'); await input(client, '#pvp-room-id', roomId); await click(client, '.lobby-dialog button[type="submit"]')
  await until(() => client.evaluate(`!!document.querySelector('.ready-button')&&!document.querySelector('.ready-button').disabled`))
}
async function shot(client, label) { const screenshot = await client.command('Page.captureScreenshot', { format: 'png' }); await writeFile(`tests/artifacts/pvp-room/${label}.png`, Buffer.from(screenshot.data, 'base64')) }
async function verifyLayout(client, width, height) {
  await client.command('Emulation.setDeviceMetricsOverride', { width, height, deviceScaleFactor: 1, mobile: false }); await sleep(180)
  const result = await client.evaluate(`(()=>{
    const stage=document.querySelector('.is-entry-stage'), rect=s=>document.querySelector(s).getBoundingClientRect();
    const e=rect('[data-seat="E"]'),s=rect('[data-seat="S"]'),w=rect('[data-seat="W"]'),n=rect('[data-seat="N"]');
    const overflow=[...document.querySelectorAll('.waiting-seat,.waiting-table')].some(el=>el.scrollWidth>el.clientWidth+1);
    return {overflow:overflow||stage.scrollWidth>stage.clientWidth+1, fourSeats:document.querySelectorAll('.waiting-seat').length===4,
      cardinal:document.querySelector('[data-seat="E"]').offsetLeft<document.querySelector('[data-seat="N"]').offsetLeft&&document.querySelector('[data-seat="W"]').offsetLeft>document.querySelector('[data-seat="N"]').offsetLeft&&document.querySelector('[data-seat="N"]').offsetTop<document.querySelector('[data-seat="E"]').offsetTop&&document.querySelector('[data-seat="S"]').offsetTop>document.querySelector('[data-seat="E"]').offsetTop, allInWidth:[e,s,w,n].every(r=>r.left>=0&&r.right<=innerWidth)};
  })()`)
  assert.deepEqual(result, { overflow: false, fourSeats: true, cardinal: true, allInWidth: true })
  await shot(client, `waiting-${width}`)
  return { width, height, ...result }
}
async function seatGeometry(client) {
  return client.evaluate(`Object.fromEntries([...document.querySelectorAll('.waiting-seat')].map(el=>{const r=el.getBoundingClientRect();return [el.dataset.seat,[r.x,r.y,r.width,r.height]]}))`)
}
try {
  await mkdir('tests/artifacts/pvp-room', { recursive: true })
  const first = await launch(9363), second = await launch(9364)
  await enterLobby(first, '东窗房主'); await enterLobby(second, '南窗牌友')
  const roomId = await createRoom(first)
  const stableSeats=[]
  for(const [width,height] of [[1280,900],[390,844],[320,640]]) {
    await first.command('Emulation.setDeviceMetricsOverride',{width,height,deviceScaleFactor:1,mobile:false});await sleep(180)
    const before=await seatGeometry(first)
    const widths=Object.values(before).map(r=>r[2])
    assert.ok(Math.max(...widths)-Math.min(...widths)<0.1,JSON.stringify({width,widths})) // Fractional grid pixel rounding only.
    const heights=Object.values(before).map(r=>r[3])
    assert.ok(Math.max(...heights)-Math.min(...heights)<0.1)
    for(const wind of ['S','W','N','E','S','W','N','E']) {
      await click(first,`[data-seat="${wind}"]`)
      await until(()=>first.evaluate(`document.querySelector('.my-seat').dataset.seat===${JSON.stringify(wind)}`))
      assert.deepEqual(await seatGeometry(first),before,`seat moved at ${width}px after switching to ${wind}`)
    }
    stableSeats.push({width,height,fixedGeometry:true,consecutiveSeatChanges:8})
  }
  await first.command('Emulation.setDeviceMetricsOverride',{width:1280,height:900,deviceScaleFactor:1,mobile:false});await sleep(180)
  const beforeJoin=await seatGeometry(first)
  await click(first, '[data-seat="W"]'); await until(() => first.evaluate(`document.querySelector('.my-seat').dataset.seat==='W'`))
  await joinRoom(second, roomId)
  await until(() => first.evaluate(`document.querySelectorAll('.ai-seat').length===2`))
  assert.deepEqual(await seatGeometry(first),beforeJoin,'joining player and AI fill must not move any card')
  assert.equal(await second.evaluate(`document.querySelector('.my-seat').dataset.seat`), 'E')
  assert.equal(await first.evaluate(`document.querySelector('[data-seat="E"] strong').textContent`), '南窗牌友')
  await click(first, '[data-seat="N"]'); await until(() => second.evaluate(`document.querySelector('[data-seat="N"] strong').textContent==='东窗房主'`))
  await click(second, '[data-seat="S"]'); await until(() => first.evaluate(`document.querySelector('[data-seat="S"] strong').textContent==='南窗牌友'`))
  const replacement = await launch(9365); await enterLobby(replacement, '再会牌友')
  for (const [id, error] of [['000000', '不存在'], [roomId, '已满']]) {
    await click(replacement, '.entry-action:nth-child(2)'); await input(replacement, '#pvp-room-id', id); await click(replacement, '.lobby-dialog button[type="submit"]')
    await until(() => replacement.evaluate(`!!document.querySelector('.lobby-entry')&&document.querySelector('.lobby-error')?.textContent.includes(${JSON.stringify(error)})`))
  }
  assert.equal(await first.evaluate(`document.querySelectorAll('.occupied:not(.ai-seat)').length`), 2)
  const layouts = []
  for (const [width, height] of [[1280, 900], [390, 844], [320, 640]]) layouts.push(await verifyLayout(first, width, height))
  await click(first, '.ready-button'); await until(() => second.evaluate(`document.querySelector('[data-seat="N"] .ready-label').textContent.includes('已准备')`))
  await click(first, '.ready-button'); await until(() => second.evaluate(`document.querySelector('[data-seat="N"] .ready-label').textContent==='未准备'`))
  await click(first, '.ready-button'); await click(second, '.ready-button')
  await until(() => first.evaluate(`!!document.querySelector('.countdown-overlay')`))
  await click(second, '.countdown-overlay button')
  await until(() => first.evaluate(`!document.querySelector('.countdown-overlay')`))
  await sleep(3100)
  assert.equal(await first.evaluate(`!!document.querySelector('.pvp-game-table')`), false)
  await click(second, '.ready-button')
  const numbers = [new Set(), new Set()], startedAt = []
  const deadline = Date.now() + 8000
  while (Date.now() < deadline && startedAt.filter(Boolean).length < 2) {
    const states = await Promise.all([first, second].map(client => client.evaluate(`({number:document.querySelector('.countdown-overlay strong')?.textContent,game:document.querySelector('.pvp-game-table')?.dataset.gameId})`)))
    states.forEach((state, index) => { if (state.number) numbers[index].add(state.number); if (state.game && !startedAt[index]) startedAt[index] = Date.now() })
    await sleep(80)
  }
  for (const set of numbers) for (const number of ['3', '2', '1']) assert.ok(set.has(number), JSON.stringify([...set]))
  assert.equal(startedAt.filter(Boolean).length, 2)
  assert.ok(Math.abs(startedAt[0] - startedAt[1]) < 250)
  const games = await Promise.all([first, second].map(client => client.evaluate(`({id:document.querySelector('.pvp-game-table').dataset.gameId,tiles:document.querySelectorAll('.pvp-own-hand [role="list"] .mahjong-tile').length,god:document.querySelector('.round-god .mahjong-tile').dataset.tile,ev:!!document.querySelector('.pve-discard-hud,.action-recommend-badge'),progress:!!document.querySelector('.game-status-hint')})`)))
  assert.equal(games[0].id, games[1].id); assert.equal(games[0].god, games[1].god)
  assert.equal(games[0].tiles, 13); assert.equal(games[1].tiles, 13); assert.ok(games.every(g => !g.ev && g.progress))
  await shot(first, 'game-mobile'); await shot(second, 'game-desktop')
  // Abruptly closing the second independent browser dissolves a running room.
  await second.command('Browser.close'); second.socket.close()
  await until(() => first.evaluate(`!!document.querySelector('.pvp-dissolved-dialog')&&!!document.querySelector('[data-mode="pvp"]')`))
  assert.equal(await first.evaluate(`location.hash`), '')
  await click(first,'[data-dismiss-room]'); await enterLobby(first,'东窗房主')
  // Explicit exit dissolves the next room for both windows too.
  const nextRoom = await createRoom(first, 3); await joinRoom(replacement, nextRoom)
  await until(() => first.evaluate(`document.querySelectorAll('.occupied:not(.ai-seat)').length===2`))
  assert.equal(await first.evaluate(`document.querySelectorAll('.ai-seat').length`), 0)
  await click(replacement, '.waiting-footer .quiet-button'); await click(replacement, '.lobby-dialog .primary-button')
  await until(() => first.evaluate(`!!document.querySelector('.pvp-dissolved-dialog')&&!!document.querySelector('[data-mode="pvp"]')`))
  await until(() => replacement.evaluate(`!!document.querySelector('.pvp-dissolved-dialog')&&!!document.querySelector('[data-mode="pvp"]')`))
  console.log(JSON.stringify({ status: 'passed', separateBrowserWindows: true, roomId, stableSeats, scenarios: ['fixed seat geometry through 24 seat changes', 'joining player and AI fill preserve geometry', 'seat synchronization', 'first vacant E/S/W/N', 'AI fill', 'reject missing/full rooms over WS', 'ready/unready synchronization', 'cancel countdown', '3-2-1 on both windows', 'same private deal', 'disconnect dissolution', 'explicit exit dissolution'], numbers: numbers.map(s => [...s]), startDifferenceMs: Math.abs(startedAt[0] - startedAt[1]), games, layouts }, null, 2))
} finally {
  for (const client of clients) if (client.socket.readyState === WebSocket.OPEN) { try { await client.command('Browser.close') } catch {} client.socket.close() }
  for (const browser of browsers) browser.kill()
}
