import assert from 'node:assert/strict'
import { spawn } from 'node:child_process'
import { mkdir, mkdtemp, writeFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'

const profile = await mkdtemp(join(tmpdir(), 'dinglong-pvp-'))
const port = 9361
const url = process.env.PVP_URL || process.env.PVE_URL || 'http://127.0.0.1:5173/'
const chrome = spawn(process.env.CHROME_PATH || 'C:/Program Files/Google/Chrome/Application/chrome.exe', [
  '--headless=new', '--disable-gpu', '--no-first-run', '--no-default-browser-check',
  `--remote-debugging-port=${port}`, '--remote-allow-origins=*', `--user-data-dir=${profile}`, 'about:blank',
], { windowsHide: true, stdio: 'ignore' })
const sleep = ms => new Promise(resolve => setTimeout(resolve, ms))
async function until(fn) { for (let i = 0; i < 220; i++) { const result = await fn(); if (result) return result; await sleep(100) } throw new Error('Browser test timed out') }
const connections = []
async function connect(page) {
  const socket = new WebSocket(page.webSocketDebuggerUrl), pending = new Map(); let id = 0
  await new Promise(resolve => socket.addEventListener('open', resolve, { once: true }))
  socket.addEventListener('message', ({ data }) => { const msg = JSON.parse(data), waiter = pending.get(msg.id); if (!waiter) return; pending.delete(msg.id); msg.error ? waiter.reject(new Error(msg.error.message)) : waiter.resolve(msg.result) })
  const command = (method, params = {}) => new Promise((resolve, reject) => { const nextId = ++id; pending.set(nextId, { resolve, reject }); socket.send(JSON.stringify({ id: nextId, method, params })) })
  async function evaluate(expression) { const result = await command('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true }); if (result.exceptionDetails) throw new Error(JSON.stringify(result.exceptionDetails)); return result.result.value }
  const client = { socket, command, evaluate }; connections.push(client); await command('Page.enable'); return client
}
async function click(client, selector) { await client.evaluate(`document.querySelector(${JSON.stringify(selector)}).click()`); await sleep(60) }
async function input(client, selector, value) { await client.evaluate(`(()=>{const el=document.querySelector(${JSON.stringify(selector)});el.value=${JSON.stringify(value)};el.dispatchEvent(new Event('input',{bubbles:true}));})()`); await sleep(30) }
const submit = client => click(client, '.lobby-dialog button[type="submit"]')
async function screenshot(client, label) { const result = await client.command('Page.captureScreenshot', { format: 'png' }); await writeFile(`tests/artifacts/pvp-entry/${label}.png`, Buffer.from(result.data, 'base64')) }
async function layout(client, width, height, selector) {
  await client.command('Page.bringToFront')
  await client.command('Emulation.setDeviceMetricsOverride', { width, height, deviceScaleFactor: 1, mobile: false }); await sleep(160)
  const result = await client.evaluate(`(()=>{ const stage=document.querySelector('.is-entry-stage'), els=[...document.querySelectorAll(${JSON.stringify(selector)})];return { stageOverflow:stage.scrollWidth>stage.clientWidth+1, elements:els.map(el=>{const r=el.getBoundingClientRect();return {left:r.left,right:r.right,width:r.width,overflow:el.scrollWidth>el.clientWidth+1}}),transform:getComputedStyle(stage).transform }; })()`)
  assert.equal(result.stageOverflow, false, JSON.stringify(result)); assert.notEqual(result.transform, 'none')
  assert.ok(result.elements.every(r => r.left >= 0 && r.right <= width + 1 && !r.overflow), JSON.stringify(result))
  return { width, height, ...result }
}
let hostRoom, guestClientId, hostClientId
try {
  const hostPage = await until(async () => { try { return (await (await fetch(`http://127.0.0.1:${port}/json/list`)).json()).find(p => p.type === 'page') } catch { return null } })
  const host = await connect(hostPage)
  await host.command('Page.navigate', { url }); await until(() => host.evaluate(`!!document.querySelector('[data-mode="pvp"]')`))
  await mkdir('tests/artifacts/pvp-entry', { recursive: true })
  const layouts = []
  for (const [width, height] of [[1280, 900], [390, 844], [320, 640], [844, 390]]) {
    layouts.push(await layout(host, width, height, '.mode-card'))
    const order = await host.evaluate(`(()=>{const cards=[...document.querySelectorAll('.mode-card')]; return cards.every((c,i)=>!i||c.offsetTop>cards[i-1].offsetTop+cards[i-1].offsetHeight)})()`)
    assert.ok(order); await screenshot(host, `home-${width}`)
  }
  await host.command('Emulation.setDeviceMetricsOverride', { width: 390, height: 844, deviceScaleFactor: 1, mobile: false })
  await click(host, '[data-mode="pvp"]'); await until(() => host.evaluate(`!!document.querySelector('#pvp-nickname')`))
  for (const name of ['', 'aI 1号', 'A I-2号', 'ＡＩ３号', '牌友AI四号']) {
    await input(host, '#pvp-nickname', name); await submit(host)
    assert.ok(await host.evaluate(`!!document.querySelector('.dialog-error').textContent.trim()`), name)
    assert.ok(await host.evaluate(`!!document.querySelector('#pvp-nickname')`))
  }
  await input(host, '#pvp-nickname', '西窗牌友'); await submit(host)
  await until(() => host.evaluate(`!document.querySelector('.lobby-dialog')`))
  await click(host, '.entry-action:first-child'); await click(host, '.capacity-options button:nth-child(2)')
  layouts.push(await layout(host, 320, 640, '.lobby-dialog'))
  await submit(host); await until(() => host.evaluate(`!!document.querySelector('.room-number')`))
  hostRoom = await host.evaluate(`document.querySelector('.room-number').textContent.trim()`)
  hostClientId = await host.evaluate(`sessionStorage.getItem('dinglong.pvp.client')`)
  assert.match(hostRoom, /^[0-9]{6}$/)
  assert.ok(await host.evaluate(`location.hash.endsWith(${JSON.stringify(hostRoom)})`))
  assert.equal(await host.evaluate(`document.querySelectorAll('.waiting-seat').length`), 4)

  const { targetId } = await host.command('Target.createTarget', { url: 'about:blank' })
  const guestPage = await until(async () => (await (await fetch(`http://127.0.0.1:${port}/json/list`)).json()).find(p => p.id === targetId))
  const guest = await connect(guestPage)
  await guest.command('Page.navigate', { url: `${url}#/pvp` }); await until(() => guest.evaluate(`!!document.querySelector('#pvp-nickname')`))
  assert.equal(await guest.evaluate(`document.querySelector('#pvp-nickname').value`), '西窗牌友')
  await input(guest, '#pvp-nickname', '南窗来客'); await submit(guest); await click(guest, '.entry-action:nth-child(2)')
  await input(guest, '#pvp-room-id', '12a456'); await submit(guest)
  assert.match(await guest.evaluate(`document.querySelector('.dialog-error').textContent`), /6 位数字/)
  await input(guest, '#pvp-room-id', hostRoom); await submit(guest)
  await until(() => guest.evaluate(`!!document.querySelector('.room-number')`))
  guestClientId = await guest.evaluate(`sessionStorage.getItem('dinglong.pvp.client')`)
  await until(() => host.evaluate(`document.querySelectorAll('.waiting-seat.occupied').length===2`))
  assert.equal(await guest.evaluate(`document.querySelector('.my-seat strong').textContent`), '南窗来客')
  assert.equal(await host.evaluate(`document.querySelector('.my-seat strong').textContent`), '西窗牌友')
  assert.equal(await guest.evaluate(`!!document.querySelector('.pve-discard-hud,.game-status-hint')`), false)
  for (const [width, height] of [[1280, 900], [390, 844], [320, 640]]) {
    layouts.push(await layout(host, width, height, '.waiting-table,.waiting-seat')); await screenshot(host, `room-${width}`)
  }
  await click(guest, '.waiting-footer .quiet-button'); await click(guest, '.lobby-dialog .primary-button')
  await until(() => guest.evaluate(`!!document.querySelector('.pvp-dissolved-dialog')&&!!document.querySelector('[data-mode="pvp"]')`))
  guestClientId = null
  await until(() => host.evaluate(`!!document.querySelector('.pvp-dissolved-dialog')&&!!document.querySelector('[data-mode="pvp"]')`))
  await click(host, '[data-dismiss-room]')
  await until(() => host.evaluate(`!!document.querySelector('[data-mode="pvp"]')`))
  hostClientId = null
  await click(host, '[data-mode="pve"]'); assert.ok(await host.evaluate(`!!document.querySelector('[aria-label="人机对战设置"]')`))
  console.log(JSON.stringify({ status: 'passed', roomId: hostRoom, scenarios: ['nickname validation', 'capacity choice', 'create', 'join', 'live synchronization', 'leave dissolves room', 'PvE entry preserved'], layouts }, null, 2))
} finally {
  for (const client_id of [guestClientId, hostClientId]) if (hostRoom && client_id) {
    try { await fetch(`http://127.0.0.1:8000/api/rooms/${hostRoom}/leave`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ client_id }) }) } catch {}
  }
  if (connections[0]?.socket.readyState === WebSocket.OPEN) { try { await connections[0].command('Browser.close') } catch {} }
  for (const client of connections) client.socket.close()
  chrome.kill()
}
