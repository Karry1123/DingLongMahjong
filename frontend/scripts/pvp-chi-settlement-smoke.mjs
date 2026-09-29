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
  const profile=await mkdtemp(join(tmpdir(),'dinglong-chi-'))
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

try {
  const folder = 'tests/artifacts/pvp-chi-settlement'
  await mkdir(folder, {recursive:true})
  for(let i=0;i<4;i++)await launch(9471+i)
  await start('吃牌房主')
  const [east,south,west,north] = clients
  async function discard(client, tile) {
    await until(()=>client.evaluate(`window.__game.phase==='discard' && window.__game.current_turn===window.__game.seat_wind`))
    await click(client,`.pvp-own-hand [data-tile="${tile}"]`)
  }
  await discard(east,'5m')
  await until(()=>south.evaluate(`!!document.querySelector('[data-action="chi"]')`))
  await click(south,'[data-action="chi"]')
  await until(()=>south.evaluate(`document.querySelectorAll('[data-meld-wind="S"] [data-sideways="true"]').length===1`))
  await discard(south,'F')
  await discard(west,'2s')
  await discard(north,'3s')
  await discard(east,'9p')
  await until(()=>south.evaluate(`!!document.querySelector('[data-action="hu"]')`))
  await click(south,'[data-action="hu"]')
  for(const c of clients)await until(()=>c.evaluate(`!!document.querySelector('.pvp-result')`))
  const measurements=[]
  for(const [i,client]of clients.entries()){
    for(const [width,height]of [[1280,720],[844,390],[390,844]]){
      await client.command('Emulation.setDeviceMetricsOverride',{width,height,deviceScaleFactor:1,mobile:width<1000})
      await sleep(100)
      const result=await client.evaluate(`(()=>{
        const g=window.__game, detail=g.result.seat_details.S;
        const group=[...document.querySelectorAll('.landscape-winner-group')].find(el=>el.querySelector('[data-tile="5m"]'));
        const tiles=[...group.querySelectorAll('.mahjong-tile')];
        // Use layout coordinates because portrait mode rotates the entire stage.
        const rects=tiles.map(el=>({code:el.dataset.tile,sideways:el.dataset.sideways==='true',width:el.offsetWidth,height:el.offsetHeight,bottom:el.offsetTop+el.offsetHeight,transform:getComputedStyle(el.querySelector('.tile-face')).transform}));
        const panel=document.querySelector('.game-over-panel').getBoundingClientRect();
        return {winner:g.result.winner_seat,meld:detail.melds[0],group:detail.winning_hand_groups.find(g=>g.source==='open'),rects,
          fits:panel.left>=-1&&panel.top>=-1&&panel.right<=innerWidth+1&&panel.bottom<=innerHeight+1};
      })()`)
      assert.equal(result.winner,'S')
      assert.equal(result.meld.claimed_tile,'5m');assert.equal(result.meld.provider_seat,'E')
      assert.equal(result.group.claimed_tile,'5m');assert.equal(result.group.provider_seat,'E')
      assert.deepEqual(result.rects.map(t=>t.code),['3m','5m','4m'])
      assert.deepEqual(result.rects.map(t=>t.sideways),[false,true,false])
      const [upright,claimed]=result.rects
      assert.ok(claimed.width>claimed.height && upright.width<upright.height)
      assert.ok(Math.abs(claimed.width-upright.height)<1 && Math.abs(claimed.height-upright.width)<1)
      assert.ok(result.rects.every(t=>Math.abs(t.bottom-upright.bottom)<1),'Chi tiles must share the bottom edge')
      assert.match(claimed.transform,/matrix\(0, 1, -1, 0,/)
      assert.ok(result.fits)
      measurements.push({window:i+1,width,height,...result})
      const shot=await client.command('Page.captureScreenshot',{format:'png'})
      await writeFile(`${folder}/window-${i+1}-${width}x${height}.png`,Buffer.from(shot.data,'base64'))
    }
  }
  // Switch the live shared settlement component to its PvE presentation and
  // compare geometry in the same stage, preserving the browser's loaded styles.
  const parity=await south.evaluate(`(async()=>{
    function geometry(root){const group=[...root.querySelectorAll('.landscape-winner-group')].find(el=>el.querySelector('[data-tile="5m"]'));
      return [...group.querySelectorAll('.mahjong-tile')].map(el=>({code:el.dataset.tile,sideways:el.dataset.sideways==='true',width:el.offsetWidth,height:el.offsetHeight,face:getComputedStyle(el.querySelector('.tile-face')).transform}))}
    const root=document.querySelector('.pvp-result'), instance=root.__vueParentComponent;
    const pvp=geometry(root);instance.props.pvp=false;
    await new Promise(resolve=>requestAnimationFrame(resolve));const pve=geometry(root);
    if(root.classList.contains('pvp-result'))throw new Error('PvE presentation did not activate');
    instance.props.pvp=true;await new Promise(resolve=>requestAnimationFrame(resolve));
    return {pvp,pve};
  })()`)
  assert.deepEqual(parity.pvp,parity.pve)
  assert.deepEqual(errors,[])
  await writeFile(`${folder}/report.json`,JSON.stringify({status:'passed',measurements,parity},null,2))
  console.log(JSON.stringify({status:'passed',windows:4,viewports:3,claimedTile:'5m',provider:'E',pveParity:true},null,2))
}finally{
  for(const client of clients)if(client.socket.readyState===WebSocket.OPEN){try{await client.command('Browser.close')}catch{}client.socket.close()}
  for(const browser of browsers)browser.kill()
}
