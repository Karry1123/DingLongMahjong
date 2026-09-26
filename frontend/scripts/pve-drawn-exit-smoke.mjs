import assert from 'node:assert/strict'
import { spawn } from 'node:child_process'
import { mkdir, mkdtemp, writeFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { northDiscardDeal } from '../tests/pveFixture.js'

const port = 9343
const profile = await mkdtemp(join(tmpdir(), 'mahjong-zoom-'))
const chrome = spawn(process.env.CHROME_PATH || 'C:/Program Files/Google/Chrome/Application/chrome.exe', [
  '--headless=new', '--disable-gpu', '--no-first-run', '--no-default-browser-check',
  `--remote-debugging-port=${port}`, '--remote-allow-origins=*', `--user-data-dir=${profile}`, 'about:blank',
], { windowsHide: true, stdio: ['ignore', 'ignore', 'pipe'] })
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms))
const pending = new Map()
let socket, id = 0
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
async function until(fn, timeout = 20000) {
  const deadline = Date.now() + timeout
  while (Date.now() < deadline) {
    const value = await fn()
    if (value) return value
    await sleep(40)
  }
  throw new Error('Zoom review timed out')
}
const shotDir = 'tests/artifacts/drawn-exit'
async function capture(name) {
  await mkdir(shotDir, { recursive: true })
  const shot = await command('Page.captureScreenshot', { format: 'png' })
  await writeFile(`${shotDir}/${name}.png`, Buffer.from(shot.data, 'base64'))
}

try {
  const page = await until(async () => {
    try { return (await (await fetch(`http://127.0.0.1:${port}/json/list`)).json()).find(item => item.type === 'page') }
    catch { return null }
  })
  socket = new WebSocket(page.webSocketDebuggerUrl)
  await new Promise(resolve => socket.addEventListener('open', resolve, { once: true }))
  socket.addEventListener('message', ({ data }) => {
    const message = JSON.parse(data)
    const waiter = pending.get(message.id)
    if (!waiter) return
    pending.delete(message.id)
    message.error ? waiter.reject(new Error(message.error.message)) : waiter.resolve(message.result)
  })
  await command('Runtime.enable')
  await command('Page.enable')
  await command('Network.enable')
  await command('Network.setUserAgentOverride', { userAgent:'Mozilla/5.0 Chrome/120.0.0.0 Mobile MicroMessenger/8.0.0' })
  await command('Page.addScriptToEvaluateOnNewDocument', { source: `
    const originalFetch = window.fetch.bind(window);
    const record = {game_id:'GM-ZOOM01',round_id:'zoom',timestamp:new Date().toISOString(),
      config:{seat_wind:'E',initial_hands:{E:['1m','2m','3m'],S:['4m'],W:['5m'],N:['6m']}},
      steps:[{seat:'E',action:'DISCARD',tile:'1m'},{seat:'S',action:'DISCARD',tile:'4m'}]};
    const summary = {game_id:record.game_id,round_wind:'E',self_seat:'E',timestamp:record.timestamp,
      win_type:'draw',winner_name:'荒牌流局',self_score:{net:0},xiajia_score:{net:0},
      duijia_score:{net:0},shangjia_score:{net:0}};
    window.fetch = (url, init) => {
      const path = String(url);
      if (path.endsWith('/game/step')) return new Promise(() => {});
      if (path.endsWith('/game/auto-deal')) return Promise.resolve(new Response(JSON.stringify(${JSON.stringify(northDiscardDeal())}), {headers:{'Content-Type':'application/json'}}));
      if (path.endsWith('/game/records')) return Promise.resolve(new Response(JSON.stringify({records:[summary]}), {headers:{'Content-Type':'application/json'}}));
      if (path.endsWith('/game/records/GM-ZOOM01')) return Promise.resolve(new Response(JSON.stringify(record), {headers:{'Content-Type':'application/json'}}));
      return originalFetch(url, init);
    };
  ` })
  await command('Page.navigate', { url: process.env.PVE_URL || 'http://127.0.0.1:5178/' })
  await until(() => evaluate(`!![...document.querySelectorAll('button')].find(button=>button.textContent.includes('人机对战'))`))
  await evaluate(`[...document.querySelectorAll('button')].find(button=>button.textContent.includes('人机对战')).click()`)
  await until(() => evaluate(`!![...document.querySelectorAll('button')].find(button=>button.textContent.includes('开始对战'))`))
  await evaluate(`document.querySelector('[aria-label="人机对战设置"] input[type="checkbox"]').click()`)
  await evaluate(`[...document.querySelectorAll('button')].find(button=>button.textContent.includes('开始对战')).click()`)
  await until(() => evaluate(`!!document.querySelector('.pve-self-hand')`))

  await sleep(500)
  for (const [width, height] of [[1280,720], [844,390], [390,844]]) {
    await command('Emulation.setDeviceMetricsOverride', {width,height,deviceScaleFactor:1,mobile:width<1000})
    await command('Emulation.setTouchEmulationEnabled', {enabled:width<1000})
    await evaluate(`(() => {
      const s=document.querySelector('#app').__vue_app__._instance.setupState;
      s.stepLoading=false;
      s.roundState.handTiles=['1m','2m','3m','4m','5m','6m','7m','8m','9m','1p','2p','3p','N','N'];
      s.roundState.melds=[]; s.roundState.discards=[];
      s.latestDrawnTile='N'; s.currentTurnSeat=s.roundState.seatWind;
      s.currentPhase='MY_TURN_DISCARD';
    })()`)
    await sleep(250)
    const point=await evaluate(`(() => {
      const button=document.querySelector('.pve-drawn-slot button');
      const r=button.getBoundingClientRect(), x=r.x+r.width/2,y=r.y+r.height/2;
      return {x,y,hit:button.contains(document.elementFromPoint(x,y))};
    })()`)
    assert.ok(point.hit, `drawn tile is obscured at ${width}x${height}`)
    await capture(`${width}x${height}`)
    if(width<1000) {
      await command('Input.dispatchTouchEvent',{type:'touchStart',touchPoints:[{x:point.x,y:point.y}]})
      await command('Input.dispatchTouchEvent',{type:'touchEnd',touchPoints:[]})
    } else {
      await command('Input.dispatchMouseEvent',{type:'mousePressed',x:point.x,y:point.y,button:'left',clickCount:1})
      await command('Input.dispatchMouseEvent',{type:'mouseReleased',x:point.x,y:point.y,button:'left',clickCount:1})
    }
    await until(()=>evaluate(`document.querySelector('#app').__vue_app__._instance.setupState.roundState.discards.length===1`),3000)
    const state=await evaluate(`(() => {const s=document.querySelector('#app').__vue_app__._instance.setupState;
      return {hand:[...s.roundState.handTiles],river:[...s.roundState.discards],drawn:s.latestDrawnTile};})()`)
    assert.equal(state.hand.length,13)
    assert.equal(state.hand.filter(tile=>tile==='N').length,1)
    assert.deepEqual(state.river,['N'])
    assert.equal(state.drawn,null)
    console.log(`${width}x${height}: one tap discards the drawn tile exactly once`)
  }
  await evaluate(`(() => {
    window.exitFrames=[];
    const record=()=>{const s=document.querySelector('#app').__vue_app__._instance.setupState;
      window.exitFrames.push({mode:s.gameMode,home:!!document.querySelector('.home-screen'),table:!!document.querySelector('.pve-self-hand')});};
    window.exitObserver=new MutationObserver(record);
    window.exitObserver.observe(document.querySelector('#app'),{subtree:true,childList:true,attributes:true});
    const frame=()=>{record();window.exitRAF=requestAnimationFrame(frame)};frame();
    const original=window.fetch;
    window.fetch=(url,init)=>String(url).endsWith('/game/auto-deal')
      ? new Promise(resolve=>setTimeout(()=>resolve(original(url,init)),700)):original(url,init);
    [...document.querySelectorAll('button')].find(b=>b.textContent.includes('返回主页')).click();
  })()`)
  await until(()=>evaluate(`!!document.querySelector('.home-screen')`),1000)
  await sleep(1000)
  const frames=await evaluate(`(() => {cancelAnimationFrame(window.exitRAF);window.exitObserver.disconnect();return window.exitFrames;})()`)
  assert.ok(frames.some(f=>f.home))
  assert.ok(!frames.some(f=>f.mode==='SANDBOX'&&(!f.home||f.table)), 'sandbox flashed during exit')
  await capture('home')
  console.log(`Return home: ${frames.length} render/DOM samples, no sandbox flash`)
} finally {
  if(socket?.readyState===WebSocket.OPEN) {try {await command('Browser.close')} catch {} socket.close()}
  chrome.kill()
}

