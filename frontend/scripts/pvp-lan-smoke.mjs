import assert from 'node:assert/strict'
import { spawn } from 'node:child_process'
import { mkdir, mkdtemp, writeFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'

const url = process.env.PVP_URL || 'http://localhost:5173/'
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
      cardinal:e.left<n.left&&w.left>n.left&&n.top<e.top&&s.top>e.top, allInWidth:[e,s,w,n].every(r=>r.left>=0&&r.right<=innerWidth)};
  })()`)
  assert.deepEqual(result, { overflow: false, fourSeats: true, cardinal: true, allInWidth: true })
  await shot(client, `waiting-${width}`)
  return { width, height, ...result }
}
async function seatGeometry(client) {
  return client.evaluate(`Object.fromEntries([...document.querySelectorAll('.waiting-seat')].map(el=>{const r=el.getBoundingClientRect();return [el.dataset.seat,[r.x,r.y,r.width,r.height]]}))`)
}
const lan = process.env.PVP_LAN_ORIGIN
if (!lan) throw new Error('Set PVP_LAN_ORIGIN to this computer\'s current LAN URL, e.g. http://192.168.1.25:5173/')
const requests=[], sockets=[]
try {
  const local=await launch(9421),phone=await launch(9422)
  for(const client of [local,phone]) {
    client.socket.addEventListener('message',({data})=>{
      const message=JSON.parse(data)
      if(message.method==='Network.requestWillBeSent')requests.push(message.params.request.url)
      if(message.method==='Network.webSocketCreated')sockets.push(message.params.url)
    })
    await client.command('Network.enable')
  }
  await phone.command('Emulation.setDeviceMetricsOverride',{width:390,height:844,deviceScaleFactor:1,mobile:true})
  await phone.command('Page.navigate',{url:lan})
  await until(()=>phone.evaluate(`!!document.querySelector('[data-mode="pvp"]')`))
  const joined=[]
  for(const creator of [local,phone]) {
    const guest=creator===local?phone:local
    await enterLobby(local,'电脑牌友');await enterLobby(phone,'手机牌友')
    const id=await createRoom(creator,2);await joinRoom(guest,id)
    for(const client of [local,phone]) {
      await until(()=>client.evaluate(`document.querySelectorAll('.occupied:not(.ai-seat)').length===2`))
      assert.equal(await client.evaluate(`!!document.querySelector('.lobby-error')`),false)
    }
    joined.push({createdFrom:await creator.evaluate('location.origin'),roomId:id,bothConnected:true})
    await click(creator,'.waiting-footer .quiet-button');await click(creator,'.lobby-dialog .primary-button')
    for(const client of [local,phone]) {await until(()=>client.evaluate(`!!document.querySelector('.pvp-dissolved-dialog')`));await click(client,'[data-dismiss-room]')}
  }
  for(const origin of [new URL(url).origin,new URL(lan).origin]) {
    assert.ok(requests.some(request=>request===`${origin}/api/rooms`),`Missing create request from ${origin}`)
    assert.ok(sockets.some(socket=>socket.startsWith(`${origin.replace('http:','ws:')}/api/rooms/`)),`Missing WS from ${origin}`)
  }
  console.log(JSON.stringify({status:'passed',mobileViewport:true,joined,roomRequests:requests.filter(url=>url.endsWith('/api/rooms')),webSocketURLs:sockets.filter(url=>url.includes('/api/rooms/'))},null,2))
} finally {
  for(const client of clients)if(client.socket.readyState===WebSocket.OPEN){try{await client.command('Browser.close')}catch{}client.socket.close()}
  for(const browser of browsers)browser.kill()
}
