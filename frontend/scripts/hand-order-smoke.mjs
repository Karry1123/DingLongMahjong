import assert from 'node:assert/strict'
import { spawn } from 'node:child_process'
import { mkdir, mkdtemp, writeFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'

const profile = await mkdtemp(join(tmpdir(), 'mahjong-hand-order-'))
const chrome = spawn(process.env.CHROME_PATH || 'C:/Program Files/Google/Chrome/Application/chrome.exe', [
  '--headless=new', '--disable-gpu', '--no-first-run', '--no-default-browser-check',
  '--remote-debugging-port=9352', '--remote-allow-origins=*', `--user-data-dir=${profile}`, 'about:blank',
], { windowsHide: true, stdio: 'ignore' })
let socket, id = 0
const pending = new Map()
const sleep = ms => new Promise(resolve => setTimeout(resolve, ms))
async function until(fn) {
  for (let i = 0; i < 200; i++) {
    const result = await fn()
    if (result) return result
    await sleep(100)
  }
  throw new Error('Browser test timed out')
}
const command = (method, params = {}) => new Promise((resolve, reject) => {
  const requestId = ++id
  pending.set(requestId, { resolve, reject })
  socket.send(JSON.stringify({ id: requestId, method, params }))
})
async function evaluate(expression) {
  const result = await command('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true })
  if (result.exceptionDetails) throw new Error(JSON.stringify(result.exceptionDetails))
  return result.result.value
}
try {
  const page = await until(async () => {
    try { return (await (await fetch('http://127.0.0.1:9352/json/list')).json()).find(p => p.type === 'page') }
    catch { return null }
  })
  socket = new WebSocket(page.webSocketDebuggerUrl)
  await new Promise(resolve => socket.addEventListener('open', resolve, { once: true }))
  socket.addEventListener('message', ({ data }) => {
    const msg = JSON.parse(data), waiter = pending.get(msg.id)
    if (!waiter) return
    pending.delete(msg.id)
    msg.error ? waiter.reject(new Error(msg.error.message)) : waiter.resolve(msg.result)
  })
  await command('Page.enable')
  await command('Page.navigate', { url: process.env.PVE_URL || 'http://127.0.0.1:5178/' })
  await until(() => evaluate(`!!document.querySelector('#app')?.__vue_app__`))
  await evaluate(`(() => {
    const s=document.querySelector('#app').__vue_app__._instance.setupState;
    window.__handSession=s.session;
    window.__fixtureHand=(auto,kong=false)=>{
      s.soundMuted=true;s.enableEV=false;s.activeUiMode='PVE';s.gameMode='PVE';s.gameState='PLAYING';s.pveOpening=false;
      s.session.tableLocked.value=true;s.godViewWallMode=false;s.autoSortEnabled=auto;s.dealerSeat='E';s.analyzeError='';
      s.gameRoundId='hand-'+auto+'-'+kong;s.session.clearHandLayoutPin();s.latestDrawnTile=null;s.latestDrawnBySeat={E:null,S:null,W:null,N:null};
      s.currentTurnSeat='E';s.currentPhase='WAITING';s.lastStepResult=null;s.lastDiscardSeat=null;
      Object.assign(s.roundState,{seatWind:'E',roundWind:'E',dealerTile:'9p',isDealer:true,melds:[],discards:[],
        handTiles:kong?['9p','2p','P','4p','1m','1m','1m','1m','5s','6s','7s','N','N','C']
          :['9p','1m','2m','3m','2p','4p','P','5s','5s','7s','8s','N','N'],
        opponents:['S','W','N'].map(seat_wind=>({seat_wind,is_dealer:false,hand_tiles:[],melds:[],discards:[]}))});
      s.wallTiles=Array(60).fill('6p');
    };
  })()`)
  await command('Emulation.setDeviceMetricsOverride',{width:1280,height:720,deviceScaleFactor:1,mobile:false})
  const hand=()=>evaluate(`[...window.__handSession.roundState.handTiles]`)
  async function drag(fromIndex,toIndex){
    await sleep(180)
    const pos=await evaluate(`(()=>{
      const buttons=[...document.querySelectorAll('.pve-hand-anchor button[data-hand-index]')];
      const a=buttons.find(b=>Number(b.dataset.handIndex)===${fromIndex}).getBoundingClientRect();
      const b=buttons.find(b=>Number(b.dataset.handIndex)===${toIndex}).getBoundingClientRect();
      return {x:a.left+a.width/2,y:a.top+a.height/2,tx:b.left+b.width/2-2,ty:b.top+b.height/2};
    })()`)
    await command('Input.dispatchMouseEvent',{type:'mouseMoved',x:pos.x,y:pos.y})
    await command('Input.dispatchMouseEvent',{type:'mousePressed',x:pos.x,y:pos.y,button:'left',clickCount:1})
    for(let i=1;i<=6;i++)await command('Input.dispatchMouseEvent',{type:'mouseMoved',x:pos.x+(pos.tx-pos.x)*i/6,y:pos.y+(pos.ty-pos.y)*i/6,button:'left',buttons:1})
    await command('Input.dispatchMouseEvent',{type:'mouseReleased',x:pos.tx,y:pos.ty,button:'left',clickCount:1})
    await sleep(100)
  }
  const results=[];await mkdir('tests/artifacts/hand-order',{recursive:true})
  for(const auto of [true,false]){
    await evaluate(`window.__fixtureHand(${auto})`)
    if(auto){
      await sleep(200)
      const before=await hand();await drag(4,8);assert.deepEqual(await hand(),before)
      assert.equal(await evaluate(`document.querySelector('.pve-hand-anchor button[data-hand-index="4"]').draggable`),false)
      results.push({ordinaryDragBlocked:true,noAccidentalDiscard:true})
    }
    await drag(0,5)
    let expected=['1m','2m','3m','2p','9p','4p','P','5s','5s','7s','8s','N','N']
    assert.deepEqual(await hand(),expected)
    await drag(6,4)
    expected=['1m','2m','3m','2p','P','9p','4p','5s','5s','7s','8s','N','N']
    assert.deepEqual(await hand(),expected)
    if(!auto){await drag(9,1);const [tile]=expected.splice(9,1);expected.splice(1,0,tile);assert.deepEqual(await hand(),expected)}
    for(const tile of ['C','F']){
      await evaluate(`(async()=>{const s=window.__handSession;s.currentTurnSeat.value='E';s.currentPhase.value='WAITING';s.lastStepResult.value=null;await s.selfDrawTile('${tile}')})()`)
      assert.deepEqual(await hand(),[...expected,tile])
      assert.equal(await evaluate(`window.__handSession.latestDrawnTile.value`),tile)
      await evaluate(`(()=>{const s=window.__handSession;s.currentTurnSeat.value='E';s.currentPhase.value='MY_TURN_DISCARD';return s.discardTile('${tile}',13)})()`)
      assert.deepEqual(await hand(),expected)
    }
    await evaluate(`(async()=>{const s=window.__handSession;s.currentTurnSeat.value='E';s.currentPhase.value='WAITING';s.lastStepResult.value=null;await s.selfDrawTile('3p')})()`)
    assert.deepEqual(await hand(),[...expected,'3p'])
    await evaluate(`(()=>{const s=window.__handSession;s.currentTurnSeat.value='E';s.currentPhase.value='MY_TURN_DISCARD';return s.discardTile('N',s.roundState.handTiles.lastIndexOf('N'))})()`)
    expected.splice(expected.lastIndexOf('N'),1)
    if(auto)expected.splice(expected.indexOf('P'),0,'3p')
    else expected.push('3p')
    assert.deepEqual(await hand(),expected)
    results.push({auto,retainedDrawSorted:auto,godAnchorBefore4p:true})
    async function claim(type,tiles,tile,provider){
      await evaluate(`(async()=>{const s=window.__handSession;s.lastDiscardSeat.value='${provider}';s.currentPhase.value='WAIT_RESPONSE';s.lastStepResult.value={_response_tile:'${tile}',need_self_action:true,action_phase:'CALL'};
        s.roundState.opponents.find(p=>p.seat_wind==='${provider}').discards.push('${tile}');
        await s.applySelfMeld({meld_type:'${type}',tiles:${JSON.stringify(tiles)},claimed_tile:'${tile}',provider_seat:'${provider}'})})()`)
    }
    await claim('chi',['1m','2m','3m'],'3m','N');expected=expected.filter(t=>!['1m','2m'].includes(t));assert.deepEqual(await hand(),expected)
    await evaluate(`window.__handSession.discardTile('N',window.__handSession.roundState.handTiles.lastIndexOf('N'))`);expected.splice(expected.lastIndexOf('N'),1)
    await claim('pong',['5s','5s','5s'],'5s','S');expected=expected.filter(t=>t!=='5s');assert.deepEqual(await hand(),expected)
    const godIndex=expected.indexOf('9p'),proxyIndex=expected.indexOf('P')
    await evaluate(`(()=>{const b=[...document.querySelectorAll('.pve-self-controls button')].find(b=>b.textContent.includes('一键理牌'));b.click()})()`)
    assert.equal((await hand()).indexOf('9p'),godIndex);assert.equal((await hand()).indexOf('P'),proxyIndex)
    results.push({auto,draggedGod:true,draggedProxy:true,drawDiscardCycles:2,chi:true,pong:true,explicitTidyPreservesGods:true})
    const shot=await command('Page.captureScreenshot',{format:'png'});await writeFile(`tests/artifacts/hand-order/auto-${auto}.png`,Buffer.from(shot.data,'base64'))
    await evaluate(`window.__fixtureHand(${auto},true)`);await drag(0,3)
    assert.ok((await hand()).indexOf('9p')>0)
    expected=(await hand()).filter(t=>t!=='1m')
    await evaluate(`window.__handSession.applySelfKong({meld_type:'an_gang',tile:'1m'})`)
    assert.deepEqual(await hand(),expected)
    await evaluate(`window.__handSession.selfDrawTile('F')`);assert.deepEqual(await hand(),[...expected,'F'])
    results.push({auto,kong:true,replacementDrawPreservesOrder:true})
  }
  console.log(JSON.stringify({status:'passed',results},null,2))
} finally {
  if(socket?.readyState===WebSocket.OPEN){try{await command('Browser.close')}catch{}socket.close()}
  chrome.kill()
}
