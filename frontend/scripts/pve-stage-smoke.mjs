import assert from 'node:assert/strict'
import { spawn } from 'node:child_process'
import { mkdir, mkdtemp, writeFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { northDiscardDeal, selfWinDeal } from '../tests/pveFixture.js'

const port = 9336
const profile = await mkdtemp(join(tmpdir(), 'mahjong-stage-'))
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
  throw new Error('Stage browser test timed out')
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
async function capture(label) {
  if (!process.env.PVE_CAPTURE_DIR) return
  await mkdir(process.env.PVE_CAPTURE_DIR, { recursive: true })
  const shot = await command('Page.captureScreenshot', { format: 'png' })
  await writeFile(join(process.env.PVE_CAPTURE_DIR, `${label}.png`), Buffer.from(shot.data, 'base64'))
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
  await command('Emulation.setDeviceMetricsOverride', { width: 390, height: 844, deviceScaleFactor: 1, mobile: true })
  await command('Emulation.setTouchEmulationEnabled', { enabled: true, maxTouchPoints: 1 })
  await command('Page.addScriptToEvaluateOnNewDocument', { source: `
    const realFetch=window.fetch.bind(window);
    window.fetch=(url,init)=>{
      if(String(url).endsWith('/game/auto-deal')) return Promise.resolve(new Response(JSON.stringify(
        location.search.includes('self_win_smoke=1')
          ? ${JSON.stringify(selfWinDeal())} : ${JSON.stringify(northDiscardDeal())}
      ),{headers:{'Content-Type':'application/json'}}));
      if(location.search.includes('self_win_smoke=1')&&String(url).endsWith('/api/game/record')) {
        window.__archivePosted=true;
        return Promise.resolve(new Response(JSON.stringify({game_id:'GM-TEST01',steps_count:1}),{headers:{'Content-Type':'application/json'}}));
      }
      return realFetch(url,init);
    };
  ` })
  await command('Page.navigate', { url: process.env.PVE_URL || 'http://127.0.0.1:5173/' })
  await until(() => evaluate(`!![...document.querySelectorAll('button')].find(button=>button.textContent.includes('人机对战'))`))
  await evaluate(`window.__rootStage=document.querySelector('.game-stage')`)
  for (const [width, height] of [[390, 844], [844, 390], [1280, 720]]) {
    await command('Emulation.setDeviceMetricsOverride', { width, height, deviceScaleFactor: 1, mobile: width < 1000 })
    await sleep(100)
    const home = await evaluate(`(() => {
      const stage=document.querySelector('.game-stage'),r=stage.getBoundingClientRect();
      const button=[...document.querySelectorAll('.home-screen button')].find(item=>item.textContent.includes('人机对战'));
      const b=button.getBoundingClientRect();
      return {stable:stage===window.__rootStage,logical:[stage.offsetWidth,stage.offsetHeight],fits:r.left>=-1&&r.top>=-1&&r.right<=innerWidth+1&&r.bottom<=innerHeight+1,
        home:stage.classList.contains('is-home-stage'),buttonHit:document.elementFromPoint(b.left+b.width/2,b.top+b.height/2)?.closest('button')===button,
        noScroll:document.documentElement.scrollWidth<=innerWidth+1&&document.documentElement.scrollHeight<=innerHeight+1};
    })()`)
    assert.ok(home.stable&&home.logical[0]===1280&&home.logical[1]===720&&home.fits&&home.home&&home.buttonHit&&home.noScroll, `${width}x${height}: homepage stage broken ${JSON.stringify(home)}`)
  }
  await command('Emulation.setDeviceMetricsOverride', { width: 390, height: 844, deviceScaleFactor: 1, mobile: true })
  await capture('home-portrait')
  await evaluate(`[...document.querySelectorAll('button')].find(button=>button.textContent.includes('全景上帝视角沙盘')).click()`)
  await until(() => evaluate(`!!document.querySelector('.god-view-return')`))
  assert.ok(await evaluate(`(() => {
    const button=document.querySelector('.god-view-return'), rect=button.getBoundingClientRect();
    return button.textContent.includes('返回模式选择')&&rect.top>=0&&rect.left>=0&&rect.bottom<=innerHeight&&rect.right<=innerWidth&&
      document.elementFromPoint(rect.left+rect.width/2,rect.top+rect.height/2)?.closest('button')===button;
  })()`), 'sandbox return button is missing or covered')
  await evaluate(`document.querySelector('.god-view-return').click()`)
  await until(() => evaluate(`!![...document.querySelectorAll('button')].find(button=>button.textContent.includes('人机对战'))&&!document.querySelector('.god-view-return')`))
  await evaluate(`[...document.querySelectorAll('button')].find(button=>button.textContent.includes('人机对战')).click()`)
  await until(() => evaluate(`!![...document.querySelectorAll('button')].find(button=>button.textContent.includes('开始对战'))`))
  await evaluate(`document.querySelector('[aria-label="人机对战设置"] input[type="checkbox"]').click()`)
  const startButton = await evaluate(`(() => { const r=[...document.querySelectorAll('button')].find(button=>button.textContent.includes('开始对战')).getBoundingClientRect(); return {x:r.left+r.width/2,y:r.top+r.height/2} })()`)
  await command('Input.dispatchMouseEvent', { type:'mousePressed', x:startButton.x, y:startButton.y, button:'left', clickCount:1 })
  await command('Input.dispatchMouseEvent', { type:'mouseReleased', x:startButton.x, y:startButton.y, button:'left', clickCount:1 })
  await until(() => evaluate(`!!document.querySelector('.pve-self-hand')`))
  assert.ok(await evaluate(`document.querySelector('.game-stage')===window.__rootStage`), 'entering PvE remounted the global stage')
  await until(() => evaluate(`!!document.fullscreenElement`))
  assert.ok(await evaluate(`document.documentElement.classList.contains('game-fullscreen-scroll-lock')&&document.body.classList.contains('game-fullscreen-scroll-lock')`), 'fullscreen scroll lock was not applied')
  await evaluate(`document.exitFullscreen()`)
  await until(() => evaluate(`!document.fullscreenElement&&!document.body.classList.contains('game-fullscreen-scroll-lock')`))
  await command('Emulation.setTouchEmulationEnabled', { enabled: false })
  await evaluate(`document.querySelector('#app').__vue_app__._instance.setupState.enableEV=true`)
  await until(() => evaluate(`!!document.querySelector('.pve-discard-hud .hud-tile')`))

  const viewports = [[390, 844, true], [393, 852, true], [844, 390, true], [1280, 720, false], [1920, 1080, false]]
  const results = []
  let logicalStage = null
  for (const [width, height, mobile] of viewports) {
    await command('Emulation.setDeviceMetricsOverride', { width, height, deviceScaleFactor: 1, mobile })
    await sleep(700)
    const result = await evaluate(`(() => {
      const rect=(el)=>el.getBoundingClientRect();
      const inside=(a,b)=>a.left>=b.left-3&&a.top>=b.top-3&&a.right<=b.right+3&&a.bottom<=b.bottom+3;
      const viewport={left:0,top:0,right:innerWidth,bottom:innerHeight};
      const stage=rect(document.querySelector('.game-stage'));
      const board=rect(document.querySelector('.pve-table'));
      const hand=rect(document.querySelector('.pve-self-hand'));
      const status=rect(document.querySelector('.pve-game-main > [aria-label="轮次状态"]'));
      const anchor=rect(document.querySelector('.pve-hand-anchor'));
      const hud=rect(document.querySelector('.pve-discard-hud'));
      const situation=rect(document.querySelector('.pve-situation-hud'));
      const tiles=[...document.querySelectorAll('.pve-self-hand button[role="listitem"]')];
      const hudTiles=[...document.querySelectorAll('.pve-discard-hud .hud-tile')];
      const fullscreenButton=[...document.querySelectorAll('button')].find(button=>button.textContent.trim()==='⛶ 全屏');
      const rivers=[...document.querySelectorAll('.discard-river')].map(rect);
      const melds=[...document.querySelectorAll('.meld-area')].map(rect);
      const transform=getComputedStyle(document.querySelector('.game-stage')).transform;
      const hit=(element)=>{const r=rect(element);return document.elementFromPoint((r.left+r.right)/2,(r.top+r.bottom)/2)?.closest('button')===element};
      const overlap=(a,b)=>a.left<b.right&&a.right>b.left&&a.top<b.bottom&&a.bottom>b.top;
      const logicalSelectors=['.game-stage','.pve-game-main','.pve-table','.pve-table .opponent-seat','.pve-table .tile-back','.pve-self-hand','.pve-self-hand button[role="listitem"]','.pve-discard-hud','.pve-situation-hud'];
      const logical=logicalSelectors.map(selector=>{const element=document.querySelector(selector);return [element?.offsetWidth,element?.offsetHeight]});
      const center=rect(document.querySelector('.table-center'));
      const topRiver=rect(document.querySelector('.opponent-seat.top .discard-river'));
      const leftRiver=rect(document.querySelector('.opponent-seat.left .discard-river'));
      const rightRiver=rect(document.querySelector('.opponent-seat.right .discard-river'));
      const selfRiver=rect(document.querySelector('.self-river .discard-river'));
      const noSeatFrames=[...document.querySelectorAll('.opponent-seat')].every(seat=>getComputedStyle(seat).borderTopWidth==='0px'&&getComputedStyle(seat).backgroundColor==='rgba(0, 0, 0, 0)');
      return {viewport:[innerWidth,innerHeight],stage:stage.toJSON(),hand:hand.toJSON(),hud:hud.toJSON(),logical,noPageScroll:document.documentElement.scrollWidth<=innerWidth+1&&document.documentElement.scrollHeight<=innerHeight+1,
        transform,tiles:tiles.length,rivers:rivers.length,melds:melds.length,stageFits:inside(stage,viewport),boardFits:inside(board,stage),handFits:inside(hand,stage),hudFits:inside(hud,viewport),situationFits:inside(situation,stage)&&!overlap(situation,hand)&&!overlap(situation,hud),anchorCentered:innerHeight>innerWidth?Math.abs((anchor.top+anchor.bottom)/2-(stage.top+stage.bottom)/2)<2:Math.abs((anchor.left+anchor.right)/2-(stage.left+stage.right)/2)<2,
        compassRing:noSeatFrames&&(innerHeight>innerWidth
          ? topRiver.right<=center.left&&selfRiver.left>=center.right&&leftRiver.top>=center.bottom&&rightRiver.bottom<=center.top
          : topRiver.bottom<=center.top&&selfRiver.top>=center.bottom&&leftRiver.right<=center.left&&rightRiver.left>=center.right),
        anchorsCorrect:innerHeight>innerWidth?hand.left>stage.left+stage.width/2&&status.right<stage.left+stage.width/2:hand.top>stage.top+stage.height/2&&status.bottom<stage.top+stage.height/2,
        riversFit:rivers.every(river=>inside(river,viewport)),meldsFit:melds.every(meld=>inside(meld,viewport)),hintRemoved:!document.body.innerText.includes('建议横屏使用'),
        tilesFit:tiles.every(tile=>inside(rect(tile),hand)&&inside(rect(tile),viewport)),hudTiles:hudTiles.length,
        clickTargets:tiles.every(hit)&&hudTiles.every(hit)&&fullscreenButton&&!fullscreenButton.disabled&&inside(rect(fullscreenButton),viewport)&&hit(fullscreenButton)};
    })()`)
    assert.ok(result.transform.startsWith('matrix('), `${width}x${height}: missing stage transform`)
    assert.ok(result.stageFits && result.boardFits && result.handFits && result.hudFits && result.situationFits && result.compassRing && result.anchorCentered && result.anchorsCorrect && result.tilesFit && result.riversFit && result.meldsFit && result.hintRemoved && result.clickTargets && result.noPageScroll,
      `${width}x${height}: stage or hand clipped / click target drifted: ${JSON.stringify(result)}`)
    if (logicalStage) assert.deepEqual(result.logical, logicalStage, `${width}x${height}: inner stage layout changed with physical viewport`)
    else logicalStage = result.logical
    assert.equal(result.tiles, 14)
    if (!mobile) {
      const anchor = await evaluate(`(async () => {
        const state=document.querySelector('#app').__vue_app__._instance.setupState;
        const original=[...state.roundState.handTiles], drawn=state.latestDrawnTile;
        const slot=document.querySelector('.pve-hand-anchor');
        const start=slot.getBoundingClientRect().left;
        const offsets=[];
        for(let i=0;i<3;i++) {
          state.roundState.handTiles=original.slice(0,-1);state.latestDrawnTile=null;
          await new Promise(resolve=>setTimeout(resolve,60)); offsets.push(slot.getBoundingClientRect().left-start);
          state.roundState.handTiles=[...original];state.latestDrawnTile=original.at(-1);
          await new Promise(resolve=>setTimeout(resolve,60)); offsets.push(slot.getBoundingClientRect().left-start);
        }
        state.latestDrawnTile=drawn;
        return {offsets,width:slot.getBoundingClientRect().width};
      })()`)
      assert.ok(anchor.offsets.every(delta=>Math.abs(delta)<1), `${width}x${height}: hand jumped ${JSON.stringify(anchor)}`)
    }
    results.push({ viewport: result.viewport, stage: result.stage, hand: result.hand, tiles: result.tiles })
  }
  await command('Emulation.setDeviceMetricsOverride', { width: 1280, height: 720, deviceScaleFactor: 1, mobile: false })
  await sleep(100)
  await capture('pve-desktop')
  await evaluate(`(() => {
    const state=document.querySelector('#app').__vue_app__._instance.setupState;
    window.__pveMeldSnapshot={hand:[...state.roundState.handTiles],melds:[...state.roundState.melds],drawn:state.latestDrawnTile,ev:state.enableEV};
    state.enableEV=false;
    window.__pveHandAnchorLeft=document.querySelector('.pve-hand-anchor').getBoundingClientRect().left;
  })()`)
  for (const count of [1, 4]) {
    await evaluate(`(() => {
      const state=document.querySelector('#app').__vue_app__._instance.setupState;
      state.roundState.melds=Array.from({length:${count}},(_,index)=>({meld_type:'pong',tiles:[['1p','2p','3p','4p'][index]].flatMap(tile=>[tile,tile,tile]),provider_seat:'S'}));
      state.roundState.handTiles=window.__pveMeldSnapshot.hand.slice(0,14-3*${count});
      state.latestDrawnTile=null;
    })()`)
    await until(() => evaluate(`document.querySelectorAll('.compact-melds [role="listitem"]').length===${count}`))
    const layout = await evaluate(`(() => {
      const meld=document.querySelector('.pve-self-controls > .compact-melds'),anchor=document.querySelector('.pve-hand-anchor');
      const meldTiles=[...meld.querySelectorAll('.mahjong-tile')];
      const handTiles=[...document.querySelectorAll('.pve-self-hand button[role="listitem"]')];
      const header=document.querySelector('.pve-self-hand > div:first-child');
      const a=anchor.getBoundingClientRect(),m=meld.getBoundingClientRect(),h=header.getBoundingClientRect(),hand=document.querySelector('.pve-self-hand').getBoundingClientRect();
      const overlap=(x,y)=>x.left<y.right&&x.right>y.left&&x.top<y.bottom&&x.bottom>y.top;
      return {anchored:Math.abs(a.left-window.__pveHandAnchorLeft)<1,aboveHand:m.bottom<=hand.top+2,independent:!overlap(m,hand),tileWidth:meldTiles[0]?.getBoundingClientRect().width,overflow:meld.scrollWidth>meld.clientWidth+1,headerOverlapsHand:handTiles.some(tile=>overlap(h,tile.getBoundingClientRect())),tileCount:meldTiles.length,caption:document.querySelector('.pve-hand-caption')?.textContent.trim()};
    })()`)
    assert.ok(layout.anchored&&layout.aboveHand&&layout.independent&&layout.tileWidth>=34&&!layout.overflow&&!layout.headerOverlapsHand&&layout.tileCount===count*3&&layout.caption, `${count} melds: clipped or overlapping hand layout ${JSON.stringify(layout)}`)
  }
  await evaluate(`(() => {
    const state=document.querySelector('#app').__vue_app__._instance.setupState,snapshot=window.__pveMeldSnapshot;
    state.roundState.handTiles=snapshot.hand;state.roundState.melds=snapshot.melds;state.latestDrawnTile=snapshot.drawn;state.enableEV=snapshot.ev;
  })()`)
  await until(() => evaluate(`!!document.querySelector('.pve-discard-hud .hud-tile')`))
  const fullscreenButton = await evaluate(`(() => {
    const button=[...document.querySelectorAll('button')].find(item=>item.textContent.trim()==='⛶ 全屏');
    if (!button || button.disabled) return null;
    const rect=button.getBoundingClientRect();
    const x=rect.left+rect.width/2,y=rect.top+rect.height/2;
    return {x,y,visible:rect.left>=0&&rect.right<=innerWidth&&rect.top>=0&&rect.bottom<=innerHeight&&document.elementFromPoint(x,y)?.closest('button')===button};
  })()`)
  assert.ok(fullscreenButton?.visible, `fullscreen button is clipped or covered: ${JSON.stringify(fullscreenButton)}`)
  await command('Input.dispatchMouseEvent', { type:'mousePressed', x:fullscreenButton.x, y:fullscreenButton.y, button:'left', clickCount:1 })
  await command('Input.dispatchMouseEvent', { type:'mouseReleased', x:fullscreenButton.x, y:fullscreenButton.y, button:'left', clickCount:1 })
  await until(() => evaluate(`!!document.fullscreenElement&&[...document.querySelectorAll('button')].some(button=>button.textContent.trim()==='退出全屏')`))
  await evaluate(`[...document.querySelectorAll('button')].find(button=>button.textContent.trim()==='退出全屏').click()`)
  await until(() => evaluate(`!document.fullscreenElement&&[...document.querySelectorAll('button')].some(button=>button.textContent.trim()==='⛶ 全屏')`))
  await evaluate(`(() => {
    window.__pveStable={stage:document.querySelector('.game-stage'),board:document.querySelector('.pve-table'),transformChanges:0};
    new MutationObserver(()=>window.__pveStable.transformChanges++).observe(window.__pveStable.stage,{attributes:true,attributeFilter:['style']});
  })()`)
  let verifiedDiscards = 0
  for (let attempt = 0; attempt < 2; attempt++) {
    const ready = await until(() => evaluate(`(() => {
      const state=document.querySelector('#app').__vue_app__._instance.setupState;
      return state.roundState.handTiles.length===14 && !!document.querySelector('.pve-self-hand button[role="listitem"]:not([disabled])');
    })()`), 30000)
    assert.ok(ready)
    const before = await evaluate(`document.querySelector('#app').__vue_app__._instance.setupState.roundState.discards.length`)
    await evaluate(`document.querySelector('.pve-self-hand button[role="listitem"]:not([disabled])').click()`)
    await until(() => evaluate(`document.querySelector('#app').__vue_app__._instance.setupState.roundState.discards.length>${before}`), 30000)
    assert.ok(await evaluate(`window.__pveStable.stage===document.querySelector('.game-stage')&&window.__pveStable.board===document.querySelector('.pve-table')`), 'discard remounted the stage or board')
    assert.equal(await evaluate(`window.__pveStable.transformChanges`), 0, 'discard recomputed the stage transform')
    verifiedDiscards++
  }

  for (const [width, height, mobile] of viewports) {
    await command('Emulation.setDeviceMetricsOverride', { width, height, deviceScaleFactor: 1, mobile })
    await sleep(100)
    await evaluate(`(() => {
      const state=document.querySelector('#app').__vue_app__._instance.setupState;
      const action={action_type:'pong',tiles:['3m','3m','3m'],provider_seat:'S'};
      state.loading=false;
      state.aiActionBusy=false;
      state.currentPhase='OPPONENT_DISCARD_ACTION';
      state.lastStepResult={need_self_action:true,_response_tile:'3m',call_decision:{available_actions:[action,{action_type:'pass',tiles:['3m'],provider_seat:'S'}],recommended_action:action,candidates:[]}};
    })()`)
    await until(() => evaluate(`!!document.querySelector('.action-prompt-docked')`))
    const panel = await evaluate(`(() => {
      const slot=document.querySelector('.pve-ev-slot'),wrap=document.querySelector('.action-prompt-wrap'),panel=document.querySelector('.action-prompt-panel');
      const buttons=[...document.querySelectorAll('.action-prompt-panel [aria-label="可选响应动作"] button')];
      const viewport={left:0,top:0,right:innerWidth,bottom:innerHeight};
      const hand=document.querySelector('.pve-self-hand').getBoundingClientRect();
      const rect=panel.getBoundingClientRect();
      const contained=(r)=>r.left>=viewport.left-1&&r.top>=viewport.top-1&&r.right<=viewport.right+1&&r.bottom<=viewport.bottom+1;
      const hit=(button)=>{const r=button.getBoundingClientRect();return document.elementFromPoint((r.left+r.right)/2,(r.top+r.bottom)/2)?.closest('button')===button};
      const overlap=(a,b)=>a.left<b.right&&a.right>b.left&&a.top<b.bottom&&a.bottom>b.top;
      return {buttons:buttons.map(button=>({name:button.querySelector('.action-label')?.textContent.trim(),height:button.offsetHeight,visible:contained(button.getBoundingClientRect()),hit:hit(button)})),panelFits:contained(rect),panelClearOfHand:!overlap(rect,hand),scroll:[slot,wrap,panel,panel.lastElementChild].some(el=>el.scrollHeight>el.clientHeight+1),rect:rect.toJSON(),hand:hand.toJSON()};
    })()`)
    assert.ok(panel.panelFits && panel.panelClearOfHand && !panel.scroll && panel.buttons.length===2 && panel.buttons.every(button=>button.visible&&button.hit&&button.name&&button.height>=38&&button.height<=42), `${width}x${height}: clipped action bar ${JSON.stringify(panel)}`)
  }
  await evaluate(`(() => {const state=document.querySelector('#app').__vue_app__._instance.setupState;state.currentPhase='MY_TURN_DISCARD';state.lastStepResult=null})()`)
  assert.ok(await evaluate(`document.querySelector('.pve-situation-hud').textContent.includes('牌局平稳进行中')`))
  await evaluate(`(() => {
    const state=document.querySelector('#app').__vue_app__._instance.setupState;
    state.wallTiles=state.wallTiles.slice(0,55);
    state.roundState.discards=['1m','2m','3m','7m','8m'];
    state.roundState.opponents.forEach(opponent=>{opponent.discards=['1p','2p','3p','7p','8p'];opponent.melds=[]});
    state.roundState.opponents[0].melds=[{meld_type:'pong',tiles:['E','E','E']}];
  })()`)
  await until(() => evaluate(`document.querySelector('.pve-situation-hud')?.textContent.includes('已完成一组副露')`))
  await evaluate(`(() => {
    const state=document.querySelector('#app').__vue_app__._instance.setupState;
    state.wallTiles=state.wallTiles.slice(0,50);
    state.roundState.opponents[0].melds.push({meld_type:'pong',tiles:['C','C','C']});
  })()`)
  await until(() => evaluate(`document.querySelector('.pve-situation-hud')?.textContent.includes('听牌概率极高')`))
  for (const [width, height, mobile] of viewports) {
    await command('Emulation.setDeviceMetricsOverride', { width, height, deviceScaleFactor: 1, mobile })
    await sleep(250)
    assert.ok(await evaluate(`(() => {
      const rect=(selector)=>document.querySelector(selector).getBoundingClientRect();
      const warning=rect('.pve-situation-hud'),hand=rect('.pve-self-hand'),ev=rect('.pve-ev-slot');
      const overlaps=(a,b)=>a.left<b.right&&a.right>b.left&&a.top<b.bottom&&a.bottom>b.top;
      return warning.left>=-1&&warning.right<=innerWidth+1&&warning.top>=-1&&warning.bottom<=innerHeight+1&&
        !overlaps(warning,hand)&&!overlaps(warning,ev);
    })()`), `${width}x${height}: high-risk warning overlaps hand or EV panel`)
  }
  await evaluate(`(() => {
    const state=document.querySelector('#app').__vue_app__._instance.setupState;
    const action={action_type:'pong',tiles:['3m','3m','3m'],provider_seat:'S'};
    state.loading=false;state.aiActionBusy=false;state.currentPhase='OPPONENT_DISCARD_ACTION';
    state.lastStepResult={need_self_action:true,_response_tile:'3m',call_decision:{available_actions:[action,{action_type:'pass',tiles:['3m'],provider_seat:'S'}],recommended_action:action,candidates:[]}};
  })()`)
  await until(() => evaluate(`!!document.querySelector('.action-prompt-panel button[data-action="pass"]')`))
  assert.ok(await evaluate(`(() => {const button=document.querySelector('.action-prompt-panel button[data-action="pass"]');button.click();return document.querySelector('#app').__vue_app__._instance.setupState.currentPhase==='WAIT_RESPONSE'})()`), 'pass button did not advance the response phase')
  const entryLayouts = []
  for (const [width, height] of [[393, 852], [852, 393]]) {
    await command('Emulation.setDeviceMetricsOverride', { width, height, deviceScaleFactor: 1, mobile: true })
    await command('Page.navigate', { url: process.env.PVE_URL || 'http://127.0.0.1:5173/' })
    await until(() => evaluate(`!![...document.querySelectorAll('button')].find(button=>button.textContent.includes('人机对战'))`))
    await evaluate(`[...document.querySelectorAll('button')].find(button=>button.textContent.includes('人机对战')).click()`)
    await until(() => evaluate(`!![...document.querySelectorAll('button')].find(button=>button.textContent.includes('开始对战'))`))
    await evaluate(`[...document.querySelectorAll('button')].find(button=>button.textContent.includes('开始对战')).click()`)
    await until(() => evaluate(`!!document.querySelector('.pve-self-hand')`))
    const entry = await evaluate(`(() => {
      const stage=document.querySelector('.game-stage'),main=document.querySelector('.pve-game-main'),hand=document.querySelector('.pve-self-hand'),anchor=document.querySelector('.pve-hand-anchor');
      const s=stage.getBoundingClientRect(),h=hand.getBoundingClientRect();
      return {logical:[stage.offsetWidth,stage.offsetHeight,main.offsetWidth,main.offsetHeight,hand.offsetWidth,hand.offsetHeight,anchor.offsetLeft,anchor.offsetTop],fits:s.left>=-1&&s.top>=-1&&s.right<=innerWidth+1&&s.bottom<=innerHeight+1,handSide:innerHeight>innerWidth?h.left>s.left+s.width/2:h.top>s.top+s.height/2,noScroll:document.documentElement.scrollWidth<=innerWidth+1&&document.documentElement.scrollHeight<=innerHeight+1};
    })()`)
    assert.ok(entry.fits&&entry.handSide&&entry.noScroll, `${width}x${height}: direct mobile entry broken ${JSON.stringify(entry)}`)
    entryLayouts.push(entry.logical)
  }
  assert.deepEqual(entryLayouts[0],entryLayouts[1], 'portrait and landscape entry use different stage layouts')
  await command('Emulation.setDeviceMetricsOverride', { width: 390, height: 844, deviceScaleFactor: 1, mobile: true })
  await command('Page.navigate', { url: `${process.env.PVE_URL || 'http://127.0.0.1:5173/'}?self_win_smoke=1` })
  await until(() => evaluate(`!![...document.querySelectorAll('button')].find(button=>button.textContent.includes('人机对战'))`))
  await evaluate(`[...document.querySelectorAll('button')].find(button=>button.textContent.includes('人机对战')).click()`)
  await until(() => evaluate(`!![...document.querySelectorAll('button')].find(button=>button.textContent.includes('开始对战'))`))
  await evaluate(`[...document.querySelectorAll('button')].find(button=>button.textContent.includes('开始对战')).click()`)
  await until(() => evaluate(`!!document.querySelector('.pve-self-win-prompt')`), 30000)
  for (const [width, height] of [[390, 844], [844, 390], [1280, 720]]) {
    await command('Emulation.setDeviceMetricsOverride', { width, height, deviceScaleFactor: 1, mobile: width < 1000 })
    await sleep(150)
    const modal = await evaluate(`(() => {
      const stage=document.querySelector('.game-stage').getBoundingClientRect();
      const panel=document.querySelector('.pve-self-win-prompt');
      const rect=panel.getBoundingClientRect();
      const button=[...panel.querySelectorAll('button')].find(item=>item.textContent.includes('确认和牌并结算'));
      const action=button?.getBoundingClientRect();
      const inside=(r)=>r.left>=-1&&r.top>=-1&&r.right<=innerWidth+1&&r.bottom<=innerHeight+1;
      return {panelFits:inside(rect),buttonFits:!!action&&inside(action),buttonHit:!!action&&document.elementFromPoint(action.left+action.width/2,action.top+action.height/2)?.closest('button')===button,
        centered:Math.abs((rect.left+rect.right-stage.left-stage.right)/2)<2&&Math.abs((rect.top+rect.bottom-stage.top-stage.bottom)/2)<2,
        detachedFromEvSlot:!panel.closest('.pve-ev-slot'),buttonSize:button?.offsetHeight,
        title:panel.querySelector('h2')?.textContent.trim()};
    })()`)
    assert.ok(modal.panelFits&&modal.buttonFits&&modal.buttonHit&&modal.centered&&modal.detachedFromEvSlot&&modal.buttonSize>=44&&modal.title.includes('自摸和牌'), `${width}x${height}: self-win modal clipped ${JSON.stringify(modal)}`)
  }
  const settleButton = await evaluate(`(() => {const r=[...document.querySelectorAll('.pve-self-win-prompt button')].find(button=>button.textContent.includes('确认和牌并结算')).getBoundingClientRect();return {x:r.left+r.width/2,y:r.top+r.height/2}})()`)
  await command('Input.dispatchMouseEvent', { type:'mousePressed', x:settleButton.x, y:settleButton.y, button:'left', clickCount:1 })
  await command('Input.dispatchMouseEvent', { type:'mouseReleased', x:settleButton.x, y:settleButton.y, button:'left', clickCount:1 })
  await until(() => evaluate(`!!document.querySelector('[aria-label="对局结束结算"]')`), 30000)
  assert.ok(await evaluate(`(() => {const state=document.querySelector('#app').__vue_app__._instance.setupState;return window.__archivePosted&&state.selfWinSettlement?.game_id==='GM-TEST01'&&state.roundHistory.length===1&&state.gameState==='GAME_OVER'&&state.cumulativeScores.E>0})()`), 'self-win did not settle, score, and archive')
  for (const [width, height] of [[390, 844], [844, 390], [1280, 720]]) {
    await command('Emulation.setDeviceMetricsOverride', { width, height, deviceScaleFactor: 1, mobile: width < 1000 })
    await sleep(100)
    const settlement = await evaluate(`(() => {
      const panel=document.querySelector('.game-over-panel'),r=panel.getBoundingClientRect();
      const next=document.querySelector('.landscape-settlement-next'),history=document.querySelector('.landscape-settlement-history-button');
      const summary=document.querySelector('.landscape-settlement-summary').getBoundingClientRect();
      const details=document.querySelector('.landscape-settlement-details').getBoundingClientRect();
      const inside=rect=>rect.left>=-1&&rect.top>=-1&&rect.right<=innerWidth+1&&rect.bottom<=innerHeight+1;
      return {logical:[panel.offsetWidth,panel.offsetHeight],fits:inside(r)&&inside(next.getBoundingClientRect())&&inside(history.getBoundingClientRect()),
        nextHeight:next.offsetHeight,historyHeight:history.offsetHeight,cards:document.querySelectorAll('.landscape-settlement-seat').length,
        columns:innerHeight>innerWidth?summary.top>=details.bottom:summary.right<=details.left,visible:getComputedStyle(document.querySelector('.landscape-settlement')).display==='flex'};
    })()`)
    assert.ok(settlement.logical[0]===1080&&settlement.logical[1]===560&&settlement.fits&&settlement.nextHeight>=48&&settlement.historyHeight>=48&&settlement.cards===3&&settlement.columns&&settlement.visible, `${width}x${height}: settlement clipped ${JSON.stringify(settlement)}`)
    if (width === 390) await capture('settlement-portrait')
  }
  await evaluate(`document.querySelector('.landscape-settlement-next').click()`)
  await until(() => evaluate(`document.querySelector('#app').__vue_app__._instance.setupState.gameState==='PLAYING'`), 30000)
  console.log(JSON.stringify({ status: 'passed', verifiedDiscards, selfWinVerified: true, viewports: results, directEntryLayouts: entryLayouts }, null, 2))
} finally {
  if (socket?.readyState === WebSocket.OPEN) {
    try { await command('Browser.close') } catch {}
    socket.close()
  }
  chrome.kill()
}
