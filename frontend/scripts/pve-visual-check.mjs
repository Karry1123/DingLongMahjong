import assert from 'node:assert/strict'
import { writeFile } from 'node:fs/promises'

/** Browser fixture uses the production components with explicit public meld metadata. */
export async function checkPveVisuals({ command, evaluate, until, sleep }) {
  await command('Page.navigate', { url: process.env.PVE_URL || 'http://127.0.0.1:5178/' })
  await until(() => evaluate(`!!document.querySelector('#app')?.__vue_app__`))
  await command('Emulation.setDeviceMetricsOverride', { width: 1440, height: 1100, deviceScaleFactor: 1, mobile: false })
  await evaluate(`(async () => {
    const source = await (await fetch('/src/components/PvEBoard.vue')).text();
    const vueUrl = source.match(/["']([^"']*vue\\.js[^"']*)["']/)[1];
    const {createApp,h,ref,nextTick} = await import(vueUrl);
    const Board = (await import('/src/components/PvEBoard.vue')).default;
    const Workbench = (await import('/src/components/PlayerWorkbench.vue')).default;
    const Hand = (await import('/src/components/HandBar.vue')).default;
    const MeldBar = (await import('/src/components/MeldBar.vue')).default;
    const River = (await import('/src/components/DiscardRiver.vue')).default;
    const Result = (await import('/src/components/ResultCard.vue')).default;
    const Prompt = (await import('/src/components/ActionPrompt.vue')).default;
    const Modal = (await import('/src/components/GameOverModal.vue')).default;
    const meld = {meld_type:'chi',tiles:['4s','5s','6s'],claimed_tile:'5s',provider_seat:'E'};
    const response = await fetch('${process.env.API_URL || 'http://127.0.0.1:8123'}/api/calculate-hu', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({melds:[meld],hand_tiles:['4m','6m','1p','2p','3p','7p','8p','9p','E','E'],win_tile:'5m',dealer_tile:'8s',seat_wind:'E',is_zimo:false,is_dealer:true})});
    if(!response.ok) throw new Error(await response.text());
    const scored = await response.json();
    window.__sideDiscards=ref(['E','9m','N','4p','3s','P','F','2m']);
    window.__sideMelds=ref([meld]);
    window.__visualNextTick=nextTick;
    const selfRiver=['E','9m','N','4p','3s','P','F','2m','1p','2p'];
    const recommendation=['1m','4p','6s','N'].map((tile,i)=>({tile,ev_score:35-i*4,attack_ev:50-i*3,defense_loss:2+i,effective_count:12-i*2,est_final_points:42-i*4,is_safe_all:i===3,deal_in_risks:{S:.02+i*.01}}));
    document.querySelector('#app').style.display='none';
    document.body.style.background='#022c22';
    const root=document.createElement('div');root.style.cssText='max-width:1296px;margin:24px auto;padding:16px';document.body.append(root);
    window.__visualApp=createApp({render:()=>h('div',{class:'space-y-4'},[
      h(Board,{seatWind:'E',dealerSeat:'E',currentTurnSeat:'S',dealerTile:'8s',opponents:
        ['N','W','S'].map(seat=>({seat_wind:seat,hand_tiles:Array(10).fill('1m'),melds:seat==='W'?[meld]:window.__sideMelds.value,discards:seat==='W'?['E','9m','N','4p','3s','P','F','2m']:window.__sideDiscards.value}))}),
      h(Workbench,{pve:true},{default:()=>[h('header',{'aria-label':'自家信息',class:'text-amber-100'},'自家 · 东风 庄家 · 累计 0 分'),h('div',{'aria-label':'自家牌河',class:'rounded-xl border border-teal-700/40 p-2.5'},[h('p',{class:'mb-1 text-xs text-teal-200'},'自家牌河'),h(River,{tiles:selfRiver,compact:true})]),h(MeldBar,{modelValue:[meld],readOnly:true,compact:true,dealerTile:'8s'}),h(Hand,{modelValue:['1m','2m','3m','4p','5p','6p','4s','6s','E','E','N','N','P','8s'],wallDriven:true,discardMode:true,dealerTile:'8s'}),h(Prompt,{inline:true,seatWind:'E',providerSeat:'S',discardedTile:'C',dealerTile:'8s',callDecision:{reason:'碰牌锁定红中明刻(+4底胡，+1番翻倍)',recommended_action:{action_type:'pong',tiles:['C','C','C'],provider_seat:'S'},candidates:[{action:{action_type:'pong',tiles:['C','C','C'],provider_seat:'S'},net_ev:36},{action:{action_type:'pass',tiles:[],provider_seat:'S'},net_ev:8}]}})],recommendation:()=>h(Result,{bestTile:'1m',candidates:recommendation,compact:true,interactive:true,seatWind:'E'})})
    ])});window.__visualApp.mount(root);
    window.__showSettlement=()=>{window.__visualApp.unmount();window.__visualApp=createApp(Modal,{info:{...scored,winner_seat:'E',win_type:'ron',win_tile:'5m',dealer_tile:'8s'}});window.__visualApp.mount(root)};
  })()`)
  await sleep(150)
  const table = await evaluate(`(() => {
    const box=s=>document.querySelector(s).getBoundingClientRect().toJSON();
    const river=document.querySelector('[data-seat="S"] [aria-label="弃牌"]');
    const tiles=[...river.children].map(n=>n.getBoundingClientRect());
    const sideways=document.querySelector('[data-seat="S"] [data-sideways="true"]');
    return {top:box('[data-position="top"]'),left:box('[data-position="left"]'),right:box('[data-position="right"]'),center:box('[aria-label="本局财神"]'),self:box('[aria-label="自家操作工作台"]'),hand:box('[aria-label="手牌槽位"]'),prompt:box('.action-prompt-wrap'),promptPosition:getComputedStyle(document.querySelector('.action-prompt-wrap')).position,topWidth:box('[data-position="top"]').width,numberTile:document.querySelector('[data-tile="4p"] .characters')?.innerText,stripTile:document.querySelector('[data-tile="3s"] .characters')?.innerText,duplicate:!!document.querySelector('[data-seat="E"]'),sideColumns:getComputedStyle(river).gridTemplateColumns.split(' ').length,sideRows:new Set(tiles.map(t=>t.y)).size,tileWidth:tiles[0].width,rotation:getComputedStyle(sideways.querySelector('.tile-face')).transform,sideways:sideways.dataset.tile};
  })()`)
  assert.ok(table.top.bottom <= table.left.top)
  assert.ok(table.left.right < table.center.x && table.right.x > table.center.right)
  assert.ok(table.self.y >= table.right.bottom)
  assert.equal(table.duplicate, false)
  assert.ok(table.topWidth >= 786 && table.topWidth <= 788)
  assert.ok(table.left.width >= 492 && table.right.width >= 492)
  assert.ok(table.sideColumns >= 11 && table.sideRows === 1 && table.tileWidth >= 34 && table.tileWidth <= 36)
  assert.equal(table.numberTile, '四\n筒')
  assert.equal(table.stripTile, '三\n条')
  assert.equal(table.promptPosition, 'relative')
  assert.ok(table.prompt.y >= table.hand.bottom)
  assert.equal(table.sideways, '5s')
  assert.match(table.rotation, /^matrix\(0, 1, -1, 0,/)
  await evaluate(`(async () => { window.__sideDiscards.value=['E','9m','N','4p','3s','P','F','2m','1p','2p','3p','4p','5p','6p']; await window.__visualNextTick(); })()`)
  await sleep(300)
  const growth = await evaluate(`(() => { const box=s=>document.querySelector(s).getBoundingClientRect().toJSON(); const river=document.querySelector('[data-position="right"] [aria-label="弃牌"]'); return {left:box('[data-position="left"]'),right:box('[data-position="right"]'),rows:new Set([...river.children].map(t=>t.getBoundingClientRect().y)).size,tiles:river.children.length}; })()`)
  assert.equal(growth.tiles, 14)
  assert.equal(growth.rows, 2)
  assert.equal(growth.left.y, table.left.y)
  assert.equal(growth.right.y, table.right.y)
  assert.ok(growth.left.bottom > table.left.bottom && growth.right.bottom > table.right.bottom)
  await evaluate(`(async () => { window.__sideDiscards.value=Array.from({length:25},(_,i)=>['E','9m','N','4p','3s','P','F','2m'][i%8]); await window.__visualNextTick(); })()`)
  await sleep(300)
  const thirdRow = await evaluate(`(() => { const seat=document.querySelector('[data-position="left"]'); const river=seat.querySelector('[aria-label="弃牌"]'); return {top:seat.getBoundingClientRect().top,rows:new Set([...river.children].map(t=>t.getBoundingClientRect().y)).size}; })()`)
  assert.equal(thirdRow.top, table.left.y)
  assert.equal(thirdRow.rows, 3)
  await evaluate(`(async () => { window.__sideDiscards.value=['E','9m','N','4p','3s','P','F','2m','1p','2p','3p','4p','5p','6p']; window.__sideMelds.value=Array.from({length:3},()=>({meld_type:'ming_gang',tiles:['C','C','C','C']})); await window.__visualNextTick(); })()`)
  await sleep(300)
  const gangs = await evaluate(`(() => { const groups=[...document.querySelectorAll('[data-position="left"] [aria-label="副露牌组"]')]; return {count:groups.length,rows:new Set(groups.map(g=>g.getBoundingClientRect().y)).size,right:groups.at(-1)?.getBoundingClientRect().right,seatRight:document.querySelector('[data-position="left"]').getBoundingClientRect().right}; })()`)
  assert.equal(gangs.count, 3)
  assert.equal(gangs.rows, 1)
  assert.ok(gangs.right < gangs.seatRight)
  await evaluate(`(async () => { window.__sideMelds.value=[{meld_type:'chi',tiles:['4s','5s','6s'],claimed_tile:'5s',provider_seat:'E'}]; await window.__visualNextTick(); })()`)
  await sleep(100)
  let shot = await command('Page.captureScreenshot', { format: 'png' })
  await writeFile('tests/artifacts/pve-diamond.png', Buffer.from(shot.data,'base64'))
  await evaluate(`document.querySelector('[aria-label="手牌槽位"]').scrollIntoView({block:'start'})`)
  await sleep(100)
  const visible = await evaluate(`(() => { const hand=document.querySelector('[aria-label="手牌槽位"]').getBoundingClientRect(); const prompt=document.querySelector('.action-prompt-wrap').getBoundingClientRect(); return {handTop:hand.top,promptBottom:prompt.bottom,viewport:innerHeight}; })()`)
  assert.ok(visible.handTop >= 0 && visible.promptBottom <= visible.viewport)
  shot = await command('Page.captureScreenshot', { format: 'png' })
  await writeFile('tests/artifacts/pve-pong-prompt.png', Buffer.from(shot.data,'base64'))
  await command('Emulation.setDeviceMetricsOverride', { width: 390, height: 844, deviceScaleFactor: 1, mobile: false })
  await sleep(100)
  const narrow = await evaluate(`(() => { const hand=document.querySelector('[aria-label="手牌槽位"]').getBoundingClientRect(); const prompt=document.querySelector('.action-prompt-wrap').getBoundingClientRect(); return {handBottom:hand.bottom,promptTop:prompt.top,overflow:document.documentElement.scrollWidth>innerWidth}; })()`)
  assert.ok(narrow.promptTop >= narrow.handBottom)
  assert.equal(narrow.overflow, false)
  await evaluate(`document.querySelector('[aria-label="手牌槽位"]').scrollIntoView({block:'start'})`)
  shot = await command('Page.captureScreenshot', { format: 'png' })
  await writeFile('tests/artifacts/pve-pong-mobile.png', Buffer.from(shot.data,'base64'))
  const responsive = []
  for (const width of [960, 1100, 1280]) {
    await command('Emulation.setDeviceMetricsOverride', { width, height: 1000, deviceScaleFactor: 1, mobile: false })
    await sleep(50)
    const layout = await evaluate(`(() => { const left=document.querySelector('[data-position="left"]').getBoundingClientRect(); const right=document.querySelector('[data-position="right"]').getBoundingClientRect(); return {leftWidth:left.width,rightWidth:right.width,sameTop:left.y===right.y,overflow:document.documentElement.scrollWidth>innerWidth}; })()`)
    assert.ok(layout.sameTop)
    assert.equal(layout.overflow, false)
    responsive.push({ width, ...layout })
  }
  const decisionViewports = []
  for (const [width, height] of [[1366, 768], [1920, 1080]]) {
    await command('Emulation.setDeviceMetricsOverride', { width, height, deviceScaleFactor: 1, mobile: false })
    await evaluate(`document.querySelector('[aria-label="自家操作工作台"]').scrollIntoView({block:'start'})`)
    await sleep(100)
    const view = await evaluate(`(() => { const box=s=>document.querySelector(s)?.getBoundingClientRect(); const rows=[...document.querySelectorAll('[aria-label="切牌推荐结果"] [role="list"] > li')]; const river=document.querySelector('[aria-label="自家牌河"] .mahjong-tile'); const meld=document.querySelector('[aria-label="已录入副露"] .mahjong-tile'); return {heroTop:box('[aria-label="切牌推荐结果"]').top,fourthBottom:rows[3]?.getBoundingClientRect().bottom,panelHeight:box('[aria-label="切牌推荐结果"]').height,riverTileWidth:river?.getBoundingClientRect().width,meldTileWidth:meld?.getBoundingClientRect().width,viewport:innerHeight,overflow:document.documentElement.scrollWidth>innerWidth}; })()`)
    assert.ok(view.heroTop >= 0 && view.fourthBottom <= view.viewport)
    assert.equal(view.riverTileWidth, 33)
    assert.equal(view.meldTileWidth, 33)
    assert.equal(view.overflow, false)
    decisionViewports.push({ width, height, ...view })
    if (width === 1366) {
      shot = await command('Page.captureScreenshot', { format: 'png' })
      await writeFile('tests/artifacts/pve-ev-1366.png', Buffer.from(shot.data,'base64'))
    }
  }
  await command('Emulation.setDeviceMetricsOverride', { width: 1440, height: 1100, deviceScaleFactor: 1, mobile: false })
  await evaluate('window.__showSettlement()')
  await sleep(100)
  const settlement = await evaluate(`[...document.querySelectorAll('[data-sideways="true"]')].map(n=>({tile:n.dataset.tile,label:n.getAttribute('aria-label'),width:n.getBoundingClientRect().width,height:n.getBoundingClientRect().height}))`)
  assert.deepEqual(settlement.map(t=>t.tile), ['5s','5m'])
  assert.match(settlement[1].label, /胡/)
  assert.ok(settlement.every(t=>t.width>t.height))
  shot = await command('Page.captureScreenshot', { format: 'png' })
  await writeFile('tests/artifacts/pve-settlement.png', Buffer.from(shot.data,'base64'))
  await writeFile('tests/artifacts/pve-visual.json',JSON.stringify({table,growth,thirdRow,gangs,visible,narrow,responsive,decisionViewports,settlement},null,2))
  console.log('Diamond layout, anchored side seats with wrapping rivers, claimed chi and winning tile rotation: passed')
}
