import assert from 'node:assert/strict'
import { spawn } from 'node:child_process'
import { mkdir, mkdtemp, writeFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'

// Uses the isolated loopback fixtures in backend/tests/pvp_phase4_server.py.
const url = process.env.PVP_URL || 'http://127.0.0.1:5182/'
const browsers=[], clients=[], errors=[]
const sleep=ms=>new Promise(resolve=>setTimeout(resolve,ms))
async function until(fn) { for(let i=0;i<850;i++){const r=await fn();if(r)return r;await sleep(80)}throw new Error('Browser test timed out') }
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
  await click(clients[0],'.entry-action:first-child');await click(clients[0],'.capacity-options button:first-child');await click(clients[0],'.lobby-dialog button[type="submit"]')
  await until(()=>clients[0].evaluate(`!!document.querySelector('.ready-button')`))
  const id=await clients[0].evaluate(`document.querySelector('.room-number').textContent.trim()`)
  await joinRoom(clients[1],id)
  for(const c of clients)await click(c,'.ready-button')
  for(const c of clients)await until(()=>c.evaluate(`!!document.querySelector('.pvp-game-table')&&!document.querySelector('.god-opening')&&document.querySelector('.pvp-game-table').dataset.phase!=='opening'`))
  return id
}
async function leave(){
  const selector = await clients[0].evaluate(`document.querySelector('.pvp-result') ? '.pvp-result .settlement-leave' : '.pvp-game-header button:last-child'`)
  await click(clients[0],selector);await until(()=>clients[0].evaluate(`!!document.querySelector('.lobby-dialog .primary-button')`));await click(clients[0],'.lobby-dialog .primary-button')
  for(const c of clients){await until(()=>c.evaluate(`!!document.querySelector('.pvp-dissolved-dialog')&&!!document.querySelector('[data-mode="pvp"]')`));assert.match(await c.evaluate(`document.querySelector('.pvp-dissolved-dialog').textContent`),/玩家 .*退出，房间已解散/);assert.equal(await c.evaluate(`location.hash`),'');await click(c,'[data-dismiss-room]')}
}
async function shot(client,name){const r=await client.command('Page.captureScreenshot',{format:'png'});await writeFile(`tests/artifacts/pvp-time-bank/${name}.png`,Buffer.from(r.data,'base64'))}
const clock=(c,wind)=>c.evaluate(`document.querySelector('[data-clock-wind="${wind}"]')?.textContent`)
const gameId=c=>c.evaluate(`document.querySelector('.pvp-game-table').dataset.gameId`)

const banks=client=>client.evaluate(`Object.fromEntries([...document.querySelectorAll('[data-bank-wind]')].map(el=>[el.dataset.bankWind,Number(el.querySelector('b').textContent)]))`)
const stage=(client,wind)=>client.evaluate(`document.querySelector('[data-clock-wind="${wind}"]')?.dataset.timerStage`)
const logs=new Map(),results=[]
async function allBanks(){const own={};for(const c of clients){const wind=await c.evaluate(`document.querySelector('.pvp-game-table').dataset.selfWind`);own[wind]=(await banks(c))[wind]}return own}
async function time(client,wind){return client.evaluate(`Number(document.querySelector('[data-clock-wind="${wind}"] b')?.textContent)`)}
try {
  await mkdir('tests/artifacts/pvp-time-bank',{recursive:true})
  await launch(9441);await launch(9442)
  const [east,south]=clients
  await south.command('Emulation.setDeviceMetricsOverride',{width:390,height:844,deviceScaleFactor:1,mobile:true})
  for(const c of clients){
    logs.set(c,[])
    c.socket.addEventListener('message',({data})=>{
      const msg=JSON.parse(data)
      if(msg.method==='Network.webSocketFrameReceived'){
        const frame=JSON.parse(msg.params.response.payloadData)
        if(frame.type==='room_state'&&frame.game)logs.get(c).push({at:Date.now(),serverAt:frame.server_time,game:frame.game})
      }
    })
    await c.command('Network.enable')
  }
  await start('计时房主')
  for(const c of clients)assert.equal(await c.evaluate(`document.querySelectorAll('[data-bank-wind]').length`),4)
  assert.deepEqual(await allBanks(),{E:30,S:30})
  await until(()=>east.evaluate(`document.querySelector('[data-seat-timer="E"]').classList.contains('is-critical')`))
  await shot(east,'regular-low-time-red')
  await until(async()=>await stage(east,'E')==='bank'&&await stage(south,'E')==='bank')
  assert.ok(await time(east,'E')>=29)
  await sleep(2300)
  assert.ok((await banks(east)).E<=28)
  await shot(east,'bank-active-desktop');await shot(south,'bank-active-phone')
  await click(east,'.pve-drawn-slot button[role="listitem"]')
  await until(()=>south.evaluate(`document.querySelector('[data-clock-wind="S"]')?.dataset.paused==='true'`))
  const response=logs.get(east).findLast(row=>row.game.phase==='response')
  assert.ok(response)
  const frozen=(await banks(east)).E
  assert.ok(frozen>=26&&frozen<=28)
  assert.equal((await banks(south)).S,30)
  await until(()=>east.evaluate(`document.querySelectorAll('[data-meld-wind="W"] .mahjong-tile').length===3`))
  const pong=logs.get(east).findLast(row=>row.game.event?.action==='PONG'&&row.game.event.seat==='W')
  const pongMs=pong.serverAt-response.game.response_wait.started_at
  assert.ok(pongMs>=2900&&pongMs<3900,`AI claim ${pongMs}ms`)
  await shot(south,'ai-discard-clock-visible-to-peer')
  await until(()=>east.evaluate(`!!document.querySelector('[data-river-wind="W"] .mahjong-tile')`))
  const discard=logs.get(east).findLast(row=>row.game.event?.action==='DISCARD'&&row.game.event.seat==='W')
  const discardMs=discard.serverAt-pong.game.clocks.W.started_at
  assert.ok(discardMs>=5900&&discardMs<6900,`AI discard ${discardMs}ms`)
  assert.equal((await banks(east)).E,frozen)
  assert.ok(Number.isNaN((await banks(south)).E),'hidden response banks must not reveal the previous discarder')
  results.push({scenario:'10s seamlessly enters reserve; action preserves remaining bank; paused chi never drains',preservedSeconds:frozen,aiClaimMs:pongMs,aiDiscardMs:discardMs})
  console.log('Passed real base-to-bank handover, stopped reserve, 3s AI claim and 6s AI discard.')
  await leave()

  await start('耗尽房主')
  const startAt=logs.get(east).findLast(row=>row.game.clocks.E?.kind==='discard').game.clocks.E.started_at
  await until(()=>east.evaluate(`!!document.querySelector('[data-river-wind="E"] .mahjong-tile')`))
  const expired=logs.get(east).findLast(row=>row.game.event?.action==='DISCARD'&&row.game.event.seat==='E')
  assert.ok(expired.serverAt-startAt>=39900&&expired.serverAt-startAt<40900)
  assert.equal((await banks(east)).E,0);assert.ok(Number.isNaN((await banks(south)).E))
  await shot(east,'reserve-exhausted-auto-discard')
  // Let the two AIs finish their actual paced turns, passing any human claims.
  for(let i=0;i<400;i++){
    if(await east.evaluate(`document.querySelector('.pvp-game-table').dataset.phase==='discard'&&!!document.querySelector('[data-clock-wind="E"]')`))break
    for(const c of clients)if(await c.evaluate(`!!document.querySelector('[data-action="pass"]:not(:disabled)')`))await click(c,'[data-action="pass"]:not(:disabled)')
    await sleep(100)
  }
  const next=logs.get(east).findLast(row=>row.game.phase==='discard'&&row.game.current_turn==='E')
  assert.ok(next&&next.game.clocks.E)
  assert.equal(next.game.time_banks.E,0)
  assert.equal(next.game.clocks.E.deadline-next.game.clocks.E.started_at,10000)
  await until(()=>logs.get(east).some(row=>row.serverAt>=next.game.clocks.E.started_at&&row.game.event?.action==='DISCARD'&&row.game.event.seat==='E'))
  const second=logs.get(east).findLast(row=>row.game.event?.action==='DISCARD'&&row.game.event.seat==='E')
  assert.ok(second.serverAt-next.game.clocks.E.started_at>=9900&&second.serverAt-next.game.clocks.E.started_at<10900)
  results.push({scenario:'40s final expiry auto-discards; future turn has only 10s',firstExpiryMs:expired.serverAt-startAt,subsequentExpiryMs:second.serverAt-next.game.clocks.E.started_at})
  console.log('Passed real 40s reserve exhaustion and next-turn 10s-only fallback.')
  await leave()

  await start('加时和牌房主')
  assert.ok(await east.evaluate(`!!document.querySelector('[data-action="self_draw_win"]')`))
  const huStart=logs.get(east).findLast(row=>row.game.clocks.E?.kind==='win').game.clocks.E.started_at
  await until(async()=>await stage(east,'E')==='bank')
  assert.ok(await east.evaluate(`!!document.querySelector('[data-action="self_draw_win"]')`))
  await until(()=>east.evaluate(`!!document.querySelector('.pvp-result')`))
  const finished=logs.get(east).findLast(row=>row.game.phase==='finished')
  assert.ok(finished.serverAt-huStart>=35900&&finished.serverAt-huStart<36900)
  assert.match(await south.evaluate(`document.querySelector('#pvp-result-title').textContent`),/自摸/)
  await click(east,'.next-round-button');await click(south,'.next-round-button')
  await until(()=>east.evaluate(`!!document.querySelector('.god-opening-reveal')`))
  assert.deepEqual(await allBanks(),{E:30,S:30})
  results.push({scenario:'6s win response enters reserve; 36s auto-hu; next hand restores all reserves',autoHuMs:finished.serverAt-huStart})
  await until(()=>east.evaluate(`!document.querySelector('.god-opening')`));await leave()
  assert.deepEqual(errors,[])
  console.log(JSON.stringify({status:'passed',independentWindows:2,phonePortrait:true,allSeatsVisible:true,results},null,2))
}finally{
  for(const client of clients)if(client.socket.readyState===WebSocket.OPEN){try{await client.command('Browser.close')}catch{}client.socket.close()}
  for(const browser of browsers)browser.kill()
}
