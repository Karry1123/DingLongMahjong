import assert from 'node:assert/strict'
import { spawn } from 'node:child_process'
import { mkdir, mkdtemp, writeFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'

// Uses the isolated loopback fixtures in backend/tests/pvp_phase4_server.py.
const url = process.env.PVP_URL || 'http://127.0.0.1:5182/'
const browsers=[], clients=[], errors=[]
const sleep=ms=>new Promise(resolve=>setTimeout(resolve,ms))
async function until(fn) { for(let i=0;i<250;i++){const r=await fn();if(r)return r;await sleep(80)}throw new Error('Browser test timed out') }
async function launch(port){
  const profile=await mkdtemp(join(tmpdir(),'dinglong-clocks-'))
  const chrome=spawn('C:/Program Files/Google/Chrome/Application/chrome.exe',['--headless=new','--disable-gpu','--no-first-run','--no-default-browser-check',`--remote-debugging-port=${port}`,'--remote-allow-origins=*',`--user-data-dir=${profile}`,'about:blank'],{windowsHide:true,stdio:'ignore'})
  browsers.push(chrome)
  const page=await until(async()=>{try{return(await(await fetch(`http://127.0.0.1:${port}/json/list`)).json()).find(p=>p.type==='page')}catch{return null}})
  const socket=new WebSocket(page.webSocketDebuggerUrl), pending=new Map();let id=0
  await new Promise(resolve=>socket.addEventListener('open',resolve,{once:true}))
  socket.addEventListener('message',({data})=>{const msg=JSON.parse(data);if(msg.method==='Runtime.exceptionThrown')errors.push(msg.params.exceptionDetails);const waiter=pending.get(msg.id);if(!waiter)return;pending.delete(msg.id);msg.error?waiter.reject(new Error(msg.error.message)):waiter.resolve(msg.result)})
  const command=(method,params={})=>new Promise((resolve,reject)=>{const requestId=++id;pending.set(requestId,{resolve,reject});socket.send(JSON.stringify({id:requestId,method,params}))})
  async function evaluate(expression){const r=await command('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true});if(r.exceptionDetails)throw new Error(JSON.stringify(r.exceptionDetails));return r.result.value}
  const client={socket,command,evaluate};clients.push(client)
  await command('Page.enable');await command('Runtime.enable');await command('Emulation.setDeviceMetricsOverride',{width:1280,height:1000,deviceScaleFactor:1,mobile:false});await command('Page.navigate',{url})
  await until(()=>evaluate(`!!document.querySelector('[data-mode="pvp"]')`));return client
}
async function click(client,selector){
  const point=await client.evaluate(`(()=>{const el=document.querySelector(${JSON.stringify(selector)});if(!el||el.disabled)throw new Error('Unavailable '+${JSON.stringify(selector)});const r=el.getBoundingClientRect();return {x:r.left+r.width/2,y:r.top+r.height/2}})()`)
  await client.command('Input.dispatchMouseEvent',{type:'mousePressed',button:'left',clickCount:1,...point});await client.command('Input.dispatchMouseEvent',{type:'mouseReleased',button:'left',clickCount:1,...point});await sleep(60)
}
async function input(client,selector,value){await client.evaluate(`(()=>{const el=document.querySelector(${JSON.stringify(selector)});el.value=${JSON.stringify(value)};el.dispatchEvent(new Event('input',{bubbles:true}))})()`)}
async function enter(client,name){await click(client,'[data-mode="pvp"]');await until(()=>client.evaluate(`!!document.querySelector('#pvp-nickname')`));await input(client,'#pvp-nickname',name);await click(client,'.lobby-dialog button[type="submit"]')}
async function joinRoom(client,id){await click(client,'.entry-action:nth-child(2)');await input(client,'#pvp-room-id',id);await click(client,'.lobby-dialog button[type="submit"]');await until(()=>client.evaluate(`!!document.querySelector('.ready-button')&&!document.querySelector('.ready-button').disabled`))}
async function start(name){
  for(const [i,c]of clients.entries())await enter(c,i===0?name:`时钟牌友${i}`)
  await click(clients[0],'.entry-action:first-child');await click(clients[0],'.capacity-options button:nth-child(2)');await click(clients[0],'.lobby-dialog button[type="submit"]')
  await until(()=>clients[0].evaluate(`!!document.querySelector('.ready-button')`))
  const id=await clients[0].evaluate(`document.querySelector('.room-number').textContent.trim()`)
  await joinRoom(clients[1],id);await joinRoom(clients[2],id)
  for(const c of clients)await click(c,'.ready-button')
  for(const c of clients)await until(()=>c.evaluate(`!!document.querySelector('.pvp-game-table')&&!document.querySelector('.god-opening')&&document.querySelector('.pvp-game-table').dataset.phase!=='opening'`))
  return id
}
async function leave(){
  const selector = await clients[0].evaluate(`document.querySelector('.pvp-result') ? '.pvp-result .settlement-leave' : '.pvp-game-header button:last-child'`)
  await click(clients[0],selector);await until(()=>clients[0].evaluate(`!!document.querySelector('.lobby-dialog .primary-button')`));await click(clients[0],'.lobby-dialog .primary-button')
  for(const c of clients){await until(()=>c.evaluate(`!!document.querySelector('.pvp-dissolved-dialog')&&!!document.querySelector('[data-mode="pvp"]')`));assert.match(await c.evaluate(`document.querySelector('.pvp-dissolved-dialog').textContent`),/玩家 .*退出，房间已解散/);assert.equal(await c.evaluate(`location.hash`),'');await click(c,'[data-dismiss-room]')}
}
async function shot(client,name){const r=await client.command('Page.captureScreenshot',{format:'png'});await writeFile(`tests/artifacts/pvp-privacy-fullscreen/${name}.png`,Buffer.from(r.data,'base64'))}

const latest=new Map()
async function passive(client){
  const state=await client.evaluate(`(()=>({wait:document.querySelector('.pvp-response-wait')?.textContent,seconds:document.querySelector('[data-public-response-seconds]')?.textContent,clocks:[...document.querySelectorAll('[data-clock-wind]')].map(el=>el.dataset.clockWind),thoughts:document.querySelectorAll('.thinking-indicator').length,bank:document.querySelector('[data-bank-wind="S"] b').textContent}))()`)
  assert.match(state.wait,/等待其余玩家决策中/);assert.deepEqual(state.clocks,[]);assert.equal(state.thoughts,0);assert.equal(state.bank,'—')
  const wire=latest.get(client)
  assert.deepEqual(wire.clocks,{});assert.equal(wire.time_banks.S,null)
  assert.deepEqual(wire.actions,[])
  return state
}
try{
  await mkdir('tests/artifacts/pvp-privacy-fullscreen',{recursive:true})
  await launch(9461);await launch(9462);await launch(9463)
  const [east,south,west]=clients
  for(const client of clients){
    client.socket.addEventListener('message',({data})=>{const msg=JSON.parse(data);if(msg.method==='Network.webSocketFrameReceived'){const frame=JSON.parse(msg.params.response.payloadData);if(frame.type==='room_state'&&frame.game)latest.set(client,frame.game)}})
    await client.command('Network.enable')
  }
  await south.command('Emulation.setDeviceMetricsOverride',{width:390,height:844,deviceScaleFactor:1,mobile:true})
  await south.command('Emulation.setTouchEmulationEnabled',{enabled:true,maxTouchPoints:1})
  await west.command('Emulation.setDeviceMetricsOverride',{width:390,height:844,deviceScaleFactor:1,mobile:true})
  await west.command('Emulation.setTouchEmulationEnabled',{enabled:true,maxTouchPoints:1})
  await west.command('Network.setUserAgentOverride',{userAgent:'Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 Mobile/15E148 MicroMessenger/8.0'})
  await west.command('Page.addScriptToEvaluateOnNewDocument',{source:`window.__fullAttempts=0;Element.prototype.requestFullscreen=()=>{window.__fullAttempts++;return Promise.reject(new TypeError('WebView policy'))}`})
  await west.command('Page.reload');await until(()=>west.evaluate(`!!document.querySelector('[data-mode="pvp"]')`))
  await start('隐私房主')
  await until(()=>south.evaluate(`!!document.fullscreenElement||!!document.webkitFullscreenElement`))
  assert.ok(await west.evaluate(`window.__fullAttempts>=1&&document.documentElement.classList.contains('pvp-immersive-fullscreen')`))
  const phone=await west.evaluate(`(()=>{const el=document.querySelector('.viewport-wrapper'),r=el.getBoundingClientRect(),ev=new Event('touchmove',{bubbles:true,cancelable:true});el.dispatchEvent(ev);return {fixed:getComputedStyle(el).position,z:getComputedStyle(el).zIndex,fits:r.left===0&&r.top===0&&Math.abs(r.width-innerWidth)<1&&Math.abs(r.height-innerHeight)<1,blocked:ev.defaultPrevented,noScroll:document.documentElement.scrollWidth<=innerWidth&&document.documentElement.scrollHeight<=innerHeight}})()`)
  assert.ok(phone.fixed==='fixed'&&phone.z==='9999'&&phone.fits&&phone.blocked&&phone.noScroll)
  await shot(west,'wechat-immersive')
  // The manual toggle remains usable even when the native API is rejected.
  await west.evaluate(`[...document.querySelectorAll('.pvp-game-header button')].find(b=>b.textContent==='退出全屏').click()`)
  assert.equal(await west.evaluate(`document.documentElement.classList.contains('pvp-immersive-fullscreen')`),false)
  await west.evaluate(`[...document.querySelectorAll('.pvp-game-header button')].find(b=>b.textContent==='⛶ 全屏').click()`)
  await until(()=>west.evaluate(`document.documentElement.classList.contains('pvp-immersive-fullscreen')`))
  await click(east,'.pve-drawn-slot button[role="listitem"]')
  await until(()=>south.evaluate(`!!document.querySelector('[data-action="pong"]')`))
  assert.match(await south.evaluate(`document.querySelector('[data-clock-wind="S"]').textContent`),/响应/)
  assert.equal(await south.evaluate(`document.querySelectorAll('[data-clock-wind]').length`),1)
  assert.equal(latest.get(south).clocks.S.kind,'response')
  const a=await passive(east),c=await passive(west)
  assert.ok(Number.parseInt(a.seconds)<=6&&Number.parseInt(c.seconds)<=6)
  assert.deepEqual(latest.get(east).response_wait,latest.get(west).response_wait)
  await shot(east,'discarder-neutral-wait');await shot(west,'observer-neutral-wait');await shot(south,'respondent-own-clock')
  await sleep(8500)
  assert.equal(await south.evaluate(`document.querySelector('[data-clock-wind="S"]').dataset.timerStage`),'bank')
  await passive(east);await passive(west)
  assert.ok(latest.get(south).time_banks.S<30000)
  await click(south,'[data-action="pass"]')
  await until(()=>east.evaluate(`document.querySelector('.pvp-game-table').dataset.phase==='discard'`))
  for(const client of clients){assert.equal(await client.evaluate(`!!document.querySelector('.pvp-response-wait')`),false);assert.ok(await client.evaluate(`!!document.querySelector('[data-clock-wind="S"]')`))}
  await leave()
  assert.equal(await west.evaluate(`document.documentElement.classList.contains('pvp-immersive-fullscreen')`),false)
  const ev=await west.evaluate(`(()=>{const ev=new Event('touchmove',{bubbles:true,cancelable:true});document.dispatchEvent(ev);return ev.defaultPrevented})()`)
  assert.equal(ev,false);assert.deepEqual(errors,[])
  console.log(JSON.stringify({status:'passed',threeIndependentBrowsers:true,nativeMobileFullscreen:true,wechatFallback:phone,privateResponseAndBank:true,neutralWaitSeconds:6,cleanup:true},null,2))
}finally{
  for(const client of clients)if(client.socket.readyState===WebSocket.OPEN){try{await client.command('Browser.close')}catch{}client.socket.close()}
  for(const browser of browsers)browser.kill()
}
