import assert from 'node:assert/strict'
import { spawn } from 'node:child_process'
import { mkdir, mkdtemp, writeFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'

const profile = await mkdtemp(join(tmpdir(), 'mahjong-hu-'))
const chrome = spawn(process.env.CHROME_PATH || 'C:/Program Files/Google/Chrome/Application/chrome.exe', [
  '--headless=new', '--disable-gpu', '--no-first-run', '--no-default-browser-check',
  '--remote-debugging-port=9350', '--remote-allow-origins=*', `--user-data-dir=${profile}`, 'about:blank',
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
    try { return (await (await fetch('http://127.0.0.1:9350/json/list')).json()).find(p => p.type === 'page') }
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
    const realFetch=window.fetch.bind(window); window.__scores=[];window.__winAudio=[];
    window.fetch=async(url,init)=>{
      const res=await realFetch(url,init);
      if(String(url).endsWith('/calculate-hu')) window.__scores.push({body:JSON.parse(init.body),score:await res.clone().json(),status:res.status});
      if(['/WIN.dat','/ZIMO.dat'].some(name=>String(url).endsWith(name)))window.__winAudio.push({url:String(url),status:res.status});
      return res;
    };
    window.__huFixture=(zimo,capped)=>{
      const s=document.querySelector('#app').__vue_app__._instance.setupState;
      const hand=capped?'E E E S S S W W W N N N P P'.split(' '):'1m 2m 3m 4m 5m 6m 2p 3p 4p 5s 6s 7s E E'.split(' ');
      const win=hand.pop(); if(zimo) hand.push(win);
      s.soundMuted=true; s.activeUiMode='PVE'; s.gameMode='PVE'; s.gameState='PLAYING'; s.pveOpening=false;
      s.session.tableLocked.value=true; s.enableEV=false; s.localRecommend=null; s.selfWinDismissed=false;
      Object.assign(s.roundState,{handTiles:hand,seatWind:'E',roundWind:'S',dealerTile:'9p',isDealer:true,melds:[],discards:[],
        opponents:['S','W','N'].map(seat=>({seat_wind:seat,melds:[],discards:seat==='N'&&!zimo?[win]:[],hand_tiles:[]}))});
      s.latestDrawnTile=zimo?win:null; s.currentTurnSeat=zimo?'E':'N'; s.lastDiscardSeat=zimo?null:'N';
      s.currentPhase=zimo?'MY_TURN_DISCARD':'WAIT_RESPONSE';
      s.lastStepResult=zimo?{self_win_info:{is_win:true,win_tile:win}}:{need_self_action:true,action_phase:'CALL',_response_tile:win,pending_hu_queue:['E'],
        _table_responses:[{seat:'E',types:['catch_win']}],call_decision:null};
    };
  })()`)
  const results=[]
  await mkdir('tests/artifacts/hu-preview',{recursive:true})
  for(const zimo of [true,false]) for(const capped of [false,true]) {
    console.log(JSON.stringify({testing:{zimo,capped}}))
    await evaluate(`window.__huFixture(${zimo},${capped})`)
    const selector=zimo?'.self-win-button':'button[data-action="hu"]'
    await until(()=>evaluate(`document.querySelector('${selector}')?.textContent.includes('胡)')||document.querySelector('${selector}')?.textContent.includes('辣子)')`))
    const expected=await evaluate(`window.__scores.at(-1)`)
    assert.equal(expected.status,200); assert.equal(expected.body.is_zimo,zimo); assert.equal(expected.body.hand_tiles.length,13)
    assert.equal(expected.body.round_wind,'S'); assert.equal(expected.score.is_lazi,capped)
    for(const [width,height] of [[1280,720],[390,844],[844,390]]) {
      await command('Emulation.setDeviceMetricsOverride',{width,height,deviceScaleFactor:1,mobile:false}); await sleep(180)
      const layout=await evaluate(`(()=>{
        const b=document.querySelector('${selector}'),r=b.getBoundingClientRect(),range=document.createRange();range.selectNodeContents(b);const text=range.getBoundingClientRect();
        return {label:(b.querySelector('.action-label')||b).textContent.trim(),fits:r.left>=0&&r.top>=0&&r.right<=innerWidth&&r.bottom<=innerHeight,
          textFits:text.left>=r.left&&text.right<=r.right&&text.top>=r.top&&text.bottom<=r.bottom,
          noDialog:!document.querySelector('.pve-self-win-overlay,[aria-label="自摸操作"][role="dialog"]'),noTooltip:!b.hasAttribute('title'),
          noDetails:!document.querySelector('.self-win-actions dl,.self-win-actions ul,.self-win-actions details')};
      })()`)
      assert.equal(layout.label,`${zimo?'自摸':'胡'} (${capped?'辣子':expected.score.final_hu+'胡'})`)
      assert.ok(layout.fits&&layout.textFits&&layout.noDialog&&layout.noTooltip&&layout.noDetails,JSON.stringify(layout))
      results.push({zimo,capped,width,height,...layout})
      const shot=await command('Page.captureScreenshot',{format:'png'})
      await writeFile(`tests/artifacts/hu-preview/${zimo?'zimo':'ron'}-${capped?'cap':'normal'}-${width}.png`,Buffer.from(shot.data,'base64'))
    }
    await evaluate(`(()=>{const s=document.querySelector('#app').__vue_app__._instance.setupState;s.soundMuted=false;document.querySelector('${selector}').click()})()`)
    await until(()=>evaluate(`document.querySelector('#app').__vue_app__._instance.setupState.gameState==='GAME_OVER'`))
    assert.equal(await evaluate(`document.querySelector('#app').__vue_app__._instance.setupState.selfWinSettlement.is_zimo`),zimo)
    await until(()=>evaluate(`window.__winAudio.some(a=>a.url.endsWith('/${zimo?'ZIMO':'WIN'}.dat')&&a.status===200)`))
    results.push({zimo,capped,voice:zimo?'ZIMO':'WIN',settled:true})
  }
  console.log(JSON.stringify({status:'passed',requests:await evaluate('window.__scores.length'),results},null,2))
} finally {
  if(socket?.readyState===WebSocket.OPEN){try{await command('Browser.close')}catch{}socket.close()}
  chrome.kill()
}
