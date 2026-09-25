import assert from 'node:assert/strict'
import { spawn } from 'node:child_process'
import { mkdtemp, mkdir, writeFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { northDiscardDeal } from '../tests/pveFixture.js'

const port = 9335
const profile = await mkdtemp(join(tmpdir(), 'mahjong-landscape-'))
const chrome = spawn(process.env.CHROME_PATH || 'C:/Program Files/Google/Chrome/Application/chrome.exe', [
  '--headless=new', '--disable-gpu', '--no-first-run', '--no-default-browser-check',
  `--remote-debugging-port=${port}`, '--remote-allow-origins=*', `--user-data-dir=${profile}`, 'about:blank',
], { windowsHide: true, stdio: ['ignore', 'ignore', 'pipe'] })
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
  pending.set(requestId, { resolve, reject })
  socket.send(JSON.stringify({ id: requestId, method, params }))
})
async function evaluate(expression) {
  const response = await command('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true })
  if (response.exceptionDetails) throw new Error(JSON.stringify(response.exceptionDetails))
  return response.result.value
}

try {
  const page = await until(async () => {
    try { return (await (await fetch(`http://127.0.0.1:${port}/json/list`)).json()).find((entry) => entry.type === 'page') }
    catch { return null }
  })
  socket = new WebSocket(page.webSocketDebuggerUrl)
  await new Promise((resolve) => socket.addEventListener('open', resolve, { once: true }))
  socket.addEventListener('message', ({ data }) => {
    const msg = JSON.parse(data)
    const waiter = pending.get(msg.id)
    if (!waiter) return
    pending.delete(msg.id)
    msg.error ? waiter.reject(new Error(msg.error.message)) : waiter.resolve(msg.result)
  })
  await command('Runtime.enable')
  await command('Page.enable')
  await command('Page.addScriptToEvaluateOnNewDocument', { source: `
    const realFetch=window.fetch.bind(window);
    window.__threatBodies=[];
    window.__testArchive=null;
    window.fetch=(url,init)=>{
      if(String(url).endsWith('/game/threats')) window.__threatBodies.push(JSON.parse(init.body));
      if(String(url).endsWith('/game/record') && init?.method==='POST') {
        const payload=JSON.parse(init.body);
        window.__testArchive={...payload,game_id:'GM-ABCDEF',timestamp:new Date().toISOString()};
        return Promise.resolve(new Response(JSON.stringify({ok:true,game_id:'GM-ABCDEF',round_id:payload.round_id,
          timestamp:window.__testArchive.timestamp,path:'memory',absolute_path:'memory',
          bytes_written:JSON.stringify(payload).length,steps_count:payload.steps.length}),
          {headers:{'Content-Type':'application/json'}}));
      }
      if(String(url).endsWith('/game/records/GM-ABCDEF') && window.__testArchive)
        return Promise.resolve(new Response(JSON.stringify(window.__testArchive),{headers:{'Content-Type':'application/json'}}));
      return String(url).endsWith('/game/auto-deal')
        ? Promise.resolve(new Response(JSON.stringify(${JSON.stringify(northDiscardDeal())}),{headers:{'Content-Type':'application/json'}}))
        : realFetch(url,init);
    };
  ` })
  await command('Page.navigate', { url: process.env.PVE_URL || 'http://127.0.0.1:5173/' })
  await until(() => evaluate(`!![...document.querySelectorAll('button')].find(button=>button.textContent.includes('人机对战'))`))
  await evaluate(`[...document.querySelectorAll('button')].find(button=>button.textContent.includes('人机对战')).click()`)
  await until(() => evaluate(`!![...document.querySelectorAll('button')].find(button=>button.textContent.includes('开始对战'))`))
  await evaluate(`document.querySelector('[aria-label="人机对战设置"] input[type="checkbox"]').click()`)
  await evaluate(`[...document.querySelectorAll('button')].find(button=>button.textContent.includes('开始对战')).click()`)
  await until(() => evaluate(`!!document.querySelector('.pve-self-hand')`))
  assert.equal(await evaluate(`!!document.querySelector('.pve-discard-hud')`), false)
  const blindCall = await evaluate(`(async () => {
    const session=document.querySelector('#app').__vue_app__._instance.setupState;
    const oldPhase=session.currentPhase, oldStep=session.lastStepResult;
    session.currentPhase='OPPONENT_DISCARD_ACTION';
    session.lastStepResult={...oldStep,need_self_action:true,_response_tile:'3m',call_decision:{
      recommended_action:{action_type:'chi',tiles:['2m','4m'],provider_seat:'N'},
      candidates:[{action:{action_type:'chi',tiles:['2m','4m'],provider_seat:'N'},net_ev:10},{action:{action_type:'pass',tiles:[],provider_seat:'N'},net_ev:0}]}};
    await new Promise(resolve=>setTimeout(resolve,30));
    const panel=document.querySelector('.action-prompt-panel');
    const result={visible:!!panel,hasRecommendation:panel?.textContent.includes('荐'),actions:panel?.querySelectorAll('button[data-action]').length};
    session.currentPhase=oldPhase;session.lastStepResult=oldStep;
    return result;
  })()`)
  assert.deepEqual(blindCall,{visible:true,hasRecommendation:false,actions:2})
  await evaluate(`document.querySelector('#app').__vue_app__._instance.setupState.enableEV=true`)
  await until(() => evaluate(`!!document.querySelector('.pve-discard-hud .hud-tile')`))
  await command('Emulation.setDeviceMetricsOverride', { width: 1298, height: 600, deviceScaleFactor: 1, mobile: false })
  const jokerSelfWin = await evaluate(`(async () => {
    const session=document.querySelector('#app').__vue_app__._instance.setupState;
    const saved={hand:[...session.roundState.handTiles],melds:[...session.roundState.melds],dealer:session.roundState.dealerTile,
      phase:session.currentPhase,turn:session.currentTurnSeat,result:session.lastStepResult};
    session.roundState.handTiles=['C','4m','4m','5m','5m','2s','3s','5s','6s','7s','C'];
    session.roundState.melds=[{meld_type:'pong',tiles:['3m','3m','3m']}];
    session.roundState.dealerTile='C';
    session.currentTurnSeat=session.roundState.seatWind;
    session.currentPhase='MY_TURN_DISCARD';
    session.lastStepResult={...saved.result,can_self_win:true,self_win_info:{is_win:true,win_tile:'C',final_hu:18,base_hu:18,fan:0}};
    await new Promise(resolve=>setTimeout(resolve,80));
    const prompt=document.querySelector('.pve-self-win-prompt');
    const button=prompt?.querySelector('button');
    const bounds=button?.getBoundingClientRect();
    const visible=!!bounds&&bounds.width>0&&bounds.height>0&&bounds.top>=0&&bounds.bottom<=innerHeight&&
      document.elementFromPoint(bounds.left+bounds.width/2,bounds.top+bounds.height/2)?.closest('button')===button;
    const result={visible,winTile:prompt?.textContent.includes('胡张 中'),decisionCard:!!document.querySelector('.pve-discard-hud')};
    session.roundState.handTiles=saved.hand;session.roundState.melds=saved.melds;session.roundState.dealerTile=saved.dealer;
    session.currentPhase=saved.phase;session.currentTurnSeat=saved.turn;session.lastStepResult=saved.result;
    return result;
  })()`)
  assert.deepEqual(jokerSelfWin,{visible:true,winTile:true,decisionCard:false})
  await evaluate(`document.querySelector('#app').__vue_app__._instance.setupState.roundState.opponents[1].melds=[{meld_type:'chi',tiles:['1m','2m','3m']},{meld_type:'chi',tiles:['4m','5m','6m']},{meld_type:'pong',tiles:['E','E','E']}]`)
  await until(() => evaluate(`window.__threatBodies.length>0`))
  assert.equal(await evaluate(`window.__threatBodies.every(body=>body.opponents.every(opponent=>!Object.keys(opponent).some(key=>/hand|hidden|closed/i.test(key))))`), true)
  assert.equal(await evaluate(`!!document.querySelector('.opponent-risk-badge')`), false)
  await evaluate(`(() => { const session=document.querySelector('#app').__vue_app__._instance.setupState; window.__savedWallForThreat=[...session.wallTiles]; session.wallTiles=session.wallTiles.slice(0,55) })()`)
  await until(() => evaluate(`document.querySelector('.opponent-risk-badge')?.textContent.includes('已三副露')`))
  await evaluate(`(() => { const session=document.querySelector('#app').__vue_app__._instance.setupState; session.roundState.opponents[1].melds=[]; session.wallTiles=window.__savedWallForThreat })()`)
  await evaluate(`(() => {
    const session=document.querySelector('#app').__vue_app__._instance.setupState;
    const rightSeat=document.querySelector('.opponent-seat.right').dataset.seat;
    session.roundState.opponents.find(opponent=>opponent.seat_wind===rightSeat).melds=[
      {meld_type:'pong',tiles:['E','E','E']},
      {meld_type:'pong',tiles:['C','C','C']},
      {meld_type:'chi',tiles:['2m','3m','4m'],claimed_tile:'3m'},
    ];
  })()`)
  await evaluate(`(() => {
    const state=document.querySelector('#app').__vue_app__._instance.setupState.roundState;
    const tiles=['1m','2m','3m','4m','5m','6m','7m','8m','9m','1p','2p','3p','4p','5p','6p','7p','8p','9p','1s','2s','3s','4s','5s','6s'];
    state.discards=tiles.slice();
    for (const opponent of state.opponents) opponent.discards=tiles.slice();
  })()`)
  await sleep(50)
  await mkdir('tests/artifacts', { recursive: true })
  const results = []
  for (const [width, height] of [[667, 375], [844, 390], [960, 540], [1298, 600], [1366, 768]]) {
    await command('Emulation.setDeviceMetricsOverride', { width, height, deviceScaleFactor: 1, mobile: false })
    await sleep(100)
    const result = await evaluate(`(() => {
      const rect=(selector)=>document.querySelector(selector).getBoundingClientRect();
      const inside=(a,b)=>a.left>=b.left-1&&a.top>=b.top-1&&a.right<=b.right+1&&a.bottom<=b.bottom+1;
      const page={left:0,top:0,right:innerWidth,bottom:innerHeight};
      const root=document.documentElement;
      const board=rect('.pve-table'),hand=rect('.pve-self-hand'),hud=rect('.pve-discard-hud'),center=rect('.table-center .mahjong-tile');
      const selfRiver=rect('[aria-label="自家牌河"] .discard-river'), topRiver=rect('.opponent-seat.top .discard-river');
      const sideRivers=[rect('.opponent-seat.left .discard-river'),rect('.opponent-seat.right .discard-river')];
      const rightMeld=rect('.opponent-seat.right .meld-area');
      const gapX=Math.max(0,rightMeld.left-hud.right,hud.left-rightMeld.right);
      const gapY=Math.max(0,rightMeld.top-hud.bottom,hud.top-rightMeld.bottom);
      const meldHudGap=Math.hypot(gapX,gapY);
      const riverTiles=[...document.querySelectorAll('.discard-river .mahjong-tile')].map(tile=>tile.getBoundingClientRect());
      const riverUniform=riverTiles.every(tile=>Math.abs(tile.width-riverTiles[0].width)<.6&&Math.abs(tile.height-riverTiles[0].height)<.6);
      const intersects=(a,b)=>a.left<b.right&&a.right>b.left&&a.top<b.bottom&&a.bottom>b.top;
      const seats=[...document.querySelectorAll('.opponent-seat')].map(el=>inside(el.getBoundingClientRect(),board));
      const handTiles=[...document.querySelectorAll('.pve-self-hand button[role="listitem"]')];
      const hudButtons=[...document.querySelectorAll('.pve-discard-hud .hud-tile')];
      const clickable=(button)=>{const r=button.getBoundingClientRect();return document.elementFromPoint((r.left+r.right)/2,(r.top+r.bottom)/2)?.closest('button')===button};
      return {viewport:[innerWidth,innerHeight],scroll:[root.scrollWidth,root.clientWidth,root.scrollHeight,root.clientHeight],
        board:inside(board,page),hand:inside(hand,page),hud:inside(hud,page),center:inside(center,board),seats,
        hudClear:!intersects(hud,hand)&&!intersects(hud,selfRiver)&&sideRivers.every(river=>!intersects(hud,river)),meldHudGap,riverUniform,riverTileWidth:riverTiles[0]?.width,riverCentered:Math.abs((selfRiver.left+selfRiver.right)/2-innerWidth/2)<2,
        riversFit:inside(selfRiver,board)&&inside(topRiver,board)&&topRiver.bottom<selfRiver.top&&sideRivers.every(river=>inside(river,board)),
        centerClear:!intersects(rect('.table-center'),selfRiver)&&sideRivers.every(river=>!intersects(rect('.table-center'),river)),
        clickTargetsClear:handTiles.every(clickable)&&hudButtons.every(clickable),
        handCount:handTiles.length,handFit:handTiles.every(el=>inside(el.getBoundingClientRect(),page)&&!intersects(el.getBoundingClientRect(),hud)),
        topBelowHand:document.querySelector('.opponent-seat.top .discard-river').getBoundingClientRect().top>=document.querySelector('.opponent-seat.top .concealed-hand').getBoundingClientRect().bottom-1,
        debug:{board:board.toJSON(),hand:hand.toJSON(),hud:hud.toJSON(),selfRiver:selfRiver.toJSON(),sideRivers:sideRivers.map(r=>r.toJSON()),sideStyle:getComputedStyle(document.querySelector('.opponent-seat.right .discard-river')).gridTemplateRows,sideTile:rect('.opponent-seat.right .discard-river .mahjong-tile').toJSON(),outsideHand:handTiles.filter(el=>!inside(el.getBoundingClientRect(),hand)).map(el=>el.getBoundingClientRect().toJSON()),center:center.toJSON(),centerSlot:rect('.table-center').toJSON(),topHand:rect('.opponent-seat.top .concealed-hand').toJSON(),topRiver:rect('.opponent-seat.top .discard-river').toJSON()}};
    })()`)
    assert.deepEqual(result.scroll, [width,width,height,height], `${width}x${height} page overflow`)
    if (!(result.board && result.hand && result.hud && result.center && result.seats.every(Boolean) && result.handFit && result.topBelowHand && result.hudClear && result.riverCentered && result.riversFit && result.centerClear && result.clickTargetsClear)) console.error(JSON.stringify(result))
    assert.ok(result.board && result.hand && result.hud && result.center && result.seats.every(Boolean) && result.handFit && result.topBelowHand && result.hudClear && result.meldHudGap>=16 && result.riverUniform && result.riverCentered && result.riversFit && result.centerClear && result.clickTargetsClear, `${width}x${height} clipped or overlapping game layer`)
    if (height>=600) assert.ok(result.riverTileWidth>=24 && result.riverTileWidth<=26, `${width}x${height} river tile size`)
    assert.equal(result.handCount, 14)
    const shot = await command('Page.captureScreenshot', { format: 'png' })
    await writeFile(`tests/artifacts/pve-landscape-${width}x${height}.png`, Buffer.from(shot.data, 'base64'))
    results.push(result)
  }
  const meldRiverGaps=[]
  await evaluate(`(() => {const session=document.querySelector('#app').__vue_app__._instance.setupState;
    window.__savedSelfMelds=session.roundState.melds;
    session.roundState.melds=[
      {meld_type:'pong',tiles:['3m','3m','3m']},
      {meld_type:'pong',tiles:['4m','4m','4m']},
      {meld_type:'pong',tiles:['5m','5m','5m']},
    ];
  })()`)
  for (const [width,height] of [[667,375],[960,540],[1298,600]]) {
    await command('Emulation.setDeviceMetricsOverride',{width,height,deviceScaleFactor:1,mobile:false})
    await sleep(50)
    const gap=await evaluate(`(() => {const river=document.querySelector('.opponent-seat.left > .discard-river').getBoundingClientRect();
      const melds=[...document.querySelectorAll('.pve-self-controls .compact-melds .mahjong-tile')].map(el=>el.getBoundingClientRect());
      return {width:innerWidth,gap:river.left-Math.max(...melds.map(rect=>rect.right)),count:melds.length,
        river:river.toJSON(),meldLeft:Math.min(...melds.map(rect=>rect.left)),meldRight:Math.max(...melds.map(rect=>rect.right)),tileWidth:melds[0]?.width,
        meldContainer:document.querySelector('.pve-self-controls .compact-melds')?.getBoundingClientRect().toJSON()};})()`)
    assert.equal(gap.count,9)
    assert.ok(gap.gap>=32,`${width} self melds overlap left river: ${JSON.stringify(gap)}`)
    meldRiverGaps.push({viewport:[width,height],gap:gap.gap})
  }
  await evaluate(`document.querySelector('#app').__vue_app__._instance.setupState.roundState.melds=window.__savedSelfMelds`)
  await command('Emulation.setDeviceMetricsOverride', { width: 1298, height: 600, deviceScaleFactor: 1, mobile: false })
  const drawerClear = await evaluate(`(async () => {
    const more=document.querySelector('.pve-discard-hud .hud-more');
    if (!more) return {available:false};
    more.click();
    await new Promise(resolve=>setTimeout(resolve,220));
    const drawer=document.querySelector('.pve-discard-hud .hud-drawer')?.getBoundingClientRect();
    const hudElement=document.querySelector('.pve-discard-hud');
    const hud=hudElement.getBoundingClientRect();
    const blockers=[...document.querySelectorAll('.pve-self-hand,.opponent-seat.right .meld-area,.opponent-seat.right .discard-river')].map(el=>el.getBoundingClientRect());
    const intersects=(a,b)=>a.left<b.right&&a.right>b.left&&a.top<b.bottom&&a.bottom>b.top;
    const result={available:true,withinViewport:drawer.left>=0&&drawer.right<=innerWidth&&drawer.top>=0&&drawer.bottom<=innerHeight,
      blockersClear:blockers.every(rect=>!intersects(drawer,rect)),downward:drawer.top>=hud.bottom+3,
      elevated:Number(getComputedStyle(hudElement).zIndex)>=50,
      drawer:drawer.toJSON(),hud:hud.toJSON(),blockers:blockers.map(rect=>rect.toJSON())};
    return result;
  })()`)
  assert.equal(drawerClear.available,true,'HUD has expandable candidates')
  assert.ok(drawerClear.withinViewport&&drawerClear.blockersClear&&drawerClear.downward&&drawerClear.elevated,`HUD drawer layout: ${JSON.stringify(drawerClear)}`)
  const hudShot=await command('Page.captureScreenshot',{format:'png'})
  await writeFile('tests/artifacts/pve-hud-expanded-1298x600.png',Buffer.from(hudShot.data,'base64'))
  await evaluate(`document.querySelector('.pve-discard-hud .hud-more').click()`)
  await command('Emulation.setDeviceMetricsOverride', { width: 844, height: 390, deviceScaleFactor: 1, mobile: false })
  const chi = await evaluate(`(async () => {
    const session=document.querySelector('#app').__vue_app__._instance.setupState;
    session.lastDiscardSeat='N';session.currentPhase='OPPONENT_DISCARD_ACTION';
    session.lastStepResult={...session.lastStepResult,need_self_action:true,_response_tile:'3m',call_decision:{
      recommended_action:{action_type:'chi',tiles:['2m','4m'],provider_seat:'N'},
      candidates:[{action:{action_type:'chi',tiles:['2m','4m'],provider_seat:'N'},net_ev:10},{action:{action_type:'pass',tiles:[],provider_seat:'N'},net_ev:0}],
    }};
    await new Promise(resolve=>setTimeout(resolve,50));
    const button=document.querySelector('.pve-ev-slot button[data-action="chi"]');
    const tiles=[...button?.querySelectorAll('.action-meld-preview > span')||[]];
    return {codes:tiles.map(tile=>tile.textContent.trim()),claimed:tiles.findIndex(tile=>tile.classList.contains('action-claimed-tile')),
      panelTop:document.querySelector('.action-prompt-panel')?.getBoundingClientRect().top,
      handTop:document.querySelector('.pve-self-hand').getBoundingClientRect().top,scrollY:window.scrollY};
  })()`)
  assert.deepEqual(chi.codes, ['二万','三万','四万'])
  assert.equal(chi.claimed, 1)
  assert.ok(chi.panelTop < chi.handTop && chi.scrollY === 0)
  const otherMelds = await evaluate(`(async () => {
    const session=document.querySelector('#app').__vue_app__._instance.setupState;
    const rows=[];
    for (const [type,tiles] of [['pong',['3m','3m']],['ming_gang',['3m','3m','3m']]]) {
      session.currentPhase='OPPONENT_DISCARD_ACTION';
      session.lastStepResult={...session.lastStepResult,need_self_action:true,_response_tile:'3m',call_decision:{
        recommended_action:{action_type:type,tiles,provider_seat:'N'},
        candidates:[{action:{action_type:type,tiles,provider_seat:'N'},net_ev:10},{action:{action_type:'pass',tiles:[],provider_seat:'N'},net_ev:0}],
      }};
      await new Promise(resolve=>setTimeout(resolve,20));
      const cards=[...document.querySelectorAll('.pve-ev-slot button[data-action="'+type+'"] .action-meld-preview > span')];
      rows.push({type,count:cards.length,claimed:cards.filter(card=>card.classList.contains('action-claimed-tile')).length});
    }
    return rows;
  })()`)
  assert.deepEqual(otherMelds, [{type:'pong',count:3,claimed:1},{type:'ming_gang',count:4,claimed:1}])
  await evaluate(`(async () => {
    const session=document.querySelector('#app').__vue_app__._instance.setupState;
    session.roundState.opponents[0].melds=[{meld_type:'chi',tiles:['1m','2m','3m'],claimed_tile:'2m'}];
    session.roundState.opponents[1].melds=[{meld_type:'chi',tiles:['7m','8m','9m'],claimed_tile:'8m'}];
    session.roundState.opponents[2].melds=[{meld_type:'chi',tiles:['7p','8p','9p'],claimed_tile:'8p'}];
    session.roundState.melds=[{meld_type:'chi',tiles:['7s','8s','9s'],claimed_tile:'8s'},{meld_type:'pong',tiles:['1p','1p','1p']}];
    session.roundState.handTiles=['1m','2m','3m','4p','5p','6p','E','E'];
    await session.declareDraw('layout regression');
    await new Promise(resolve=>setTimeout(resolve,70));
    const gameId=document.body.innerText.match(/GM-[0-9A-F]{6}/)?.[0];
    if (!gameId) throw new Error('Settlement did not show archive ID');
    const archive=await (await fetch('/api/game/records/'+gameId)).json();
    if (archive.game_id!==gameId||!archive.config.initial_wall_tiles?.length||archive.final_result.win_type!=='draw') throw new Error('Archive cannot be replayed');
    window.__testGameId=gameId;
    Object.defineProperty(navigator,'clipboard',{configurable:true,value:{writeText:async text=>{window.__copiedGameId=text}}});
    [...document.querySelectorAll('button')].find(button=>button.textContent.trim()==='复制')?.click();
    await new Promise(resolve=>setTimeout(resolve,20));
    if (window.__copiedGameId!==gameId||!document.body.innerText.includes('已复制对局编号')) throw new Error('Archive ID copy failed');
  })()`)
  const fullSettlements=[]
  for (const [width,height] of [[667,375],[1298,600]]) {
    await command('Emulation.setDeviceMetricsOverride',{width,height,deviceScaleFactor:1,mobile:false})
    await sleep(60)
    const layout=await evaluate(`(() => {
      const panel=document.querySelector('.game-over-panel');
      const summary=document.querySelector('.landscape-settlement-summary').getBoundingClientRect();
      const details=document.querySelector('.landscape-settlement-details').getBoundingClientRect();
      const cards=[...document.querySelectorAll('.landscape-settlement-seat')].map(card=>card.getBoundingClientRect());
      const rect=panel.getBoundingClientRect();
      const breakdowns=[...document.querySelectorAll('.landscape-seat-breakdown')];
      const detailFont=breakdowns.length ? parseFloat(getComputedStyle(breakdowns[0]).fontSize) : 0;
      const cardContentVisible=breakdowns.every((item,index)=>item.getBoundingClientRect().bottom<=cards[index].bottom+1);
      return {panel:rect.toJSON(),columnOrder:summary.right<details.left,cards:cards.length,
        cardsVisible:cards.every(card=>card.top>=rect.top&&card.bottom<=rect.bottom&&card.left>=details.left&&card.right<=details.right),
        cardContentVisible,detailFont,overflow:panel.scrollHeight-panel.clientHeight,detailOverflow:document.querySelector('.landscape-settlement-details').scrollHeight-document.querySelector('.landscape-settlement-details').clientHeight};
    })()`)
    assert.equal(layout.columnOrder,true)
    assert.equal(layout.cards,4)
    assert.equal(layout.cardsVisible,true)
    assert.equal(layout.cardContentVisible,true,`${width}x${height} settlement detail clipped`)
    assert.ok(layout.detailFont>=12,`${width}x${height} settlement detail font`)
    assert.ok(layout.overflow<=1&&layout.detailOverflow<=1,`${width}x${height} settlement scroll`)
    assert.ok(layout.panel.width<=1060&&layout.panel.height<=height*.92+1)
    const shot=await command('Page.captureScreenshot',{format:'png'})
    await writeFile(`tests/artifacts/pve-result-full-${width}x${height}.png`,Buffer.from(shot.data,'base64'))
    fullSettlements.push({viewport:[width,height],cards:layout.cards,scroll:false})
  }
  await evaluate(`document.querySelector('#app').__vue_app__._instance.setupState.selfWinSettlement.game_id='GM-E206B3'; document.querySelector('.landscape-settlement-history-button').click()`)
  await until(() => evaluate(`document.querySelectorAll('.history-row').length > 0`))
  const historyList = await evaluate(`(() => {
    const modal=document.querySelector('.history-modal');
    const row=[...modal.querySelectorAll('.history-row')].find(el=>el.textContent.includes('GM-E206B3'));
    const scores=row ? [...row.querySelectorAll('.history-score')].map(el=>el.textContent.trim()) : [];
    const style=getComputedStyle(modal);
    return {target:!!row,first:modal.querySelector('.history-row')?.textContent.includes('GM-E206B3'),scores,rows:modal.querySelectorAll('.history-row').length,
      height:modal.getBoundingClientRect().height,maxHeight:innerHeight*.75,
      rowWrap:row ? getComputedStyle(row).gridTemplateColumns : '',scrollable:style.overflow};
  })()`)
  assert.equal(historyList.target,true)
  assert.equal(historyList.first,true)
  assert.ok(historyList.rows<=10 && historyList.height<=historyList.maxHeight+1)
  assert.ok(historyList.scores[0].includes('+21分') && historyList.scores[1].includes('+24分'))
  assert.ok(historyList.scores[2].includes('-15分') && historyList.scores[3].includes('-30分'))
  const historyShot=await command('Page.captureScreenshot',{format:'png'})
  await writeFile('tests/artifacts/pve-history-1298x600.png',Buffer.from(historyShot.data,'base64'))
  await command('Emulation.setDeviceMetricsOverride',{width:667,height:375,deviceScaleFactor:1,mobile:false})
  await sleep(40)
  const narrowHistory=await evaluate(`(() => {
    const modal=document.querySelector('.history-modal');
    const list=document.querySelector('.history-list-viewport');
    const rows=[...document.querySelectorAll('.history-row')];
    return {height:modal.getBoundingClientRect().height,viewport:innerHeight,
      horizontalScroll:list.scrollWidth>list.clientWidth,
      verticalScroll:list.scrollHeight>list.clientHeight,
      oneLine:rows.every(row=>row.getBoundingClientRect().height<100)};
  })()`)
  assert.ok(narrowHistory.height<=narrowHistory.viewport*.75+1)
  assert.ok(narrowHistory.horizontalScroll && narrowHistory.verticalScroll && narrowHistory.oneLine)
  await command('Emulation.setDeviceMetricsOverride',{width:1298,height:600,deviceScaleFactor:1,mobile:false})
  await evaluate(`(async () => {
    const row=[...document.querySelectorAll('.history-row')].find(el=>el.textContent.includes('GM-E206B3'));
    Object.defineProperty(navigator,'clipboard',{configurable:true,value:{writeText:async text=>{window.__historyCopied=text}}});
    row.querySelector('.history-id-line button').click();
    await new Promise(resolve=>setTimeout(resolve,30));
    row.querySelector('.history-actions button:last-child').click();
  })()`)
  assert.equal(await evaluate(`window.__historyCopied`),'GM-E206B3')
  await until(() => evaluate(`document.querySelector('.history-replay-seats')?.children.length === 4`))
  const replay = await evaluate(`(async () => {
    const panel=document.querySelector('.history-modal');
    const before=panel.textContent.includes('第 1 / 33 步');
    panel.querySelector('.history-replay-controls button:last-child').click();
    await new Promise(resolve=>setTimeout(resolve,30));
    return {before,after:panel.textContent.includes('第 2 / 33 步'),hands:panel.querySelectorAll('.history-replay-seats article').length};
  })()`)
  assert.deepEqual(replay,{before:true,after:true,hands:4})
  await evaluate(`document.querySelector('[aria-label="关闭复盘历史"]').click()`)
  assert.equal(await evaluate(`!!document.querySelector('.history-modal')`),false)
  await evaluate(`document.querySelector('#app').__vue_app__._instance.setupState.selfWinSettlement.game_id='GM-ABCDEF'`)
  await evaluate(`document.querySelector('.landscape-settlement-topline button').click()`)
  await sleep(40)
  const settlements=[]
  for (const [width,height] of [[667,375],[1298,600]]) {
    await command('Emulation.setDeviceMetricsOverride', { width,height,deviceScaleFactor:1,mobile:false })
    await sleep(60)
    const result=await evaluate(`(() => {
      const capsule=document.querySelector('.settlement-capsule')?.getBoundingClientRect();
      const handTiles=[...document.querySelectorAll('.pve-self-hand button[role="listitem"]')].map(el=>el.getBoundingClientRect());
      const tileFaces=[...document.querySelectorAll('.pve-table .mahjong-tile .tile-face,.pve-self-controls .mahjong-tile .tile-face')];
      const topMeld=document.querySelector('.opponent-seat.top .meld-area')?.getBoundingClientRect();
      const topRiver=document.querySelector('.opponent-seat.top .discard-river')?.getBoundingClientRect();
      const selfMeld=document.querySelector('.pve-self-controls .compact-melds')?.getBoundingClientRect();
      const selfRiver=document.querySelector('.pve-self-controls .discard-river')?.getBoundingClientRect();
      const overflowing=tileFaces.flatMap(face=>[...face.querySelectorAll('.characters,.honor')].filter(text=>{const a=text.getBoundingClientRect(),b=face.getBoundingClientRect();return a.left<b.left-1||a.right>b.right+1||a.top<b.top-1||a.bottom>b.bottom+1}).map(text=>({tile:face.parentElement.dataset.tile,text:text.textContent,textRect:text.getBoundingClientRect().toJSON(),faceRect:face.getBoundingClientRect().toJSON()})));
      const chiGroups=[...document.querySelectorAll('.opponent-seat [data-meld-type="chi"]')];
      const chiGaps=chiGroups.flatMap(group=>{const faces=[...group.querySelectorAll('.mahjong-tile .tile-face')].map(face=>face.getBoundingClientRect());return faces.slice(1).map((face,i)=>face.left-faces[i].right)});
      return {capsule:!!capsule,rect:capsule?.toJSON(),handTop:Math.min(...handTiles.map(r=>r.top)),handVisible:handTiles.every(r=>r.left>=0&&r.right<=innerWidth&&r.top>=0&&r.bottom<=innerHeight),textFit:overflowing.length===0,topMeldClear:topMeld?.bottom<=topRiver?.top+1,selfMeldClear:selfMeld?.right<=selfRiver?.left||selfMeld?.bottom<=selfRiver?.top,evHidden:getComputedStyle(document.querySelector('.pve-ev-slot')).display==='none',overflowing:overflowing.slice(0,8),chiGaps};
    })()`)
    assert.equal(result.capsule,true)
    assert.equal(result.chiGaps.length,6)
    assert.ok(result.chiGaps.every(gap=>gap>=3),`${width}x${height} sideways meld tile overlaps neighbour: ${result.chiGaps}`)
    assert.ok(result.rect.bottom+20<=result.handTop,`${width}x${height} settlement overlaps final hand`)
    if (!(result.rect.left>=0&&result.rect.right<=width&&result.rect.top>=0&&result.handVisible&&result.textFit&&result.topMeldClear&&result.selfMeldClear&&result.evHidden)) console.error(JSON.stringify({viewport:[width,height],result}))
    assert.ok(result.rect.left>=0&&result.rect.right<=width&&result.rect.top>=0&&result.handVisible&&result.textFit&&result.topMeldClear&&result.selfMeldClear&&result.evHidden)
    const shot=await command('Page.captureScreenshot',{format:'png'})
    await writeFile(`tests/artifacts/pve-settlement-${width}x${height}.png`,Buffer.from(shot.data,'base64'))
    settlements.push({viewport:[width,height],handGap:result.handTop-result.rect.bottom,textFit:result.textFit})
  }
  await command('Emulation.setDeviceMetricsOverride',{width:1298,height:600,deviceScaleFactor:1,mobile:false})
  const winnerVisual=await evaluate(`(async () => {
    const source=await (await fetch('/src/components/GameOverModal.vue')).text();
    const vueUrl=source.match(/["']([^"']*vue\\.js[^"']*)["']/)[1];
    const {createApp}=await import(vueUrl);
    const Modal=(await import('/src/components/GameOverModal.vue')).default;
    const melds=[{meld_type:'pong',tiles:['1m','1m','1m']},
      {meld_type:'chi',tiles:['1m','2m','3m']},{meld_type:'chi',tiles:['2m','3m','4m']}];
    const hand=['1p','1p','4p','4p'];
    const response=await fetch('/api/calculate-hu',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({melds,hand_tiles:hand,win_tile:'1p',is_zimo:true,seat_wind:'E',dealer_tile:'5m',is_dealer:true})});
    if(!response.ok) throw new Error(await response.text());
    const scored=await response.json();
    document.querySelector('#app').style.display='none';
    const root=document.createElement('div');document.body.append(root);
    const info={...scored,game_id:'GM-VISUAL',winner_seat:'E',win_type:'zimo',win_tile:'1p',dealer_tile:'5m',
      seat_details:{E:{hand_tiles:hand,melds,winning_hand_groups:scored.winning_hand_groups,net:72},
        S:{hand_tiles:Array(13).fill('2s'),melds:[],net:-24,inherent:{items:['红中雀头 (+2胡)']}},
        W:{hand_tiles:Array(13).fill('3p'),melds:[],net:-24,inherent:{items:['明刻 西风 (+4胡)']}},
        N:{hand_tiles:Array(13).fill('4m'),melds:[],net:-24,inherent:{items:['暗刻 八筒 (+8胡)']}}},
      net_by_seat:{E:72,S:-24,W:-24,N:-24}};
    createApp(Modal,{info,seatWind:'E',dealerSeat:'E'}).mount(root);
    await new Promise(resolve=>setTimeout(resolve,80));
    const panel=document.querySelector('.game-over-panel');
    const winnerTile=document.querySelector('.landscape-winner-group .settlement-mini-tile');
    const loserTile=document.querySelector('.landscape-seat-tiles .settlement-mini-tile');
    const winningTile=document.querySelector('.landscape-winner-group .is-winning-tile');
    const breakdown=document.querySelector('.landscape-winner-breakdown');
    const summary=document.querySelector('.landscape-settlement-summary').getBoundingClientRect();
    return {tileRatio:winnerTile.getBoundingClientRect().width/loserTile.getBoundingClientRect().width,
      huBadge:getComputedStyle(winningTile,'::after').content,breakdown:breakdown.textContent,
      breakdownVisible:breakdown.getBoundingClientRect().bottom<=summary.bottom+1,
      noScroll:panel.scrollHeight<=panel.clientHeight+1};
  })()`)
  assert.ok(winnerVisual.tileRatio>=1.2&&winnerVisual.huBadge.includes('胡'))
  assert.match(winnerVisual.breakdown,/明刻 一万/)
  assert.match(winnerVisual.breakdown,/暗刻 一筒/)
  assert.match(winnerVisual.breakdown,/自摸/)
  assert.ok(winnerVisual.breakdownVisible&&winnerVisual.noScroll)
  const winnerShot=await command('Page.captureScreenshot',{format:'png'})
  await writeFile('tests/artifacts/pve-winner-details-1298x600.png',Buffer.from(winnerShot.data,'base64'))
  await command('Emulation.setDeviceMetricsOverride',{width:667,height:375,deviceScaleFactor:1,mobile:false})
  await sleep(60)
  const winnerPhone=await evaluate(`(() => {
    const panel=document.querySelector('.game-over-panel');
    const summary=document.querySelector('.landscape-settlement-summary').getBoundingClientRect();
    const action=document.querySelector('.landscape-settlement-actions').getBoundingClientRect();
    const breakdown=document.querySelector('.landscape-winner-breakdown').getBoundingClientRect();
    const groups=[...document.querySelectorAll('.landscape-winner-group')].map(el=>el.getBoundingClientRect());
    return {noScroll:panel.scrollHeight<=panel.clientHeight+1,breakdownBottom:breakdown.bottom,actionTop:action.top,
      detailsClear:breakdown.bottom+3<=action.top,
      groupsVisible:groups.every(rect=>rect.left>=summary.left-1&&rect.right<=summary.right+1&&rect.bottom<action.top)};
  })()`)
  assert.ok(winnerPhone.noScroll&&winnerPhone.detailsClear&&winnerPhone.groupsVisible,`667x375 winner details clipped: ${JSON.stringify(winnerPhone)}`)
  console.log(JSON.stringify({ status:'passed', viewports:results.map(({debug,...result})=>result), meldRiverGaps, drawerClear:{downward:drawerClear.downward,elevated:drawerClear.elevated}, chi, otherMelds, fullSettlements, settlements, winnerVisual, winnerPhone }, null, 2))
} finally {
  if (socket?.readyState === WebSocket.OPEN) {
    try { await command('Browser.close') } catch {}
    socket.close()
  }
  chrome.kill()
}
