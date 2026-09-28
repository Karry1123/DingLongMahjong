import assert from 'node:assert/strict'
import { spawn } from 'node:child_process'
import { mkdir, mkdtemp, writeFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'

const profile = await mkdtemp(join(tmpdir(), 'mahjong-ev-'))
const chrome = spawn(process.env.CHROME_PATH || 'C:/Program Files/Google/Chrome/Application/chrome.exe', [
  '--headless=new', '--disable-gpu', '--no-first-run', '--no-default-browser-check',
  '--remote-debugging-port=9347', '--remote-allow-origins=*', `--user-data-dir=${profile}`, 'about:blank',
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
    try { return (await (await fetch('http://127.0.0.1:9347/json/list')).json()).find(p => p.type === 'page') }
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
  const recommendation = await evaluate(`(async () => {
    // Diagnostic completion of the report's 13 tiles, pending the actual missing tile.
    const response=await fetch('/api/recommend',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({hand_tiles:'1m 1m 6m 7m 2p 2p 5p P 2s 5s E E E 6p'.split(' '),
        dealer_tile:'6p',is_dealer:true,seat_wind:'E',latest_drawn_tile:'5p'})});
    const result=await response.json();
    if(!response.ok) throw new Error(JSON.stringify(result));
    return result;
  })()`)
  assert.equal(recommendation.best_tile, '2s')
  assert.deepEqual(new Set(recommendation.candidates.map(row=>row.tile)), new Set(['2s','5s']))
  const reported = await evaluate(`(async()=>{
    const response=await fetch('/api/recommend',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({hand_tiles:'3m 6m 6m 7m 3p 4p 2s 4s 7s 8s P N C 4p'.split(' '),
        dealer_tile:'E',is_dealer:false,seat_wind:'W',round_wind:'E',latest_drawn_tile:'4p'})});
    const result=await response.json();if(!response.ok)throw new Error(JSON.stringify(result));return result;
  })()`)
  assert.equal(reported.best_tile,'N')
  // Mount the real component with five candidates so all drawer faces are tested.
  // Existing App styles remain loaded, including the stage and river/meld sizing.
  await evaluate(`(async () => {
    const source=await (await fetch('/src/components/PvEDiscardHud.vue')).text();
    const vueUrl=source.split('"').find(part=>part.startsWith('/')&&part.includes('/vue.js'));
    const {createApp, h} = await import(vueUrl);
    const {default: Hud} = await import('/src/components/PvEDiscardHud.vue');
    document.querySelector('#app').style.display='none';
    const host=document.createElement('div');
    host.className='viewport-wrapper is-stage-active';
    host.style.cssText='position:relative;width:280px;margin:20px';
    document.body.append(host);
    createApp({render:()=>h(Hud,{bestTile:'3m',interactive:true,candidates:
      ['3m','N','4p','6m','7s'].map((tile,index)=>({tile,ev_score:100-index,effective_count:22,deal_in_risks:{S:.12}}))})}).mount(host);
  })()`)
  const results = []
  for (const [width, height] of [[390,844],[844,390],[1280,720]]) {
    await command('Emulation.setDeviceMetricsOverride', { width, height, deviceScaleFactor: 1, mobile: false })
    await evaluate(`if(document.querySelector('.hud-more').getAttribute('aria-expanded')!=='true') document.querySelector('.hud-more').click()`)
    await sleep(250)
    const layout = await evaluate(`(() => {
      const drawer=document.querySelector('.hud-drawer'), bounds=drawer.getBoundingClientRect();
      return {faces:[...drawer.querySelectorAll('.hud-candidate-face')].map(face=>({w:face.offsetWidth,h:face.offsetHeight,scroll:face.scrollWidth>face.clientWidth||face.scrollHeight>face.clientHeight})),
        noOverflow:drawer.scrollWidth<=drawer.clientWidth&&drawer.scrollHeight<=drawer.clientHeight,
        fits:bounds.right<=innerWidth&&bounds.bottom<=innerHeight,
        svg:[...drawer.querySelectorAll('svg')].map(svg=>({w:svg.clientWidth,h:svg.clientHeight})),
        centered:[...document.querySelectorAll('.hud-face,.hud-candidate-face')].map(face=>{
          const box=face.getBoundingClientRect(), content=face.querySelector('.hud-face-text'), svg=face.querySelector('svg');
          let contentBox;if(svg)contentBox=svg.getBoundingClientRect();else{const range=document.createRange();range.selectNodeContents(content);contentBox=range.getBoundingClientRect()}
          const errors=content?[...(content.querySelectorAll('b').length?content.querySelectorAll('b'):[content])].map(line=>{
            const range=document.createRange();range.selectNodeContents(line);const r=range.getBoundingClientRect();return Math.abs((r.left+r.right-box.left-box.right)/2);
          }):[Math.abs((contentBox.left+contentBox.right-box.left-box.right)/2)];
          return {horizontalError:Math.max(...errors),verticalError:Math.abs((contentBox.top+contentBox.bottom-box.top-box.bottom)/2),
            fits:contentBox.left>=box.left&&contentBox.right<=box.right&&contentBox.top>=box.top&&contentBox.bottom<=box.bottom};
        })};
    })()`)
    assert.equal(layout.faces.length, 3)
    assert.ok(layout.faces.every(f=>f.w===28&&f.h===38&&!f.scroll), JSON.stringify(layout))
    assert.ok(layout.svg.every(s=>s.w<=28&&s.h<=38), JSON.stringify(layout))
    assert.ok(layout.noOverflow&&layout.fits, JSON.stringify(layout))
    assert.ok(layout.centered.every(face=>face.horizontalError<1&&face.verticalError<2&&face.fits),JSON.stringify(layout))
    results.push({width,height,...layout})
  }
  await mkdir('tests/artifacts/ev-drawer', { recursive:true })
  const shot = await command('Page.captureScreenshot', {format:'png'})
  await writeFile('tests/artifacts/ev-drawer/expanded.png', Buffer.from(shot.data,'base64'))
  console.log(JSON.stringify({status:'passed',bestTile:recommendation.best_tile,gm362005BestTile:reported.best_tile,results},null,2))
} finally {
  if (socket?.readyState===WebSocket.OPEN) {
    try { await command('Browser.close') } catch {}
    socket.close()
  }
  chrome.kill()
}
