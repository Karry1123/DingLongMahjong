import assert from 'node:assert/strict'
import { spawn } from 'node:child_process'
import { mkdir, mkdtemp, writeFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { northDiscardDeal } from '../tests/pveFixture.js'

const port = 9341
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
const shotDir = 'tests/artifacts/zoom-review'
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
      if (path.endsWith('/game/auto-deal')) return Promise.resolve(new Response(JSON.stringify(${JSON.stringify(northDiscardDeal())}), {headers:{'Content-Type':'application/json'}}));
      if (path.endsWith('/game/records')) return Promise.resolve(new Response(JSON.stringify({records:[summary]}), {headers:{'Content-Type':'application/json'}}));
      if (path.endsWith('/game/records/GM-ZOOM01')) return Promise.resolve(new Response(JSON.stringify(record), {headers:{'Content-Type':'application/json'}}));
      return originalFetch(url, init);
    };
  ` })
  await command('Page.navigate', { url: process.env.PVE_URL || 'http://127.0.0.1:5173/' })
  await until(() => evaluate(`!![...document.querySelectorAll('button')].find(button=>button.textContent.includes('人机对战'))`))
  await evaluate(`[...document.querySelectorAll('button')].find(button=>button.textContent.includes('人机对战')).click()`)
  await until(() => evaluate(`!![...document.querySelectorAll('button')].find(button=>button.textContent.includes('开始对战'))`))
  await evaluate(`document.querySelector('[aria-label="人机对战设置"] input[type="checkbox"]').click()`)
  await evaluate(`[...document.querySelectorAll('button')].find(button=>button.textContent.includes('开始对战')).click()`)
  await until(() => evaluate(`!!document.querySelector('.pve-self-hand')`))
  await until(() => evaluate(`performance.getEntriesByType('resource').filter(entry=>entry.name.includes('/audio/tiles/')).length===38`))
  await evaluate(`if (document.fullscreenElement) document.exitFullscreen()`)

  await command('Emulation.setDeviceMetricsOverride', { width:844,height:390,deviceScaleFactor:1,mobile:true })
  await evaluate(`(() => {const s=document.querySelector('#app').__vue_app__._instance.setupState;
    const dealer=s.roundState.dealerTile;
    s.roundState.handTiles=[dealer,'1m','2m','3m','4m','5m','6m','7m','8m','9m','1p','2p','3p','4p'];
    s.currentTurnSeat=s.roundState.seatWind;
    s.currentPhase='MY_TURN_DISCARD';
  })()`)
  await sleep(80)
  const dragPoints = async (from,to) => evaluate(`(() => {
    const buttons=[...document.querySelectorAll('.pve-self-hand button[data-hand-index]')];
    const center=button=>{const r=button.getBoundingClientRect();return {x:r.left+r.width/2,y:r.top+r.height/2}};
    const first=center(buttons[0]),last=center(buttons.at(-1)),target=center(buttons[${to}]);
    const length=Math.hypot(last.x-first.x,last.y-first.y),step=length/(buttons.length-1);
    return {from:center(buttons[${from}]),to:{x:target.x-(last.x-first.x)/length*step*.28,
      y:target.y-(last.y-first.y)/length*step*.28}};
  })()`)
  const mouse = await dragPoints(0,5)
  await command('Input.dispatchMouseEvent', {type:'mouseMoved',x:mouse.from.x,y:mouse.from.y})
  await command('Input.dispatchMouseEvent', {type:'mousePressed',x:mouse.from.x,y:mouse.from.y,button:'left',clickCount:1})
  await command('Input.dispatchMouseEvent', {type:'mouseMoved',x:mouse.to.x,y:mouse.to.y,button:'left',buttons:1})
  assert.ok(await evaluate(`!!document.querySelector('.pve-self-hand .hand-dragging')&&!!document.querySelector('.pve-self-hand .hand-insert-before')`), 'mouse drag feedback missing')
  await capture('hand-mouse-drag')
  await command('Input.dispatchMouseEvent', {type:'mouseReleased',x:mouse.to.x,y:mouse.to.y,button:'left',clickCount:1})
  await until(() => evaluate(`(() => {const s=document.querySelector('#app').__vue_app__._instance.setupState;
    return s.roundState.handTiles[4]===s.roundState.dealerTile&&s.handLayoutPinned.E===true&&s.roundState.discards.length===0;})()`))

  await command('Emulation.setDeviceMetricsOverride', { width:390,height:844,deviceScaleFactor:1,mobile:true })
  await command('Emulation.setTouchEmulationEnabled', { enabled:true })
  await sleep(300)
  const touch = await dragPoints(6,2)
  await command('Input.dispatchTouchEvent', {type:'touchStart',touchPoints:[{x:touch.from.x,y:touch.from.y,id:1}]})
  await sleep(40)
  await command('Input.dispatchTouchEvent', {type:'touchMove',touchPoints:[{x:touch.from.x+(touch.to.x-touch.from.x)*.4,y:touch.from.y+(touch.to.y-touch.from.y)*.4,id:1}]})
  await sleep(40)
  await command('Input.dispatchTouchEvent', {type:'touchMove',touchPoints:[{x:touch.to.x,y:touch.to.y,id:1}]})
  await until(() => evaluate(`!!document.querySelector('.pve-self-hand .hand-dragging')&&!!document.querySelector('.pve-self-hand .hand-insert-before')`), 3000)
  await capture('hand-touch-drag')
  await command('Input.dispatchTouchEvent', {type:'touchEnd',touchPoints:[]})
  await until(() => evaluate(`(() => {const s=document.querySelector('#app').__vue_app__._instance.setupState;
    return s.roundState.handTiles[2]==='6m'&&s.roundState.discards.length===0;})()`))
  await command('Emulation.setTouchEmulationEnabled', { enabled:false })

  const layouts = []
  for (const [width, height] of [[390,844],[844,390],[1163,537],[1280,720]]) {
    await command('Emulation.setDeviceMetricsOverride', { width, height, deviceScaleFactor:1, mobile:width<1000 })
    await sleep(250)
    const result = await evaluate(`(() => {
      const r = el => el.getBoundingClientRect();
      const inside = (a,b) => a.left>=b.left-2&&a.top>=b.top-2&&a.right<=b.right+2&&a.bottom<=b.bottom+2;
      const stage=r(document.querySelector('.game-stage'));
      const main=r(document.querySelector('.pve-game-main'));
      const board=r(document.querySelector('.pve-table'));
      const hand=r(document.querySelector('.pve-self-hand'));
      const viewport={left:0,top:0,right:innerWidth,bottom:innerHeight};
      const river=[...document.querySelectorAll('.discard-river')].map(r);
      const tiles=[...document.querySelectorAll('.pve-self-hand button[role="listitem"]')].map(r);
      return {viewport:[innerWidth,innerHeight],stageFits:inside(stage,viewport),mainFits:inside(main,stage),
        boardFits:inside(board,stage),handFits:inside(hand,stage),riverFits:river.every(x=>inside(x,stage)),
        tilesFit:tiles.every(x=>inside(x,hand)),handGap:Math.abs(innerHeight>innerWidth ? hand.left-board.right : hand.top-board.bottom),
        mainScale:getComputedStyle(document.querySelector('.pve-game-main')).transform,
        noPageScroll:document.documentElement.scrollWidth<=innerWidth+1&&document.documentElement.scrollHeight<=innerHeight+1};
    })()`)
    assert.ok(result.stageFits&&result.mainFits&&result.boardFits&&result.handFits&&result.riverFits&&result.tilesFit&&result.noPageScroll, `${width}x${height}: clipped: ${JSON.stringify(result)}`)
    assert.ok(result.mainScale.startsWith('matrix(1.2, 0, 0, 1.2,'), `${width}x${height}: missing 20% zoom`)
    assert.ok(result.handGap<=1, `${width}x${height}: hand is separated from board: ${result.handGap}`)
    layouts.push(result)
    if (width===844 || width===1163) await capture(`board-${width}x${height}`)
  }

  await evaluate(`(() => {const s=document.querySelector('#app').__vue_app__._instance.setupState;
    const tiles=['1m','2m','3m','4m','5m','6m','7m','8m','9m','1p','2p','3p','4p','5p','6p','7p','8p','9p','1s','2s','3s','4s','5s','6s'];
    s.roundState.discards=[...tiles];
    s.roundState.opponents.forEach((opponent,index)=>{opponent.discards=[...tiles];opponent.melds=[
      {meld_type:'chi',tiles:['1m','2m','3m']},{meld_type:'pong',tiles:['4m','4m','4m']},
      {meld_type:'chi',tiles:['5m','6m','7m']}];});
    s.roundState.melds=[{meld_type:'pong',tiles:['3m','3m','3m']},{meld_type:'pong',tiles:['4m','4m','4m']},
      {meld_type:'pong',tiles:['5m','5m','5m']}];
  })()`)
  for (const [width,height] of [[844,390],[1163,537]]) {
    await command('Emulation.setDeviceMetricsOverride', { width,height,deviceScaleFactor:1,mobile:width<1000 })
    await sleep(100)
    const crowded=await evaluate(`(() => {
      const r=x=>document.querySelector(x).getBoundingClientRect();
      const overlap=(a,b)=>a.left<b.right&&a.right>b.left&&a.top<b.bottom&&a.bottom>b.top;
      const center=r('.table-center'),board=r('.pve-table');
      const hand=r('.pve-self-hand');
      const rivers=['.opponent-seat.top > .discard-river','.opponent-seat.left > .discard-river',
        '.opponent-seat.right > .discard-river','.self-river .discard-river'].map(r);
      const melds=[...document.querySelectorAll('.pve-self-controls .compact-melds .mahjong-tile')].map(x=>x.getBoundingClientRect());
      const within=x=>x.left>=board.left-1&&x.top>=board.top-1&&x.right<=board.right+1&&x.bottom<=board.bottom+1;
      return {riversFit:rivers.every(within),riversClear:rivers.every(x=>!overlap(x,center))&&rivers.every((x,i)=>rivers.every((y,j)=>i===j||!overlap(x,y))),
        overlappingPairs:rivers.flatMap((x,i)=>rivers.flatMap((y,j)=>i<j&&overlap(x,y)?[[i,j]]:[])),
        centerOverlaps:rivers.flatMap((x,i)=>overlap(x,center)?[i]:[]),
        topRiver:rivers[0].toJSON(),center:center.toJSON(),
        seamGap:Math.abs(hand.top-board.bottom),
        meldsFit:melds.every(within),meldsClear:melds.every(x=>!overlap(x,rivers[1])),meldCount:melds.length};
    })()`)
    assert.ok(crowded.riversFit&&crowded.riversClear&&crowded.meldsFit&&crowded.meldsClear&&crowded.meldCount===9&&crowded.seamGap<=1,
      `${width}x${height}: crowded board overlaps: ${JSON.stringify(crowded)}`)
    await capture(`board-crowded-${width}x${height}`)
  }

  await evaluate(`(() => {const s=document.querySelector('#app').__vue_app__._instance.setupState;
    s.gameState='GAME_OVER';s.selfWinSettlement={win_type:'draw',is_draw:true,game_id:'GM-ZOOM01',net_by_seat:{E:0,S:0,W:0,N:0}};
    s.showGameOverModal=false;s.showRoundSummaryModal=true;})()`)
  await until(() => evaluate(`!!document.querySelector('.circle-panel')`))
  for (const [width,height] of [[390,844],[844,390],[1280,720]]) {
    await command('Emulation.setDeviceMetricsOverride', { width,height,deviceScaleFactor:1,mobile:width<1000 })
    await sleep(100)
    const result=await evaluate(`(() => {const r=document.querySelector('.circle-panel').getBoundingClientRect();
      const buttons=[...document.querySelectorAll('.circle-actions button')].map(x=>x.getBoundingClientRect());
      const inside=x=>x.left>=-1&&x.top>=-1&&x.right<=innerWidth+1&&x.bottom<=innerHeight+1;
      const back=document.querySelector('.circle-back'),b=back.getBoundingClientRect();
      return {fits:inside(r)&&buttons.every(inside),landscape:document.querySelector('.circle-panel').offsetWidth>document.querySelector('.circle-panel').offsetHeight,
        backHit:document.elementFromPoint((b.left+b.right)/2,(b.top+b.bottom)/2)?.closest('button')===back,
        back:document.querySelector('.circle-back')?.textContent.trim()};})()`)
    assert.ok(result.fits&&result.landscape&&result.backHit&&result.back==='返回本局结算', `${width}x${height}: circle modal: ${JSON.stringify(result)}`)
    if(width===390) await capture('circle-portrait')
    if(width===844) await capture('circle-landscape')
  }
  await evaluate(`document.querySelector('.circle-back').click()`)
  await until(() => evaluate(`!!document.querySelector('.game-over-panel')&&!document.querySelector('.circle-panel')`))
  await evaluate(`document.querySelector('.landscape-settlement-history-button').click()`)
  await until(() => evaluate(`!!document.querySelector('.history-row')`))
  for (const [width,height] of [[390,844],[844,390],[1280,720]]) {
    await command('Emulation.setDeviceMetricsOverride', { width,height,deviceScaleFactor:1,mobile:width<1000 })
    await sleep(100)
    const result=await evaluate(`(() => {const modal=document.querySelector('.history-modal');const r=modal.getBoundingClientRect();
      const load=modal.querySelector('.history-actions button:last-child'),b=load.getBoundingClientRect();
      return {fits:r.left>=-1&&r.top>=-1&&r.right<=innerWidth+1&&r.bottom<=innerHeight+1,
        loadHit:document.elementFromPoint((b.left+b.right)/2,(b.top+b.bottom)/2)?.closest('button')===load,
        landscape:modal.offsetWidth>modal.offsetHeight,scroll:document.documentElement.scrollWidth<=innerWidth+1};})()`)
    assert.ok(result.fits&&result.landscape&&result.scroll&&result.loadHit, `${width}x${height}: history modal: ${JSON.stringify(result)}`)
    if(width===390) await capture('history-portrait')
    if(width===844) await capture('history-landscape')
  }
  await evaluate(`document.querySelector('.history-actions button:last-child').click()`)
  await until(() => evaluate(`!!document.querySelector('.history-replay-seats')`))
  await evaluate(`document.querySelector('.history-replay-controls button:last-child').click()`)
  assert.ok(await evaluate(`document.querySelector('.history-replay-controls').textContent.includes('第 2 / 2 步')`), 'history step navigation failed')
  await command('Emulation.setDeviceMetricsOverride', { width:844,height:390,deviceScaleFactor:1,mobile:true })
  await sleep(100)
  await capture('replay-landscape')
  console.log(JSON.stringify({status:'passed',layouts},null,2))
} finally {
  if (socket?.readyState===WebSocket.OPEN) {
    try { await command('Browser.close') } catch {}
    socket.close()
  }
  chrome.kill()
}
