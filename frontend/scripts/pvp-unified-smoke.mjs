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
async function shot(client, label) { const screenshot = await client.command('Page.captureScreenshot', { format: 'png' }); await writeFile(`tests/artifacts/pvp-unified/${label}.png`, Buffer.from(screenshot.data, 'base64')) }

const expected={E:{bottom:'E',top:'W',left:'N',right:'S'},S:{bottom:'S',top:'N',left:'E',right:'W'},W:{bottom:'W',top:'E',left:'S',right:'N'},N:{bottom:'N',top:'S',left:'W',right:'E'}}
async function inspect(client, wind, phase) {
  const value=await client.evaluate(`(()=>{
    const stage=document.querySelector('.game-stage'),m=new DOMMatrix(getComputedStyle(stage).transform),r=stage.getBoundingClientRect(),det=m.a*m.d-m.b*m.c;
    const local=el=>{const b=el.getBoundingClientRect(),dx=(b.left+b.right-r.left-r.right)/2,dy=(b.top+b.bottom-r.top-r.bottom)/2;return {x:stage.offsetWidth/2+(m.d*dx-m.c*dy)/det,y:stage.offsetHeight/2+(-m.b*dx+m.a*dy)/det}};
    const playing=!!document.querySelector('.pvp-game-table');
    return {stage:[stage.offsetWidth,stage.offsetHeight],rotated:Math.abs(m.b)>Math.abs(m.a),portrait:innerHeight>innerWidth,
      scroll:stage.scrollWidth>stage.clientWidth+1||stage.scrollHeight>stage.clientHeight+1||document.documentElement.scrollHeight>innerHeight+1||document.documentElement.scrollWidth>innerWidth+1,
      shared:playing&&!!document.querySelector('.pve-game-main>.pve-table')&&!!document.querySelector('.pve-workbench .pve-self-hand .pve-hand-anchor'),
      noEV:!document.querySelector('.pve-ev-slot,.pve-discard-hud,.action-recommend-badge'),
      positions:playing?Object.fromEntries([...document.querySelectorAll('.round-player,.self-player-caption')].map(el=>[el.dataset.position,el.dataset.wind])):null,
      selfBottom:playing?local(document.querySelector('.pvp-own-hand')).y>local(document.querySelector('.pve-table')).y:false,
      inViewport:[...document.querySelectorAll('.waiting-seat,.pvp-own-hand,.pve-table,.pvp-topbar,.mode-card')].every(el=>{const b=el.getBoundingClientRect();return b.left>=-1&&b.top>=-1&&b.right<=innerWidth+1&&b.bottom<=innerHeight+1}),
      topbarOverflow:playing&&document.querySelector('.pvp-game-header').scrollWidth>document.querySelector('.pvp-game-header').clientWidth+1,
      labels:playing?[...document.querySelectorAll('.player-caption')].map(el=>el.textContent):[],
      handCount:document.querySelectorAll('.pvp-own-hand [aria-label="手牌槽位"] .mahjong-tile').length,
      singleLine:!playing||getComputedStyle(document.querySelector('.pvp-progress-hint')).whiteSpace==='nowrap'};
  })()`)
  assert.deepEqual(value.stage,[1280,720]);assert.equal(value.rotated,value.portrait);assert.equal(value.scroll,false,JSON.stringify(value));assert.equal(value.inViewport,true,JSON.stringify(value))
  if(wind){assert.equal(value.shared,true);assert.deepEqual(value.positions,expected[wind]);assert.ok(value.noEV&&value.selfBottom&&value.singleLine);assert.equal(value.topbarOverflow,false,JSON.stringify(value))}
  await shot(client,phase)
  return value
}
const results=[],requests=[],errors=[]
try {
  await mkdir('tests/artifacts/pvp-unified',{recursive:true})
  const first=await launch(9431),second=await launch(9432)
  for(const client of clients){
    client.socket.addEventListener('message',({data})=>{const m=JSON.parse(data);if(m.method==='Runtime.exceptionThrown')errors.push(m.params.exceptionDetails);if(m.method==='Network.requestWillBeSent')requests.push(m.params.request.url)})
    await client.command('Runtime.enable');await client.command('Network.enable')
  }
  if(process.env.PVP_LAN_ORIGIN){await second.command('Page.navigate',{url:process.env.PVP_LAN_ORIGIN});await until(()=>second.evaluate(`!!document.querySelector('[data-mode="pvp"]')`))}
  await second.command('Emulation.setDeviceMetricsOverride',{width:390,height:844,deviceScaleFactor:1,mobile:true});await sleep(200)
  await inspect(first,null,'home-desktop');await inspect(second,null,'home-phone')
  await click(first,'[data-mode="pvp"]')
  assert.equal(await first.evaluate(`document.querySelector('#pvp-nickname').maxLength`),6)
  await input(first,'#pvp-nickname','七字昵称不允许');assert.equal(await first.evaluate(`document.querySelector('#pvp-nickname').value`),'七字昵称不允')
  await input(first,'#pvp-nickname','AI 1号');await click(first,'.lobby-dialog button[type="submit"]');assert.match(await first.evaluate(`document.querySelector('.dialog-error').textContent`),/系统保留/)
  await input(first,'#pvp-nickname','顶龙真人牌友');await click(first,'.lobby-dialog button[type="submit"]')
  await enterLobby(second,'六字真人牌友')
  for(const [a,b] of [['E','S'],['W','N']]) {
    const id=await createRoom(first,2)
    if(a!=='E')await click(first,'[data-seat="W"]')
    await joinRoom(second,id)
    if(b!=='S')await click(second,'[data-seat="N"]')
    for(const c of clients)await until(()=>c.evaluate(`document.querySelectorAll('.occupied:not(.ai-seat)').length===2`))
    await inspect(first,null,`waiting-${a}`);await inspect(second,null,`waiting-phone-${b}`)
    const geometry=()=>second.evaluate(`Object.fromEntries([...document.querySelectorAll('.waiting-seat')].map(el=>{const r=el.getBoundingClientRect();return[el.dataset.seat,[r.x,r.y,r.width,r.height]]}))`)
    const baseline=await geometry()
    for(const target of b==='S'?['N','W','S']:['S','E','N']){await click(second,`[data-seat="${target}"]`);await until(()=>second.evaluate(`document.querySelector('.my-seat').dataset.seat===${JSON.stringify(target)}`));assert.deepEqual(await geometry(),baseline)}
    await click(first,'.ready-button');await click(second,'.ready-button')
    await until(()=>first.evaluate(`!!document.querySelector('.god-opening-reveal')`))
    await shot(second,`god-phone-${b}`)
    await until(()=>first.evaluate(`!document.querySelector('.god-opening')&&document.querySelector('.pvp-game-table')?.dataset.phase!=='opening'`))
    await until(()=>second.evaluate(`!document.querySelector('.god-opening')`))
    const firstView=await inspect(first,a,`game-${a}`),secondView=await inspect(second,b,`game-phone-${b}`)
    assert.equal(await first.evaluate(`document.querySelector('.pvp-game-table').dataset.gameId`),await second.evaluate(`document.querySelector('.pvp-game-table').dataset.gameId`))
    if(a==='E'){
      const tile=await first.evaluate(`document.querySelector('.pve-drawn-slot .mahjong-tile').dataset.tile`)
      await click(first,'.pve-drawn-slot button[role="listitem"]')
      await until(()=>second.evaluate(`document.querySelector('[data-river-wind="E"] .mahjong-tile')?.dataset.tile===${JSON.stringify(tile)}`))
      assert.equal(await first.evaluate(`document.querySelectorAll('.pvp-own-hand [aria-label="手牌槽位"] .mahjong-tile').length`),13)
    }
    for(const [width,height] of [[1920,1080],[960,540],[1280,900],[390,844],[320,640],[844,390]]){
      await first.command('Emulation.setDeviceMetricsOverride',{width,height,deviceScaleFactor:1,mobile:width<500});await sleep(130)
      await inspect(first,a,`${a}-${width}x${height}`)
    }
    // Trusted click preserves the browser user activation required by fullscreen.
    await first.command('Emulation.setDeviceMetricsOverride',{width:1280,height:900,deviceScaleFactor:1,mobile:false});await sleep(100)
    const point=await first.evaluate(`(()=>{const r=document.querySelector('.pvp-game-header button:nth-last-child(2)').getBoundingClientRect();return{x:r.left+r.width/2,y:r.top+r.height/2}})()`)
    await first.command('Input.dispatchMouseEvent',{type:'mousePressed',button:'left',clickCount:1,...point});await first.command('Input.dispatchMouseEvent',{type:'mouseReleased',button:'left',clickCount:1,...point})
    await until(()=>first.evaluate(`!!document.fullscreenElement`));await inspect(first,a,`${a}-fullscreen`)
    await first.evaluate(`document.exitFullscreen()`)
    results.push({winds:[a,b],firstView,secondView,nicknameLimit:6,stableSeats:true,fullscreen:true})
    await click(first,'.pvp-game-header button:last-child');await click(first,'.lobby-dialog .primary-button')
    for(const client of clients){await until(()=>client.evaluate(`!!document.querySelector('.pvp-dissolved-dialog')`));await click(client,'[data-dismiss-room]')}
    await enterLobby(first,'顶龙真人牌友');await enterLobby(second,'六字真人牌友')
  }
  assert.deepEqual(errors,[]);assert.ok(!requests.some(r=>/\/api\/(recommend|opponent-threats)/.test(r)))
  console.log(JSON.stringify({status:'passed',noEVRequests:true,desktopAndLanPhone:true,results},null,2))
} finally {
  for(const client of clients)if(client.socket.readyState===WebSocket.OPEN){try{await client.command('Browser.close')}catch{}client.socket.close()}
  for(const browser of browsers)browser.kill()
}
