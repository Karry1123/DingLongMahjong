import assert from 'node:assert/strict'
import { spawn } from 'node:child_process'
import { mkdir, mkdtemp, writeFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'

const profile = await mkdtemp(join(tmpdir(), 'mahjong-opening-'))
const chrome = spawn(process.env.CHROME_PATH || 'C:/Program Files/Google/Chrome/Application/chrome.exe', [
  '--headless=new', '--autoplay-policy=no-user-gesture-required', '--disable-gpu', '--no-first-run', '--no-default-browser-check',
  '--remote-debugging-port=9349', '--remote-allow-origins=*', `--user-data-dir=${profile}`, 'about:blank',
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
    try { return (await (await fetch('http://127.0.0.1:9349/json/list')).json()).find(p => p.type === 'page') }
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
  assert.equal(await evaluate('document.title'),'顶龙麻将')
  await evaluate(`(async()=>{
    const {northDiscardDeal}=await import('/tests/pveFixture.js');
    const realFetch=window.fetch.bind(window);
    window.__audioRequests=[];window.__audioDecoded=0;window.__audioPlayed=[];
    const decode=AudioContext.prototype.decodeAudioData;
    AudioContext.prototype.decodeAudioData=function(...args){window.__audioDecoded++;return decode.apply(this,args)};
    const start=AudioBufferSourceNode.prototype.start;
    AudioBufferSourceNode.prototype.start=function(...args){window.__audioPlayed.push(this.buffer?.duration);return start.apply(this,args)};
    window.fetch=(url,init)=>{
      if(String(url).endsWith('/game/auto-deal')) return Promise.resolve(new Response(JSON.stringify(northDiscardDeal()),{headers:{'Content-Type':'application/json'}}));
      if(String(url).includes('/audio/')) window.__audioRequests.push(String(url));
      return realFetch(url,init);
    };
    new MutationObserver(()=>{
      const overlay=document.querySelector('.god-opening');
      if(!window.__timeline) return;
      if(overlay&&!window.__timeline.start) window.__timeline.start=performance.now();
      if(overlay?.dataset.openingPhase==='flight'&&!window.__timeline.flight) window.__timeline.flight=performance.now();
      if(!overlay&&window.__timeline.start&&!window.__timeline.end) window.__timeline.end=performance.now();
    }).observe(document.body,{childList:true,subtree:true,attributes:true,attributeFilter:['data-opening-phase']});
  })()`)
  await mkdir('tests/artifacts/opening',{recursive:true})
  const ceremonies=[]
  for(const [index,[width,height]] of [[1280,720],[390,844],[844,390]].entries()) {
    await command('Emulation.setDeviceMetricsOverride',{width,height,deviceScaleFactor:1,mobile:false})
    await evaluate('window.__timeline={}')
    if(index===0) {
      await evaluate(`[...document.querySelectorAll('button')].find(b=>b.textContent.includes('人机对战')).click()`)
      await until(()=>evaluate(`!!document.querySelector('[aria-label="人机对战设置"]')`))
      await command('Runtime.evaluate',{expression:`[...document.querySelectorAll('button')].find(b=>b.textContent.includes('开始对战')).click()`,userGesture:true})
    } else await evaluate(`void document.querySelector('#app').__vue_app__._instance.setupState.startNextRound(null,false,{isDraw:true})`)
    await until(()=>evaluate(`!!document.querySelector('.god-opening-reveal')`))
    const frozen=await evaluate(`(()=>{const s=document.querySelector('#app').__vue_app__._instance.setupState;return {state:s.gameState,opening:s.pveOpening,wall:s.wallTiles.length,inert:document.querySelector('main').inert,discards:s.roundState.discards.length+s.roundState.opponents.reduce((n,o)=>n+o.discards.length,0)}})()`)
    assert.equal(frozen.state,'SETUP');assert.equal(frozen.opening,true);assert.equal(frozen.inert,true);assert.equal(frozen.discards,0)
    const shot=await command('Page.captureScreenshot',{format:'png'})
    await writeFile(`tests/artifacts/opening/reveal-${width}x${height}.png`,Buffer.from(shot.data,'base64'))
    await sleep(2700)
    assert.equal(await evaluate(`document.querySelector('.god-opening')?.dataset.openingPhase`),'reveal')
    assert.equal(await evaluate(`document.querySelector('#app').__vue_app__._instance.setupState.wallTiles.length`),frozen.wall)
    await until(()=>evaluate(`!!window.__timeline.flight`))
    const flight=await evaluate(`(async()=>{
      await new Promise(resolve=>setTimeout(resolve,Math.max(0,550-(performance.now()-window.__timeline.flight))));
      const a=document.querySelector('.god-opening-flyer').getBoundingClientRect(),b=document.querySelector('[data-god-slot] .mahjong-tile').getBoundingClientRect();
      return {centerError:Math.hypot((a.left+a.right-b.left-b.right)/2,(a.top+a.bottom-b.top-b.bottom)/2),sizeError:Math.abs(a.width-b.width),revealMs:window.__timeline.flight-window.__timeline.start};
    })()`)
    assert.ok(flight.centerError<7&&flight.sizeError<7,JSON.stringify(flight))
    assert.ok(flight.revealMs>=2950&&flight.revealMs<3400,JSON.stringify(flight))
    await until(()=>evaluate(`!document.querySelector('.god-opening')&&document.querySelector('#app').__vue_app__._instance.setupState.gameState==='PLAYING'`))
    const timing=await evaluate(`({...window.__timeline})`)
    assert.ok(timing.end-timing.flight>=570&&timing.end-timing.flight<950,JSON.stringify(timing))
    ceremonies.push({width,height,...flight,flightMs:timing.end-timing.flight})
  }
  const audio=await evaluate(`({requests:window.__audioRequests,decoded:window.__audioDecoded,played:window.__audioPlayed,media:document.querySelectorAll('audio,video').length})`)
  assert.ok(audio.requests.some(url=>url.endsWith('/OPENING.dat'))&&audio.decoded>0&&audio.played.some(d=>Math.abs(d-1.65)<.02),JSON.stringify(audio))
  assert.equal(audio.media,0)
  await evaluate(`(()=>{
    const s=document.querySelector('#app').__vue_app__._instance.setupState;
    s.enableEV=false;s.roundState.seatWind='E';s.currentTurnSeat='E';s.currentPhase='OPPONENT_DISCARD_ACTION';s.lastDiscardSeat='N';
    const tiles=Array.from({length:24},(_,i)=>(i%9+1)+'m');
    const melds=[{meld_type:'chi',tiles:['1s','2s','3s']},{meld_type:'chi',tiles:['4p','5p','6p']},{meld_type:'pong',tiles:['C','C','C']},{meld_type:'ming_gang',tiles:['9s','9s','9s','9s']}];
    s.roundState.opponents=['S','W','N'].map(seat=>({seat_wind:seat,is_dealer:seat==='E',hand_tiles:['E'],discards:[...tiles],melds}));
    s.roundState.discards=[...tiles];s.roundState.handTiles='1m 2m 3m 4p 5p 6p 1s 2s 3s E E C F'.split(' ');
    s.roundState.opponents.find(o=>o.seat_wind==='N').discards.push('8m');
    s.lastStepResult={need_self_action:true,_response_tile:'8m',call_decision:{available_actions:[{action_type:'chi',tiles:['6m','7m','8m'],provider_seat:'N'},{action_type:'pass',tiles:[],provider_seat:'N'}],candidates:[]}};
  })()`)
  const layouts=[]
  for(const [width,height] of [[1280,720],[390,844],[844,390]]) {
    await command('Emulation.setDeviceMetricsOverride',{width,height,deviceScaleFactor:1,mobile:false});await sleep(100)
    const layout=await evaluate(`(()=>{
      const r=el=>el.getBoundingClientRect(),overlap=(a,b)=>Math.min(a.right,b.right)>Math.max(a.left,b.left)+1&&Math.min(a.bottom,b.bottom)>Math.max(a.top,b.top)+1;
      const rivers=[...document.querySelectorAll('.pve-river-tiles')],melds=[...document.querySelectorAll('.pve-opponent-melds')];
      const center=r(document.querySelector('.center-compass-hud'));
      const target=document.querySelector('.action-target-tile'),bounds=r(target);
      const chars=[...target.querySelectorAll('.characters b')].map(r);
      return {riverWidths:rivers.map(river=>river.querySelector('.mahjong-tile').offsetWidth),meldWidths:melds.map(meld=>meld.querySelector('.mahjong-tile:not(.sideways)').offsetWidth),
        handWidth:document.querySelector('.pve-self-hand .mahjong-tile').offsetWidth,
        targetFits:chars.length===2&&chars.every(b=>b.top>=bounds.top&&b.bottom<=bounds.bottom&&b.left>=bounds.left&&b.right<=bounds.right),
        collisionDetails:rivers.flatMap((river,i)=>[
          ...rivers.slice(i+1).filter(other=>overlap(r(river),r(other))).map(other=>({pair:[river.dataset.layout,other.dataset.layout],a:r(river).toJSON(),b:r(other).toJSON()})),
          ...(overlap(r(river),center)?[{pair:[river.dataset.layout,'center'],a:r(river).toJSON(),b:center.toJSON()}]:[]),
          ...melds.filter(meld=>overlap(r(river),r(meld))).map(meld=>({pair:[river.dataset.layout,'meld-'+meld.closest('[data-position]').dataset.position],a:r(river).toJSON(),b:r(meld).toJSON()})),
        ]),
        noPageOverflow:document.documentElement.scrollWidth<=innerWidth&&document.documentElement.scrollHeight<=innerHeight};
    })()`)
    assert.ok(layout.riverWidths.every(w=>Math.abs(w-31.74)<1)&&layout.meldWidths.every(w=>Math.abs(w-34.385)<1),JSON.stringify(layout))
    assert.equal(layout.handWidth,44)
    assert.ok(layout.targetFits&&!layout.collisionDetails.length&&layout.noPageOverflow,JSON.stringify(layout))
    layouts.push({width,height,...layout})
    const shot=await command('Page.captureScreenshot',{format:'png'})
    await writeFile(`tests/artifacts/opening/layout-${width}x${height}.png`,Buffer.from(shot.data,'base64'))
  }
  console.log(JSON.stringify({status:'passed',ceremonies,audio,layouts},null,2))
} finally {
  if(socket?.readyState===WebSocket.OPEN){try{await command('Browser.close')}catch{}socket.close()}
  chrome.kill()
}
