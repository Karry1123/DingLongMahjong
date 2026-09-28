import assert from 'node:assert/strict'
import { spawn } from 'node:child_process'
import { mkdir, mkdtemp, writeFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'

const profile = await mkdtemp(join(tmpdir(), 'mahjong-meld-'))
const chrome = spawn(process.env.CHROME_PATH || 'C:/Program Files/Google/Chrome/Application/chrome.exe', [
  '--headless=new', '--disable-gpu', '--no-first-run', '--no-default-browser-check',
  '--remote-debugging-port=9348', '--remote-allow-origins=*', `--user-data-dir=${profile}`, 'about:blank',
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
    try { return (await (await fetch('http://127.0.0.1:9348/json/list')).json()).find(p => p.type === 'page') }
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
    const realFetch=window.fetch.bind(window);
    window.__meldRequests=[];
    window.fetch=async(url,init)=>{
      const response=await realFetch(url,init);
      const body=init?.body?JSON.parse(init.body):null;
      if(body?.event?.event_type==='MELD') window.__meldRequests.push({body,status:response.status});
      return response;
    };
    window.__loadMeldFixture=async()=>{
      const hand='P 7p 9p E E 1m 2m 3m 4m 5m 1s 2s 3s'.split(' ');
      const opponents=['S','W','N'].map(seat=>({seat_wind:seat,is_dealer:false,melds:[],discards:[]}));
      const payload={hand_tiles:hand,seat_wind:'E',round_wind:'E',is_dealer:true,dealer_tile:'6p',
        melds:[],discards:[],opponents,event:{event_type:'DISCARD',actor_seat:'N',tile:'8p'}};
      const response=await fetch('/api/game/step',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
      const result=await response.json();
      if(!response.ok||!result.call_decision) throw new Error(JSON.stringify(result));
      window.__expectedRecommendation=result.call_decision.recommended_action;
      const s=document.querySelector('#app').__vue_app__._instance.setupState;
      s.activeUiMode='PVE';s.gameMode='PVE';s.gameState='PLAYING';s.session.tableLocked.value=true;s.soundMuted=true;
      s.enableEV=true;s.latestDrawnTile=null;s.localRecommend=null;
      Object.assign(s.roundState,{handTiles:hand,seatWind:'E',roundWind:'E',isDealer:true,dealerTile:'6p',melds:[],discards:[],opponents:opponents.map(o=>({...o,hand_tiles:[]}))});
      s.roundState.opponents.find(o=>o.seat_wind==='N').discards=['8p'];
      s.currentTurnSeat='N';s.lastDiscardSeat='N';s.currentPhase='OPPONENT_DISCARD_ACTION';
      s.lastStepResult={...result,need_self_action:true,_response_tile:'8p',
        _table_responses:[{seat:'E',types:['chi'],chiCombos:[['P','7p','8p'],['7p','8p','9p']]}]};
      window.__meldRequests=[];
    };
  })()`)
  await evaluate('window.__loadMeldFixture()')
  await until(()=>evaluate(`document.querySelectorAll('.action-prompt-docked button[data-action="chi"]').length===2`))
  const layouts=[]
  for (const [width,height] of [[390,844],[844,390],[1280,720]]) {
    await command('Emulation.setDeviceMetricsOverride',{width,height,deviceScaleFactor:1,mobile:false})
    await sleep(250)
    const result=await evaluate(`(() => {
      const panel=document.querySelector('.action-prompt-panel'),r=panel.getBoundingClientRect();
      const buttons=[...panel.querySelectorAll('button[data-action="chi"]')];
      const visible=el=>{const r=el.getBoundingClientRect();return r.width>0&&r.height>0&&getComputedStyle(el).visibility!=='hidden';};
      const badge=panel.querySelector('.action-recommend-badge');
      const chosen=badge?.closest('button');
      const expected=window.__expectedRecommendation;
      return {combos:buttons.map(button=>({tiles:[...button.querySelectorAll('.action-preview-tile')].map(tile=>tile.dataset.tile),
        visible:visible(button.querySelector('.action-meld-preview')),
        sizes:[...button.querySelectorAll('.action-preview-tile')].map(tile=>[tile.offsetWidth,tile.offsetHeight]),
        claimed:button.querySelectorAll('.action-claimed-tile').length})),
        recommendationMatches:visible(badge)&&chosen.dataset.action===expected.action_type&&
          (expected.action_type==='pass'||chosen.dataset.actionKey.split('|')[1]===[...expected.tiles].sort().join(',')),
        noScroll:panel.scrollWidth<=panel.clientWidth&&panel.scrollHeight<=panel.clientHeight,
        fits:r.left>=0&&r.top>=0&&r.right<=innerWidth&&r.bottom<=innerHeight};
    })()`)
    assert.deepEqual(result.combos.map(c=>c.tiles.join(',')).sort(), ['7p,8p,9p','P,7p,8p'].sort())
    assert.ok(result.combos.every(c=>c.visible&&c.claimed===1&&c.sizes.every(([w,h])=>w===24&&h===32)),JSON.stringify(result))
    assert.ok(result.recommendationMatches&&result.noScroll&&result.fits,JSON.stringify(result))
    layouts.push({width,height,...result})
  }
  await mkdir('tests/artifacts/meld-options',{recursive:true})
  const shot=await command('Page.captureScreenshot',{format:'png'})
  await writeFile('tests/artifacts/meld-options/multiple-chi.png',Buffer.from(shot.data,'base64'))
  for (const white of [true,false]) {
    if (!white) await evaluate('window.__loadMeldFixture()')
    await until(()=>evaluate(`!!document.querySelector('button[data-action="chi"]:not(:disabled)')`))
    await evaluate(`(() => {
      const buttons=[...document.querySelectorAll('button[data-action="chi"]')];
      buttons.find(button=>!!button.querySelector('[data-tile="P"]')===${white}).click();
    })()`)
    await until(()=>evaluate(`(() => {const s=document.querySelector('#app').__vue_app__._instance.setupState;return (window.__meldRequests.length>0||s.sessionError||s.analyzeError)&&!s.stepLoading})()`))
    const state=await evaluate(`(() => {
      const s=document.querySelector('#app').__vue_app__._instance.setupState;
      return JSON.parse(JSON.stringify({hand:[...s.roundState.handTiles],meld:s.roundState.melds[0],
        river:s.roundState.opponents.find(o=>o.seat_wind==='N').discards,
        phase:s.currentPhase,error:s.sessionError,requests:window.__meldRequests}));
    })()`)
    assert.equal(state.requests[0].status,200,JSON.stringify(state))
    assert.equal(state.error,'',JSON.stringify(state))
    assert.ok(Array.isArray(state.meld?.tiles),JSON.stringify(state))
    assert.deepEqual([...state.meld.tiles].sort(),(white?['P','7p','8p']:['7p','8p','9p']).sort())
    assert.equal(state.meld.claimed_tile,'8p')
    assert.equal(state.meld.provider_seat,'N')
    assert.equal(state.hand.length,11)
    assert.equal(state.hand.includes('P'),!white)
    assert.equal(state.hand.includes('9p'),white)
    assert.equal(state.hand.includes('7p'),false)
    assert.deepEqual(state.river,[])
    assert.equal(state.phase,'MY_TURN_DISCARD')
  }
  // No EV response: local legal actions must not manufacture a recommendation.
  await evaluate(`(async()=>{await window.__loadMeldFixture();document.querySelector('#app').__vue_app__._instance.setupState.lastStepResult.call_decision=null})()`)
  await sleep(100)
  assert.equal(await evaluate(`document.querySelectorAll('.action-recommend-badge').length`),0)
  console.log(JSON.stringify({status:'passed',physicalClaimsVerified:2,layouts},null,2))
} finally {
  if (socket?.readyState===WebSocket.OPEN) {
    try { await command('Browser.close') } catch {}
    socket.close()
  }
  chrome.kill()
}
