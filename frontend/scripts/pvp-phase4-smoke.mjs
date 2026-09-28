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
async function shot(client,name){const r=await client.command('Page.captureScreenshot',{format:'png'});await writeFile(`tests/artifacts/pvp-phase4/${name}.png`,Buffer.from(r.data,'base64'))}
const clock=(c,wind)=>c.evaluate(`document.querySelector('[data-clock-wind="${wind}"]')?.textContent`)
const gameId=c=>c.evaluate(`document.querySelector('.pvp-game-table').dataset.gameId`)
const results=[]
try {
  await mkdir('tests/artifacts/pvp-phase4',{recursive:true})
  await launch(9391);await launch(9392);await launch(9393)
  const [east,south,west]=clients
  await start('抢断房主')
  assert.match(await clock(east,'E'),/出牌 · 10秒/)
  await until(()=>south.evaluate(`document.querySelector('[data-river-wind="E"] .mahjong-tile')?.dataset.tile==='5m'`))
  assert.equal(await clock(south,'S'),'等待抢断 · 6秒')
  assert.equal(await south.evaluate(`document.querySelector('[data-action="chi"]').disabled`),true)
  await sleep(4000);assert.equal(await clock(south,'S'),'等待抢断 · 6秒')
  await shot(south,'chi-paused');await click(west,'[data-action="pass"]')
  assert.match(await clock(south,'S'),/响应 · 6秒/)
  assert.equal(await south.evaluate(`document.querySelector('[data-action="chi"]').disabled`),false)
  await until(()=>south.evaluate(`!!document.querySelector('.pvp-own-hand button[role="listitem"][aria-disabled="false"]')`))
  assert.equal(await south.evaluate(`document.querySelectorAll('.pvp-own-hand [role="list"] .mahjong-tile').length`),14)
  results.push('10s drawn-tile discard; paused chi keeps 6s; pong pass resumes; chi timeout passes')
  await leave()

  await start('抢断房主')
  await click(east,'.pve-drawn-slot button[role="listitem"]');await click(west,'[data-action="pong"]')
  await until(()=>west.evaluate(`document.querySelectorAll('[data-meld-wind="W"] .mahjong-tile').length===3`))
  assert.equal(await south.evaluate(`!!document.querySelector('[data-action="chi"]')`),false)
  assert.match(await clock(west,'W'),/出牌 · 10秒/)
  await until(()=>east.evaluate(`document.querySelector('[data-river-wind="W"] .mahjong-tile')?.dataset.tile==='P'`))
  results.push('pong interrupts chi immediately; 10s after claim uses legal remaining tile')
  await leave()

  await start('自摸房主')
  assert.match(await east.evaluate(`document.querySelector('[data-action="self_draw_win"]').textContent`),/自摸/)
  assert.match(await clock(east,'E'),/和牌 · 6秒/)
  for(const c of clients)await until(()=>c.evaluate(`!!document.querySelector('.pvp-result')`))
  const old=await gameId(east)
  assert.match(await east.evaluate(`document.querySelector('#pvp-result-title').textContent`),/自摸房主.*自摸/)
  await click(east,'.next-round-button')
  for(const c of clients)assert.equal(await c.evaluate(`document.querySelector('.next-ready-count').textContent`),'(1/3)')
  assert.equal(await east.evaluate(`document.querySelector('.next-round-button').disabled`),true)
  await click(south,'.next-round-button')
  for(const c of clients)assert.equal(await c.evaluate(`document.querySelector('.next-ready-count').textContent`),'(2/3)')
  // Settlement remains legible and bounded on mobile while waiting for the third player.
  for(const width of [390,320]){await south.command('Emulation.setDeviceMetricsOverride',{width,height:844,deviceScaleFactor:1,mobile:false});assert.equal(await south.evaluate(`document.querySelector('.pvp-result').scrollWidth>document.querySelector('.pvp-result').clientWidth+1`),false);await shot(south,`settlement-${width}`)}
  await south.command('Emulation.setDeviceMetricsOverride',{width:1280,height:1000,deviceScaleFactor:1,mobile:false})
  await click(west,'.next-round-button')
  for(const c of clients)await until(()=>c.evaluate(`!!document.querySelector('.god-opening-reveal')`))
  const nextIds=await Promise.all(clients.map(gameId));assert.equal(new Set(nextIds).size,1);assert.notEqual(nextIds[0],old)
  for(const c of clients)await until(()=>c.evaluate(`!document.querySelector('.god-opening')&&document.querySelector('.pvp-game-table').dataset.phase==='discard'`))
  assert.match(await east.evaluate(`document.querySelector('.pvp-game-header').textContent`),/第 2 局/)
  results.push('6s auto self-draw; 1/3 and 2/3 sync; 3/3 starts one shared next hand and ceremony')
  await leave()

  await start('捉铳房主')
  await until(()=>south.evaluate(`!!document.querySelector('[data-action="hu"]')`))
  assert.match(await clock(south,'S'),/和牌 · 6秒/)
  for(const c of clients)await until(()=>c.evaluate(`!!document.querySelector('.pvp-result')`))
  assert.match(await south.evaluate(`document.querySelector('#pvp-result-title').textContent`),/时钟牌友1.*捉/)
  results.push('10s auto discard followed by 6s auto ron on all three windows')
  await leave()

  await start('尾圈房主')
  for(const c of clients)await until(()=>c.evaluate(`!!document.querySelector('.pvp-result')`))
  for(const c of clients)assert.equal(await c.evaluate(`document.querySelector('.next-round-button').textContent`),'开始下一圈')
  await click(east,'.next-round-button');await click(south,'.next-round-button')
  assert.match(await west.evaluate(`document.querySelector('.next-ready-count').textContent`),/2\/3/)
  await click(west,'.next-round-button')
  for(const c of clients)await until(()=>c.evaluate(`!!document.querySelector('.god-opening-reveal')`))
  assert.match(await east.evaluate(`document.querySelector('.pvp-game-header').textContent`),/第 2 圈/)
  for(const c of clients)await until(()=>c.evaluate(`!document.querySelector('.god-opening')`))
  results.push('end-circle confirmation gates all players before circle 2')
  // A real refresh dissolves the room for the two other independent windows.
  await west.command('Page.reload')
  for(const c of [east,south]){await until(()=>c.evaluate(`!!document.querySelector('.pvp-dissolved-dialog')`));assert.match(await c.evaluate(`document.querySelector('.pvp-dissolved-dialog').textContent`),/玩家 时钟牌友2 退出/);assert.ok(await c.evaluate(`!!document.querySelector('[data-mode="pvp"]')`))}
  results.push('refresh broadcasts named dissolution dialog and returns peers to homepage')
  assert.equal(errors.length,0,JSON.stringify(errors))
  console.log(JSON.stringify({status:'passed',independentWindows:3,realDurations:{discard:10,response:6},scenarios:results},null,2))
} finally {
  for(const client of clients)if(client.socket.readyState===WebSocket.OPEN){try{await client.command('Browser.close')}catch{}client.socket.close()}
  for(const browser of browsers)browser.kill()
}
