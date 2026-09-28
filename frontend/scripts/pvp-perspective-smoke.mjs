import assert from 'node:assert/strict'
import { spawn } from 'node:child_process'
import { mkdir, mkdtemp, writeFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'

const url = process.env.PVP_URL || 'http://127.0.0.1:5178/'
const browsers = [], clients = [], errors = [], requests = []
const sleep = ms => new Promise(resolve => setTimeout(resolve, ms))
async function until(fn) { for (let i=0;i<220;i++) { const result=await fn(); if(result)return result; await sleep(80) } throw new Error('Browser test timed out') }
async function launch(port) {
  const profile=await mkdtemp(join(tmpdir(),'dinglong-perspective-'))
  const chrome=spawn('C:/Program Files/Google/Chrome/Application/chrome.exe',['--headless=new','--disable-gpu','--no-first-run','--no-default-browser-check',`--remote-debugging-port=${port}`,'--remote-allow-origins=*',`--user-data-dir=${profile}`,'about:blank'],{windowsHide:true,stdio:'ignore'})
  browsers.push(chrome)
  const page=await until(async()=>{try{return(await(await fetch(`http://127.0.0.1:${port}/json/list`)).json()).find(p=>p.type==='page')}catch{return null}})
  const socket=new WebSocket(page.webSocketDebuggerUrl), pending=new Map();let id=0
  await new Promise(resolve=>socket.addEventListener('open',resolve,{once:true}))
  socket.addEventListener('message',({data})=>{
    const msg=JSON.parse(data)
    if(msg.method==='Runtime.exceptionThrown')errors.push(msg.params.exceptionDetails)
    if(msg.method==='Network.requestWillBeSent')requests.push(msg.params.request.url)
    const waiter=pending.get(msg.id);if(!waiter)return;pending.delete(msg.id);msg.error?waiter.reject(new Error(msg.error.message)):waiter.resolve(msg.result)
  })
  const command=(method,params={})=>new Promise((resolve,reject)=>{const requestId=++id;pending.set(requestId,{resolve,reject});socket.send(JSON.stringify({id:requestId,method,params}))})
  async function evaluate(expression){const r=await command('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true});if(r.exceptionDetails)throw new Error(JSON.stringify(r.exceptionDetails));return r.result.value}
  const client={socket,command,evaluate};clients.push(client)
  await command('Page.enable');await command('Network.enable');await command('Runtime.enable')
  await command('Emulation.setDeviceMetricsOverride',{width:1280,height:1000,deviceScaleFactor:1,mobile:false});await command('Page.navigate',{url})
  await until(()=>evaluate(`!!document.querySelector('[data-mode="pvp"]')`));return client
}
async function click(client,selector){
  const point=await client.evaluate(`(()=>{const el=document.querySelector(${JSON.stringify(selector)});if(!el||el.disabled)throw new Error('Unavailable '+${JSON.stringify(selector)});const r=el.getBoundingClientRect();return {x:r.left+r.width/2,y:r.top+r.height/2}})()`)
  await client.command('Input.dispatchMouseEvent',{type:'mousePressed',button:'left',clickCount:1,...point})
  await client.command('Input.dispatchMouseEvent',{type:'mouseReleased',button:'left',clickCount:1,...point});await sleep(80)
}
async function input(client,selector,value){await client.evaluate(`(()=>{const el=document.querySelector(${JSON.stringify(selector)});el.value=${JSON.stringify(value)};el.dispatchEvent(new Event('input',{bubbles:true}));})()`);await sleep(30)}
async function enter(client,name){await click(client,'[data-mode="pvp"]');await input(client,'#pvp-nickname',name);await click(client,'.lobby-dialog button[type="submit"]')}
async function create(client){await click(client,'.entry-action:first-child');await click(client,'.capacity-options button:first-child');await click(client,'.lobby-dialog button[type="submit"]');await until(()=>client.evaluate(`!!document.querySelector('.ready-button')&&!document.querySelector('.ready-button').disabled`));return client.evaluate(`document.querySelector('.room-number').textContent.trim()`)}
async function joinRoom(client,id){await click(client,'.entry-action:nth-child(2)');await input(client,'#pvp-room-id',id);await click(client,'.lobby-dialog button[type="submit"]');await until(()=>client.evaluate(`!!document.querySelector('.ready-button')&&!document.querySelector('.ready-button').disabled`))}
async function shot(client,name){const r=await client.command('Page.captureScreenshot',{format:'png'});await writeFile(`tests/artifacts/pvp-perspective/${name}.png`,Buffer.from(r.data,'base64'))}
const expected={E:{bottom:'E',top:'W',left:'N',right:'S'},S:{bottom:'S',top:'N',left:'E',right:'W'},W:{bottom:'W',top:'E',left:'S',right:'N'},N:{bottom:'N',top:'S',left:'W',right:'E'}}
async function checkView(client,wind){
  const value=await client.evaluate(`(()=>{
    const root=document.querySelector('.pvp-game-table'),profiles=[...document.querySelectorAll('.round-player,.self-player-caption')],stage=document.querySelector('.game-stage'),m=new DOMMatrix(getComputedStyle(stage).transform),s=stage.getBoundingClientRect(),det=m.a*m.d-m.b*m.c;
    const localY=el=>{const r=el.getBoundingClientRect(),dx=(r.left+r.right-s.left-s.right)/2,dy=(r.top+r.bottom-s.top-s.bottom)/2;return stage.offsetHeight/2+(-m.b*dx+m.a*dy)/det};
    return {self:root.dataset.selfWind,game:root.dataset.gameId,positions:Object.fromEntries(profiles.map(el=>[el.dataset.position,el.dataset.wind])),
      rivers:Object.fromEntries([...document.querySelectorAll('[data-river-wind]')].map(el=>[el.dataset.position,el.dataset.riverWind])),
      melds:{bottom:root.dataset.selfWind,...Object.fromEntries([...document.querySelectorAll('[data-meld-wind]')].map(el=>[el.dataset.position,el.dataset.meldWind]))},
      ownHand:document.querySelector('.pvp-own-hand').dataset.handWind,ownPosition:document.querySelector('.pvp-own-hand').dataset.position,
      names:profiles.map(el=>el.querySelector('b').textContent),dealer:(profiles.find(el=>el.dataset.wind==='E').querySelector('.player-caption')||profiles.find(el=>el.dataset.wind==='E')).textContent,
      noEV:!document.querySelector('.pve-discard-hud,.action-recommend-badge,.pve-ev-slot'),
      horizontalOverflow:stage.scrollWidth>stage.clientWidth+1,
      selfBelow:localY(document.querySelector('.pvp-own-hand'))>localY(document.querySelector('.pve-table')),
      singleLine:getComputedStyle(document.querySelector('.pvp-progress-hint')).whiteSpace==='nowrap'};
  })()`)
  assert.equal(value.self,wind);assert.deepEqual(value.positions,expected[wind]);assert.deepEqual(value.rivers,expected[wind]);assert.deepEqual(value.melds,expected[wind])
  assert.equal(value.ownHand,wind);assert.equal(value.ownPosition,'bottom');assert.ok(value.noEV&&value.selfBelow&&value.singleLine&&!value.horizontalOverflow,JSON.stringify(value));assert.match(value.dealer,/庄/)
  return value
}
try{
  await mkdir('tests/artifacts/pvp-perspective',{recursive:true})
  const first=await launch(9371),second=await launch(9372)
  await enter(first,'东窗真人');await enter(second,'南窗真人')
  const results=[]
  for(const [a,b] of [['E','S'],['W','N']]){
    const id=await create(first)
    if(a!=='E'){await click(first,`[data-seat="${a}"]`);await until(()=>first.evaluate(`document.querySelector('.my-seat').dataset.seat===${JSON.stringify(a)}`))}
    await joinRoom(second,id)
    if(b!=='E'){const current=await second.evaluate(`document.querySelector('.my-seat').dataset.seat`);if(current!==b){await click(second,`[data-seat="${b}"]`);await until(()=>second.evaluate(`document.querySelector('.my-seat').dataset.seat===${JSON.stringify(b)}`))}}
    await click(first,'.ready-button');await click(second,'.ready-button')
    await until(()=>first.evaluate(`!!document.querySelector('.god-opening-reveal')`))
    const revealedAt=Date.now()
    assert.ok(await second.evaluate(`!!document.querySelector('.god-opening-reveal')`))
    assert.equal(await first.evaluate(`document.querySelector('.pvp-game-table').dataset.phase`),'opening')
    assert.equal(await first.evaluate(`document.querySelector('.pvp-game-table').inert`),true)
    await shot(first,`god-${a}`)
    await sleep(1700);assert.ok(await first.evaluate(`!!document.querySelector('.god-opening-reveal')`))
    await until(()=>first.evaluate(`!!document.querySelector('.god-opening-flight')`))
    const flightStyle=await first.evaluate(`document.querySelector('.god-opening-flyer').getAttribute('style')`)
    assert.match(flightStyle,/scale\(/)
    await until(()=>first.evaluate(`!document.querySelector('.god-opening')&&document.querySelector('.pvp-game-table').dataset.phase!=='opening'`))
    await until(()=>second.evaluate(`!document.querySelector('.god-opening')&&document.querySelector('.pvp-game-table').dataset.phase!=='opening'`))
    const ceremonyMs=Date.now()-revealedAt
    assert.ok(ceremonyMs>=3300)
    const viewOne=await checkView(first,a),viewTwo=await checkView(second,b);assert.equal(viewOne.game,viewTwo.game)
    for(const [client,wind] of [[first,a],[second,b]]){
      for(const [width,height] of [[1280,1000],[390,844],[320,640]]){
        await client.command('Emulation.setDeviceMetricsOverride',{width,height,deviceScaleFactor:1,mobile:false});await sleep(100)
        await checkView(client,wind);await client.evaluate(`document.querySelector('.game-stage').scrollTop=0`);await shot(client,`${wind}-${width}`)
      }
    }
    if(a==='E'){
      await first.command('Emulation.setDeviceMetricsOverride',{width:1280,height:1000,deviceScaleFactor:1,mobile:false});await second.command('Emulation.setDeviceMetricsOverride',{width:1280,height:1000,deviceScaleFactor:1,mobile:false})
      const tile=await first.evaluate(`document.querySelector('.pvp-own-hand button[role="listitem"][aria-disabled="false"] .mahjong-tile').dataset.tile`)
      await click(first,'.pvp-own-hand button[role="listitem"][aria-disabled="false"]')
      await until(()=>second.evaluate(`document.querySelector('[data-river-wind="E"] .mahjong-tile')?.dataset.tile===${JSON.stringify(tile)}`))
      assert.equal(await first.evaluate(`document.querySelectorAll('.pvp-own-hand [role="list"] .mahjong-tile').length`),13)
      for(let i=0;i<50;i++){
        if(await second.evaluate(`!!document.querySelector('.pvp-own-hand button[role="listitem"][aria-disabled="false"]')`))break
        for(const client of [first,second])if(await client.evaluate(`!!document.querySelector('button[data-action="pass"]:not(:disabled)')`))await click(client,'button[data-action="pass"]:not(:disabled)')
        if(await first.evaluate(`!!document.querySelector('.pvp-own-hand button[role="listitem"][aria-disabled="false"]')`))await click(first,'.pvp-own-hand button[role="listitem"][aria-disabled="false"]')
        await sleep(180)
      }
      assert.ok(await second.evaluate(`!!document.querySelector('.pvp-own-hand button[role="listitem"][aria-disabled="false"]')`))
      assert.equal(await second.evaluate(`document.querySelectorAll('.pvp-own-hand [role="list"] .mahjong-tile').length`),14)
      await click(second,'.pvp-own-hand button[role="listitem"][aria-disabled="false"]')
      await until(()=>first.evaluate(`!!document.querySelector('[data-river-wind="S"] .mahjong-tile')`))
      await shot(first,'live-play-E');await shot(second,'live-play-S')
    }
    results.push({winds:[a,b],roomId:id,views:[viewOne,viewTwo],ceremonyMs})
    await click(first,'.pvp-game-header button:last-child');await click(first,'.lobby-dialog .primary-button')
    for (const client of [first,second]) { await until(()=>client.evaluate(`!!document.querySelector('.pvp-dissolved-dialog')&&!!document.querySelector('[data-mode="pvp"]')`)); await click(client,'[data-dismiss-room]') }
    await enter(first,'东窗真人');await enter(second,'南窗真人')
    await first.command('Emulation.setDeviceMetricsOverride',{width:1280,height:1000,deviceScaleFactor:1,mobile:false});await second.command('Emulation.setDeviceMetricsOverride',{width:1280,height:1000,deviceScaleFactor:1,mobile:false})
  }
  assert.equal(errors.length,0,JSON.stringify(errors))
  assert.ok(requests.some(r=>r.includes('OPENING.dat')))
  assert.ok(!requests.some(r=>/\/api\/(?:recommend|opponent-threats)/.test(r)))
  console.log(JSON.stringify({status:'passed',separateWindows:true,allPerspectives:true,openingAudioViaDataFetch:true,noEVRequests:true,liveDiscardDraw:true,results},null,2))
}finally{
  for(const client of clients)if(client.socket.readyState===WebSocket.OPEN){try{await client.command('Browser.close')}catch{}client.socket.close()}
  for(const browser of browsers)browser.kill()
}
