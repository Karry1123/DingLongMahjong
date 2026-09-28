import assert from 'node:assert/strict'
import { spawn } from 'node:child_process'
import { mkdir, mkdtemp, writeFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'

const profile = await mkdtemp(join(tmpdir(), 'mahjong-status-'))
const chrome = spawn(process.env.CHROME_PATH || 'C:/Program Files/Google/Chrome/Application/chrome.exe', [
  '--headless=new', '--disable-gpu', '--no-first-run', '--no-default-browser-check',
  '--remote-debugging-port=9351', '--remote-allow-origins=*', `--user-data-dir=${profile}`, 'about:blank',
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
    try { return (await (await fetch('http://127.0.0.1:9351/json/list')).json()).find(p => p.type === 'page') }
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
    s.soundMuted=true;s.activeUiMode='PVE';s.gameMode='PVE';s.gameState='PLAYING';s.pveOpening=false;s.enableEV=false;
    s.session.tableLocked.value=true;s.currentTurnSeat='E';s.currentPhase='MY_TURN_DISCARD';s.latestDrawnTile=null;s.lastStepResult=null;
    s.dealerSeat='S';s.analyzeError='';
    Object.assign(s.roundState,{handTiles:'1m 2m 3m 4m 5m 6m 2p 3p 4p 5s 6s 7s N N'.split(' '),seatWind:'E',roundWind:'E',dealerTile:'9p',isDealer:false,melds:[],discards:[],
      opponents:['N','W','S'].map(seat=>({seat_wind:seat,is_dealer:seat==='S',hand_tiles:Array(13).fill('1m'),melds:[],discards:[]}))});
    s.wallTiles=Array(82).fill('1p');
    window.__fixtureHint=(phase)=>{
      s.gameRoundId='status-'+phase;
      s.opponentThreats=[];for(const p of s.roundState.opponents){p.melds=[];p.discards=[];}
      s.wallTiles=Array(phase==='opening'?82:phase==='late'?18:phase==='end'?35:57).fill('1p');
      if(phase==='bamboo')s.roundState.opponents[0].melds=[{meld_type:'chi',tiles:['1s','2s','3s']},{meld_type:'chi',tiles:['5s','6s','7s']}];
      if(phase==='dealer')s.roundState.opponents[2].melds=[{meld_type:'chi',tiles:['1p','2p','3p']},{meld_type:'chi',tiles:['4p','5p','6p']},{meld_type:'pong',tiles:['C','C','C']}];
      if(phase==='multiple'){
        s.roundState.opponents[0].melds=[{meld_type:'chi',tiles:['1s','2s','3s']},{meld_type:'chi',tiles:['5s','6s','7s']}];
        s.roundState.opponents[2].melds=[{meld_type:'chi',tiles:['1p','2p','3p']},{meld_type:'chi',tiles:['4p','5p','6p']},{meld_type:'pong',tiles:['C','C','C']}];
      }
      if(phase==='fresh')s.roundState.opponents[1].discards=['4m','5p'];
      if(phase==='dragon')s.roundState.opponents[0].melds=[{meld_type:'pong',tiles:['C','C','C']}];
      if(phase==='model'){
        setTimeout(()=>{s.opponentThreats=[{seat_wind:'W',probability:.2}]},0);
        setTimeout(()=>{s.opponentThreats=[{seat_wind:'W',probability:.7}]},50);
      }
    };
  })()`)
  const results=[];await mkdir('tests/artifacts/status-hint',{recursive:true})
  for(const [phase,pattern] of [['opening','牌局平稳'],['middle','牌局步入中盘'],['end','局势进入白热化'],['late','海底绝张'],['dragon','上家大番（中）'],['bamboo','上家2副露'],['dealer','下家庄家3副露'],['fresh','对家连切生张'],['model','对家听牌骤增']]) {
    console.log('Testing '+phase)
    await evaluate(`window.__fixtureHint('${phase}')`)
    try { await until(()=>evaluate(`document.querySelector('.pve-situation-hud')?.textContent.includes('${pattern}')`)) }
    catch(error) { throw new Error(phase+': '+await evaluate(`document.querySelector('.pve-situation-hud')?.textContent`)) }
    for(const [width,height] of [[1280,720],[390,844],[844,390]]) {
      await command('Emulation.setDeviceMetricsOverride',{width,height,deviceScaleFactor:1,mobile:false});await sleep(200)
      const layout=await evaluate(`(()=>{
        const hint=document.querySelector('.pve-situation-hud'),r=hint.getBoundingClientRect(),hand=document.querySelector('.pve-self-controls').getBoundingClientRect();
        const range=document.createRange();range.selectNodeContents(hint.querySelector('span'));const text=range.getBoundingClientRect();
        const overlaps=(a,b)=>Math.min(a.right,b.right)>Math.max(a.left,b.left)+1&&Math.min(a.bottom,b.bottom)>Math.max(a.top,b.top)+1;
        return {text:hint.textContent.trim(),fits:r.width>0&&r.height>0&&getComputedStyle(hint).display!=='none'&&r.left>=0&&r.top>=0&&r.right<=innerWidth&&r.bottom<=innerHeight,
          noClip:hint.scrollWidth<=hint.clientWidth&&hint.scrollHeight<=hint.clientHeight,
          singleLine:[...range.getClientRects()].length===1&&getComputedStyle(hint).whiteSpace==='nowrap'&&getComputedStyle(hint).height==='32px',
          lineMetrics:{rects:range.getClientRects().length,height:getComputedStyle(hint).height,whiteSpace:getComputedStyle(hint).whiteSpace},
          noHandOverlap:!overlaps(r,hand),level:hint.className};
      })()`)
      assert.ok(layout.fits&&layout.noClip&&layout.noHandOverlap&&layout.singleLine,JSON.stringify(layout));assert.ok(layout.text.includes(pattern));
      results.push({phase,width,height,...layout})
      const shot=await command('Page.captureScreenshot',{format:'png'});await writeFile(`tests/artifacts/status-hint/${phase}-${width}.png`,Buffer.from(shot.data,'base64'))
    }
    if(['dragon','bamboo','dealer','fresh','model'].includes(phase)) {
      await evaluate(`(()=>{const s=document.querySelector('#app').__vue_app__._instance.setupState;s.wallTiles=s.wallTiles.slice(8)})()`)
      await until(()=>evaluate(`document.querySelector('.pve-situation-hud')?.textContent.includes('牌局步入中盘')`))
      // The unchanged exposures and model response must not re-arm the event.
      await sleep(300)
      assert.ok(await evaluate(`document.querySelector('.pve-situation-hud').textContent.includes('牌局步入中盘')`))
      results.push({phase,expired:true,baseRestored:true})
    }
  }
  console.log(JSON.stringify({status:'passed',results},null,2))
} finally {
  if(socket?.readyState===WebSocket.OPEN){try{await command('Browser.close')}catch{}socket.close()}
  chrome.kill()
}
