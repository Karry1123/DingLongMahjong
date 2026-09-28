import assert from 'node:assert/strict'
import { spawn } from 'node:child_process'
import { mkdir, mkdtemp, writeFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { northDiscardDeal } from '../tests/pveFixture.js'

const port = 9342
const profile = await mkdtemp(join(tmpdir(), 'mahjong-zoom-'))
const chrome = spawn(process.env.CHROME_PATH || 'C:/Program Files/Google/Chrome/Application/chrome.exe', [
  '--headless=new', '--disable-extensions', '--no-proxy-server', '--disable-gpu', '--no-first-run', '--no-default-browser-check',
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
async function click(selector) {
  const point=await evaluate(`(() => {const r=document.querySelector(${JSON.stringify(selector)}).getBoundingClientRect(); return {x:r.left+r.width/2,y:r.top+r.height/2};})()`)
  await command('Input.dispatchMouseEvent',{type:'mousePressed',...point,button:'left',clickCount:1})
  await command('Input.dispatchMouseEvent',{type:'mouseReleased',...point,button:'left',clickCount:1})
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
const shotDir = 'tests/artifacts/meld-grid'
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
    if(message.method === 'Runtime.exceptionThrown') console.error(JSON.stringify(message.params.exceptionDetails))
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
    window.__voiceRequests=[];
    window.__voicePlays=0;
    const originalStart=AudioBufferSourceNode.prototype.start;
    AudioBufferSourceNode.prototype.start=function(...args) { if(this.buffer?.duration>.1) { window.__voicePlays++; window.__voiceContext=this.context; } return originalStart.apply(this,args); };
    const record = {game_id:'GM-ZOOM01',round_id:'zoom',timestamp:new Date().toISOString(),
      config:{seat_wind:'E',initial_hands:{E:['1m','2m','3m'],S:['4m'],W:['5m'],N:['6m']}},
      steps:[{seat:'E',action:'DISCARD',tile:'1m'},{seat:'S',action:'DISCARD',tile:'4m'}]};
    const summary = {game_id:record.game_id,round_wind:'E',self_seat:'E',timestamp:record.timestamp,
      win_type:'draw',winner_name:'荒牌流局',self_score:{net:0},xiajia_score:{net:0},
      duijia_score:{net:0},shangjia_score:{net:0}};
    window.fetch = (url, init) => {
      const path = String(url);
      if(path.includes('/audio/')) window.__voiceRequests.push(path);
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

  assert.deepEqual(await evaluate('window.__voiceRequests'), []);
  await click('.pve-self-hand [data-tile="N"]');
  await until(() => evaluate(`document.querySelector('#app').__vue_app__._instance.setupState.roundState.discards.includes('N')`));
  await until(() => evaluate(`window.__voiceRequests.some(url=>url.endsWith('/beifeng.dat')) && window.__voicePlays>0 && window.__voiceContext?.state==='running'`));
  assert.ok(await evaluate(`window.__voiceRequests.every(url=>url.endsWith('.dat'))`));
  console.log('Actual north discard triggers lazy playback with a running AudioContext');
  await sleep(500);
  await evaluate(`(() => {
    const s=document.querySelector('#app').__vue_app__._instance.setupState;
    s.gameState='GAME_OVER'; s.showGameOverModal=false; s.enableEV=false; s.error='';
    s.roundState.melds=['1m','9m','1s','9s'].map(tile=>({meld_type:'ming_gang',tiles:[tile,tile,tile,tile]}));
    s.roundState.handTiles=['2p'];
    s.roundState.discards=Array(24).fill('3p');
    for (const opponent of s.roundState.opponents) { opponent.discards=Array(24).fill('2m'); opponent.hand_tiles=['1m']; opponent.melds=['1m','9m','1s','9s'].map(tile=>({meld_type:'ming_gang',tiles:[tile,tile,tile,tile]})); }
    s.currentTurnSeat='S'; s.currentPhase='WAITING';
  })()`)
  for (const [width,height] of [[844,390],[1280,720]]) {
    await command('Emulation.setDeviceMetricsOverride',{width,height,deviceScaleFactor:1,mobile:width<1000});
    await sleep(400);
    const layout=await evaluate(`(() => {
      const container=document.querySelector('.pve-self-controls > .compact-melds');
      const list=container.querySelector('[aria-label="已录入副露"]');
      const rect=e=>{const r=e.getBoundingClientRect();return {x:r.x,y:r.y,right:r.right,bottom:r.bottom}};
      return {container:rect(container),river:rect(document.querySelector('.self-river')),
        groups:[...list.children].map(rect),
        tiles:[...list.querySelectorAll('[data-meld-group]')].map(group=>[...group.querySelectorAll('.mahjong-tile')].map(rect)),
        display:getComputedStyle(list).display};
    })()`);
    assert.equal(layout.display,'grid');
    assert.equal(layout.groups.length,4);
    assert.ok(Math.abs(layout.groups[0].y-layout.groups[1].y)<1);
    assert.ok(Math.abs(layout.groups[2].y-layout.groups[3].y)<1);
    assert.ok(layout.groups[2].y>=layout.groups[0].bottom);
    assert.ok(layout.container.right<layout.river.x,'meld area overlaps river horizontally');
    for (const tiles of layout.tiles) {
      assert.equal(tiles.length,4);
      assert.ok(tiles.every(tile=>Math.abs(tile.y-tiles[0].y)<1));
      for(let i=1;i<4;i++) assert.ok(tiles[i].x>=tiles[i-1].right-.5);
      assert.ok(tiles[3].right<=layout.container.right+.5);
    }
    const geometry = await evaluate(`(() => {
      const rect=e=>e.getBoundingClientRect();
      const overlaps=(a,b)=>a.left<b.right-1&&a.right>b.left+1&&a.top<b.bottom-1&&a.bottom>b.top+1;
      const failures=[];
      for(const seat of document.querySelectorAll('.opponent-seat')) {
        const river=seat.querySelector('.discard-river');
        for(const tile of seat.querySelectorAll('.meld-area .mahjong-tile')) {
          if(overlaps(rect(tile),rect(river))) failures.push(seat.dataset.position+' meld overlaps river');
          if(Math.abs(parseFloat(getComputedStyle(tile).width)-29.9)>.1) failures.push('meld size');
        }
      }
      const rivers=[...document.querySelectorAll('.discard-river')];
      for(const river of rivers) for(const tile of river.children) {
        const a=rect(tile),b=rect(river);
        if(a.left<b.left-1||a.right>b.right+1||a.top<b.top-1||a.bottom>b.bottom+1) failures.push('river clipping');
        if(Math.abs(parseFloat(getComputedStyle(tile).width)-27.6)>.1) failures.push('river size');
      }
      for(let i=0;i<rivers.length;i++) for(let j=i+1;j<rivers.length;j++) if(overlaps(rect(rivers[i]),rect(rivers[j]))) failures.push('rivers overlap');
      return failures;
    })()`);
    assert.deepEqual(geometry,[]);
    assert.ok(await evaluate(`['.pve-self-hand','.discard-river','.meld-area','.compact-melds'].every(selector=>[...document.querySelectorAll(selector+' .mahjong-tile')].filter(tile=>/^[1-9][ps]$/.test(tile.dataset.tile)).every(tile=>tile.querySelector('[data-artwork="'+tile.dataset.tile+'"]')))`));
    await capture(`${width}x${height}`);
    console.log(JSON.stringify({width,height,status:'passed'}));
  }
  await evaluate(`(() => {
    const state=document.querySelector('#app').__vue_app__._instance.setupState;
    state.selfWinSettlement={winner_seat:'E',win_type:'ron',win_tile:'5s',dealer_tile:'9m',
      winning_hand_groups:[{kind:'chi',source:'concealed',tiles:['3s','4s','5s'],winning_tile_index:2},{kind:'pong',tiles:['1s','1s','1s']},{kind:'chi',tiles:['7p','8p','9p']},{kind:'pong',tiles:['1p','1p','1p']},{kind:'head',tiles:['2p','2p']}]};
    state.showGameOverModal=true;
  })()`);
  await until(() => evaluate(`!!document.querySelector('.landscape-winner-hand [data-artwork]')`));
  assert.equal(await evaluate(`document.querySelectorAll('.landscape-winner-hand [data-artwork]').length`),14);
  await capture('settlement-graphics');
  await evaluate(`document.querySelector('#app').__vue_app__._instance.setupState.showGameOverModal=false`);
  await command('Emulation.setDeviceMetricsOverride',{width:390,height:844,deviceScaleFactor:1,mobile:true});
  await sleep(200);
  assert.ok(await evaluate(`(() => { const r=document.querySelector('.game-stage').getBoundingClientRect(); return r.left>=-1&&r.top>=-1&&r.right<=innerWidth+1&&r.bottom<=innerHeight+1&&document.documentElement.scrollWidth<=innerWidth; })()`));
  await capture('portrait');
  await command('Emulation.setDeviceMetricsOverride',{width:1280,height:1000,deviceScaleFactor:1,mobile:false});
  await command('Page.navigate', { url: (process.env.PVE_URL || 'http://127.0.0.1:5178/')+'?preview=tiles' });
  await until(() => evaluate(`document.querySelectorAll('.draft-tile').length===18`));
  assert.equal(await evaluate(`document.querySelectorAll('.design-preview button').length`),7);
  assert.deepEqual(await evaluate('window.__voiceRequests'), []);
  await click('.design-preview button');
  await until(() => evaluate('window.__voicePlays===1'));
  assert.equal(await evaluate('window.__voiceRequests.length'),1);
  await until(() => evaluate("window.__voiceContext?.state==='running'"));
  await click('.design-preview button');
  await until(() => evaluate('window.__voicePlays===2'));
  assert.equal(await evaluate('window.__voiceRequests.length'),1);
  await until(() => evaluate("window.__voiceContext?.state==='running'"));
  const decoded=await evaluate(`(async () => {const {unpackVoiceData}=await import('/src/utils/voiceData.js'); const context=new AudioContext(); const results=[]; try {for(const file of ['dongfeng','nanfeng','xifeng','beifeng','hongzhong','facai','baiban']) {const response=await fetch('/audio/data/'+file+'.dat',{headers:{Accept:'application/octet-stream'}}); if(response.status!==200) throw Error(file+' HTTP '+response.status); const buffer=await context.decodeAudioData(unpackVoiceData(await response.arrayBuffer())); if(buffer.duration<.3) throw Error(file+' empty'); results.push({file,type:response.headers.get('content-type'),duration:buffer.duration});}} finally {await context.close();} return results;})()`);
  console.log(JSON.stringify({decoded}));
  await capture('tile-design-preview');
  console.log('Portrait stage, 18 shared tile designs, zero entry requests, lazy playback/cache and 7 browser fetch/decode checks passed');
} finally {
  if(socket?.readyState===WebSocket.OPEN) {try {await command('Browser.close')} catch {} socket.close()}
  chrome.kill();
}
