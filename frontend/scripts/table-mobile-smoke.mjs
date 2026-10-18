import assert from 'node:assert/strict'
import { spawn } from 'node:child_process'
import { mkdtemp } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { northDiscardDeal } from '../tests/pveFixture.js'

const port = 9337
const profile = await mkdtemp(join(tmpdir(), 'mahjong-mobile-safe-'))
const chrome = spawn(process.env.CHROME_PATH || 'C:/Program Files/Google/Chrome/Application/chrome.exe', [
  '--headless=new', '--no-sandbox', '--disable-gpu-sandbox', '--in-process-gpu', '--disable-gpu', '--no-first-run', '--no-default-browser-check',
  `--remote-debugging-port=${port}`, '--remote-allow-origins=*', `--user-data-dir=${profile}`, 'about:blank',
], { windowsHide: true, stdio: ['ignore', 'ignore', 'pipe'] })
const keepAlive=setInterval(()=>{},1000)
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms))
const pending = new Map()
let socket, id = 0
async function until(fn, timeout = 20000) {
  const deadline = Date.now() + timeout
  while (Date.now() < deadline) {
    const value = await fn()
    if (value) return value
    await sleep(25)
  }
  throw new Error('Landscape browser test timed out')
}
const command = (method, params = {}) => new Promise((resolve, reject) => {
  const requestId = ++id
  const timeout=setTimeout(()=>{pending.delete(requestId);reject(Error(`CDP timeout: ${method}`))},10000)
  pending.set(requestId, { resolve:value=>{clearTimeout(timeout);resolve(value)}, reject:error=>{clearTimeout(timeout);reject(error)} })
  socket.send(JSON.stringify({ id: requestId, method, params }))
})
async function evaluate(expression) {
  const response = await command('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true })
  if (response.exceptionDetails) throw new Error(JSON.stringify(response.exceptionDetails))
  return response.result.value
}

try {
  const page = await until(async () => {
    try { return (await (await fetch(`http://127.0.0.1:${port}/json/list`)).json()).find(p => p.type === 'page') } catch { return null }
  })
  socket = new WebSocket(page.webSocketDebuggerUrl)
  await new Promise(resolve => socket.addEventListener('open', resolve, {once:true}))
  socket.addEventListener('message', ({data}) => {
    const msg=JSON.parse(data), waiter=pending.get(msg.id)
    if (!waiter) return
    pending.delete(msg.id)
    msg.error ? waiter.reject(Error(msg.error.message)) : waiter.resolve(msg.result)
  })
  await command('Page.enable')
  await command('Runtime.enable')
  await command('Page.addScriptToEvaluateOnNewDocument', {source:`
    localStorage.setItem('dl.auth.token','layout-test');
    window.__deals=0;
    window.fetch=async (url, init) => {
      let data={};
      if(String(url).endsWith('/me')) data={id:'layout',display_name:'Layout'};
      if(String(url).endsWith('/invitations')) data={invitations:[]};
      if(String(url).endsWith('/auto-deal')) { window.__deals++; data=${JSON.stringify(northDiscardDeal())}; }
      if(String(url).endsWith('/recommend')) data={best_tile:'N',can_self_win:false};
      return new Response(JSON.stringify(data),{headers:{'Content-Type':'application/json'}});
    };
  `})
  await command('Page.navigate',{url:process.env.PVE_URL || 'http://127.0.0.1:5173/#/pve'})
  const root=`document.querySelector('#app').__vue_app__._instance.setupState`
  await until(() => evaluate(`!!document.querySelector('[aria-label="\u4eba\u673a\u5bf9\u6218\u8bbe\u7f6e"]')`))
  await evaluate(`${root}.enableEV=false; void ${root}.choosePveMode()`)
  await until(() => evaluate(`!!document.querySelector('.god-opening')`))
  const results=[]
  async function check(width,height,safe, selector) {
    await command('Emulation.setDeviceMetricsOverride',{width,height,deviceScaleFactor:1,mobile:true})
    await command('Emulation.setSafeAreaInsetsOverride',{insets:safe})
    await evaluate(`window.dispatchEvent(new Event('resize'))`)
    await sleep(80)
    const result=await evaluate(`(() => {
      const rect=e=>{const r=e.getBoundingClientRect();return {left:r.left,right:r.right,top:r.top,bottom:r.bottom}};
      const stage=document.querySelector('.game-stage'), hud=document.querySelector('[aria-label="\u8f6e\u6b21\u72b6\u6001"]');
      const buttons=[...hud.querySelectorAll('button')].map(e=>({rect:rect(e),clickable:(()=>{const r=e.getBoundingClientRect();return e.contains(document.elementFromPoint((r.left+r.right)/2,(r.top+r.bottom)/2))})()}));
      const extra=document.querySelector(${JSON.stringify(selector)});
      const content=[...extra.querySelectorAll('button, .mahjong-tile, .god-opening-copy')].filter(e=>e.getBoundingClientRect().width>0).map(rect);
      return {content, stage:rect(stage),hud:rect(hud),buttons,extra:rect(document.querySelector(${JSON.stringify(selector)})),scroll:document.documentElement.scrollWidth-innerWidth};
    })()`)
    const inside=r=>r.left>=safe.left-1&&r.right<=width-safe.right+1&&r.top>=safe.top-1&&r.bottom<=height-safe.bottom+1
    assert.ok(inside(result.stage),`stage clipped ${width}x${height}: ${JSON.stringify(result)}`)
    assert.ok(inside(result.hud),`HUD clipped ${width}x${height}`)
    assert.ok(inside(result.extra),`${selector} clipped ${width}x${height}`)
    assert.ok(result.buttons.every(b=>inside(b.rect)),`button clipped ${width}x${height}`)
    if(selector==='.pve-self-hand'||selector==='.action-prompt-panel') assert.ok(result.buttons.every(b=>b.clickable),`button covered ${width}x${height}: ${JSON.stringify(result.buttons)}`)
    assert.ok(result.content.every(inside),`content outside safe bounds ${width}x${height} ${selector}`)
    assert.ok(result.scroll<=1,`horizontal scroll ${width}x${height}`)
    results.push({width,height,selector,safe})
  }
  const sizes=[[320,568],[375,812],[412,915],[540,1080],[1080,540],[812,375],[915,412]]
  const safeFor=(w,h)=>h>w?{top:44,left:0,right:0,bottom:34}:{top:0,left:44,right:28,bottom:21}
  for(const [w,h] of sizes) await check(w,h,safeFor(w,h),'.god-opening')
  await evaluate(`${root}.completeGodOpening(true)`)
  await until(() => evaluate(`${root}.isPlaying`))
  for(const [w,h] of sizes) await check(w,h,safeFor(w,h),'.pve-self-hand')
  await evaluate(`(() => {
    const s=${root};window.__oldPhase=s.currentPhase;window.__oldStep=s.lastStepResult;
    s.currentPhase='OPPONENT_DISCARD_ACTION';
    s.lastStepResult={need_self_action:true,_response_tile:'3m',call_decision:{
      recommended_action:{action_type:'chi',tiles:['2m','4m'],provider_seat:'N'},
      candidates:[{action:{action_type:'chi',tiles:['2m','4m'],provider_seat:'N'},net_ev:10},{action:{action_type:'pass',tiles:[],provider_seat:'N'},net_ev:0}]}};
  })()`)
  await until(() => evaluate(`!!document.querySelector('.action-prompt-panel')`))
  for(const [w,h] of sizes) await check(w,h,safeFor(w,h),'.action-prompt-panel')
  await evaluate(`${root}.currentPhase=window.__oldPhase;${root}.lastStepResult=window.__oldStep;void ${root}.declareDraw('layout')`)
  await until(() => evaluate(`!!document.querySelector('.game-over-panel')`))
  for(const [w,h] of sizes) await check(w,h,safeFor(w,h),'.game-over-panel')
  const oldId=await evaluate(`${root}.gameRoundId`)
  await evaluate(`document.querySelector('[aria-label="\u8f6e\u6b21\u72b6\u6001"] button:last-child').click()`)
  await until(() => evaluate(`location.hash==='#/home'`))
  assert.deepEqual(await evaluate(`({mode:${root}.gameMode,state:${root}.gameState,hand:${root}.roundState.handTiles.length,deals:window.__deals})`),{mode:'SANDBOX',state:'SETUP',hand:0,deals:1})
  await evaluate(`location.hash='/pve'`)
  await until(() => evaluate(`!!document.querySelector('[aria-label="\u4eba\u673a\u5bf9\u6218\u8bbe\u7f6e"]')`))
  await evaluate(`void ${root}.choosePveMode()`)
  await until(() => evaluate(`!!document.querySelector('.god-opening')`))
  await evaluate(`${root}.completeGodOpening(true)`)
  await until(() => evaluate(`${root}.isPlaying`))
  assert.notEqual(await evaluate(`${root}.gameRoundId`),oldId)
  // Browser/Android back changes the route without clicking the HUD.
  await evaluate(`location.hash='/home'`)
  await until(() => evaluate(`${root}.gameMode==='SANDBOX'`))
  assert.equal(await evaluate(`window.__deals`),2)
  console.log(JSON.stringify({status:'passed',checks:results.length,viewports:sizes,exit:'button and direct route; fresh reentry'},null,2))
} finally {
  clearInterval(keepAlive)
  socket?.close()
  chrome.kill()
}

