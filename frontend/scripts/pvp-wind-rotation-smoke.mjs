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
  await command('Page.enable');await command('Runtime.enable');await command('Emulation.setDeviceMetricsOverride',{width:1280,height:1000,deviceScaleFactor:1,mobile:false});await command('Page.addScriptToEvaluateOnNewDocument',{source:`const NativeWS=window.WebSocket;window.WebSocket=class extends NativeWS{constructor(...args){super(...args);if(String(args[0]).includes('/rooms/')){window.__pvpSocket=this;this.addEventListener('message',e=>{const m=JSON.parse(e.data);if(m.game)window.__game=m.game})}}}`});await command('Page.navigate',{url})
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
  await click(clients[0],'.entry-action:first-child');await click(clients[0],'.capacity-options button:last-child');await click(clients[0],'.lobby-dialog button[type="submit"]')
  await until(()=>clients[0].evaluate(`!!document.querySelector('.ready-button')`))
  const id=await clients[0].evaluate(`document.querySelector('.room-number').textContent.trim()`)
  for(const c of clients.slice(1))await joinRoom(c,id)
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
  await mkdir('tests/artifacts/pvp-wind-rotation',{recursive:true})
  for(let i=0;i<4;i++)await launch(9461+i)
  await start('换庄房主')
  const rounds=[]
  async function verify(dealerIndex){
    const views=[]
    for(const [i,c]of clients.entries()){
      const result=await c.evaluate(`(()=>{const g=window.__game;return {id:g.game_id,wind:g.seat_wind,dealer:g.dealer_seat,players:g.players.map(p=>({wind:p.seat_wind,seat:p.seat,name:p.nickname})),captions:[...document.querySelectorAll('.player-caption')].map(e=>e.textContent.trim()),self:document.querySelector('.self-player-caption').textContent.trim()}})()`)
      assert.equal(result.wind,'ESWN'[(i-dealerIndex+4)%4]);assert.equal(result.dealer,'E')
      for(const p of result.players)assert.equal(p.wind,'ESWN'[(p.seat-dealerIndex+4)%4])
      assert.match(result.self,new RegExp('自家 · '+{E:'东',S:'南',W:'西',N:'北'}[result.wind]+'风'))
      if(i===dealerIndex)assert.match(result.self,/自家 · 东风.*庄/)
      assert.equal(result.captions.filter(s=>s.includes('庄')&&s.includes('东风')).length,1)
      const shot=await c.command('Page.captureScreenshot',{format:'png'})
      await writeFile(`tests/artifacts/pvp-wind-rotation/hand-${dealerIndex+1}-window-${i+1}.png`,Buffer.from(shot.data,'base64'))
      views.push(result)
    }
    rounds.push(views)
  }
  // Play every live wall tile through authenticated browser WebSockets.
  // Passing claims and declining wins guarantees a complete drawn hand.
  for(let dealerIndex=0;dealerIndex<4;dealerIndex++){
    await verify(dealerIndex)
    if(dealerIndex===3)break
    for(let step=0;step<450;step++){
      const games=await Promise.all(clients.map(c=>c.evaluate('window.__game')))
      if(games.every(g=>g.phase==='finished')){assert.ok(games.every(g=>g.result.is_draw));break}
      const index=games.findIndex(g=>g.actions.some(a=>a.action_type===(g.phase==='response'?'pass':'discard')))
      if(index<0){await sleep(20);continue}
      const game=games[index],kind=game.phase==='response'?'pass':'discard'
      const action=game.actions.find(a=>a.action_type===kind&&(kind==='pass'||a.tiles[0]===(game.drawn_tile||game.hand_tiles.at(-1))))||game.actions.find(a=>a.action_type===kind)
      await clients[index].evaluate(`window.__pvpSocket.send(${JSON.stringify(JSON.stringify({type:'game_action',game_id:game.game_id,revision:game.revision,action_id:action.action_id}))})`)
      await until(()=>clients[index].evaluate(`window.__game.revision>${game.revision}`))
      if(step===449)throw new Error('Hand did not finish')
    }
    const previous=await clients[0].evaluate('window.__game.game_id')
    for(const c of clients)await click(c,'.next-round-button')
    for(const c of clients)await until(()=>c.evaluate(`window.__game.game_id!==${JSON.stringify(previous)}&&window.__game.phase!=='opening'&&!document.querySelector('.god-opening')`))
  }
  assert.deepEqual(errors,[])
  console.log(JSON.stringify({status:'passed',windows:4,fullDrawnHands:3,rounds},null,2))
}finally{
  for(const client of clients)if(client.socket.readyState===WebSocket.OPEN){try{await client.command('Browser.close')}catch{}client.socket.close()}
  for(const browser of browsers)browser.kill()
}
