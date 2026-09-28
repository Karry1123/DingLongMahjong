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
async function shot(client,name){const r=await client.command('Page.captureScreenshot',{format:'png'});await writeFile(`tests/artifacts/pvp-settlement/${name}.png`,Buffer.from(r.data,'base64'))}

try {
  await mkdir('tests/artifacts/pvp-settlement',{recursive:true})
  await launch(9451);await launch(9452)
  const [east,south]=clients
  for(const client of clients){
    // Exercise the browser's real native sentinel; no simulated keep-alive video.
    await client.command('Page.addScriptToEvaluateOnNewDocument',{source:`
      window.__wake={requests:0,active:0};window.__tones=[];
      if(navigator.wakeLock){const original=navigator.wakeLock.request.bind(navigator.wakeLock);
        navigator.wakeLock.request=async(...args)=>{window.__wake.requests++;const lock=await original(...args);window.__wake.active++;window.__lastWake=lock;lock.addEventListener('release',()=>window.__wake.active--);return lock}}
      const oscillator=AudioContext.prototype.createOscillator;
      AudioContext.prototype.createOscillator=function(){const o=oscillator.call(this),start=o.start.bind(o);o.start=(...args)=>{window.__tones.push(o.frequency.value);return start(...args)};return o};
    `})
    await client.command('Page.reload')
    await until(()=>client.evaluate(`!!document.querySelector('[data-mode="pvp"]')`))
  }
  await south.command('Emulation.setDeviceMetricsOverride',{width:390,height:844,deviceScaleFactor:1,mobile:true})
  await start('结算房主')
  assert.ok(await east.evaluate(`window.__tones.includes(660)&&window.__tones.includes(880)`),'local turn did not play the two-tone cue')
  const wakes=await Promise.all(clients.map(c=>c.evaluate(`({...window.__wake,supported:!!navigator.wakeLock,secure:isSecureContext})`)))
  assert.ok(wakes.every(w=>w.supported&&w.secure&&w.active===1),'native wake lock was not retained')
  // Release as the OS does on visibility loss, then verify focus recovery.
  await east.evaluate(`(async()=>{await window.__lastWake.release();window.dispatchEvent(new Event('focus'))})()`)
  await until(()=>east.evaluate(`window.__wake.active===1&&window.__wake.requests>=2`))
  await click(east,'[data-action="self_draw_win"]')
  for(const c of clients)await until(()=>c.evaluate(`!!document.querySelector('.pvp-result')`))
  const layouts=[]
  for(const [client,width,height]of[[east,1280,720],[east,1920,1080],[south,390,844],[south,844,390]]){
    await client.command('Emulation.setDeviceMetricsOverride',{width,height,deviceScaleFactor:1,mobile:width<1000});await sleep(100)
    const result=await client.evaluate(`(()=>{
      const panel=document.querySelector('.game-over-panel'),r=panel.getBoundingClientRect();
      const card=document.querySelector('[data-settlement-wind="S"]');
      const groups=[...card.querySelectorAll('.scoring-group')];
      return {cards:document.querySelectorAll('.landscape-settlement-seat').length,groups:groups.map(g=>({label:g.textContent.trim(),tiles:g.querySelectorAll('.mahjong-tile').length,backs:g.querySelectorAll('.mahjong-tile[data-face-down="true"]').length})),
        fits:r.left>=-1&&r.top>=-1&&r.right<=innerWidth+1&&r.bottom<=innerHeight+1,
        noHistory:![...document.querySelectorAll('.pvp-result button')].some(b=>/复盘|历史/.test(b.textContent)),
        logical:[panel.offsetWidth,panel.offsetHeight],winnerTiles:document.querySelectorAll('.landscape-winner-group .mahjong-tile').length,
        winBadge:!!document.querySelector('.is-winning-tile'),title:document.querySelector('#pvp-result-title').textContent,
        id:document.querySelector('.landscape-settlement-id').textContent,
        noDeadTiles:!card.querySelector('.landscape-seat-tiles'),confirmed:document.querySelector('.next-ready-count').textContent};
    })()`)
    assert.equal(result.cards,4);assert.equal(result.groups.length,4)
    assert.deepEqual(result.groups.map(g=>g.tiles).sort(),[2,2,3,4])
    assert.equal(result.groups.find(g=>g.tiles===4).backs,3)
    assert.ok(result.groups.every(g=>/胡/.test(g.label)))
    assert.ok(result.fits&&result.noHistory&&result.noDeadTiles&&result.winnerTiles===14&&result.winBadge)
    assert.deepEqual(result.logical,[1080,560]);assert.match(result.title,/结算房主.*自摸/);assert.match(result.id,/GM-/)
    assert.equal(result.confirmed,'(0/2)');layouts.push({width,height,...result})
    await shot(client,`settlement-${width}x${height}`)
  }
  await click(east,'.next-round-button')
  await until(()=>south.evaluate(`document.querySelector('.next-ready-count').textContent==='(1/2)'`))
  assert.ok(await east.evaluate(`document.querySelector('.next-round-button').disabled`))
  await click(south,'.next-round-button')
  await until(()=>east.evaluate(`!!document.querySelector('.god-opening')`))
  await until(()=>east.evaluate(`!document.querySelector('.god-opening')`))
  await leave()
  assert.deepEqual(errors,[])
  console.log(JSON.stringify({status:'passed',nativeWakeLock:wakes,turnCue:true,layouts},null,2))
}finally{
  for(const client of clients)if(client.socket.readyState===WebSocket.OPEN){try{await client.command('Browser.close')}catch{}client.socket.close()}
  for(const browser of browsers)browser.kill()
}
