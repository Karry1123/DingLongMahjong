import assert from 'node:assert/strict'
import { spawn } from 'node:child_process'
import { mkdir, mkdtemp, writeFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { northDiscardDeal } from '../tests/pveFixture.js'

const port = 9342
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
  await command('Page.navigate', { url: process.env.PVE_URL || 'http://127.0.0.1:5178/' })
  await until(() => evaluate(`!![...document.querySelectorAll('button')].find(button=>button.textContent.includes('人机对战'))`))
  await evaluate(`[...document.querySelectorAll('button')].find(button=>button.textContent.includes('人机对战')).click()`)
  await until(() => evaluate(`!![...document.querySelectorAll('button')].find(button=>button.textContent.includes('开始对战'))`))
  await evaluate(`document.querySelector('[aria-label="人机对战设置"] input[type="checkbox"]').click()`)
  await evaluate(`[...document.querySelectorAll('button')].find(button=>button.textContent.includes('开始对战')).click()`)
  await until(() => evaluate(`!!document.querySelector('.pve-self-hand')`))

  await sleep(500);
  await evaluate(`(() => {
    const s=document.querySelector('#app').__vue_app__._instance.setupState;
    s.gameState='GAME_OVER'; s.showGameOverModal=false;
    s.roundState.melds=['1m','9m','1s','9s'].map(tile=>({meld_type:'ming_gang',tiles:[tile,tile,tile,tile]}));
    s.roundState.handTiles=['2p'];
    s.roundState.discards=Array(24).fill('3p');
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
    await capture(`${width}x${height}`);
    console.log(JSON.stringify({width,height,status:'passed',layout}));
  }
} finally {
  if(socket?.readyState===WebSocket.OPEN) {try {await command('Browser.close')} catch {} socket.close()}
  chrome.kill();
}
