import assert from 'node:assert/strict'
import { spawn } from 'node:child_process'
import { mkdir, mkdtemp, writeFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { readFile } from 'node:fs/promises'

const profile = await mkdtemp(join(tmpdir(), 'mahjong-gm4720ef-'))
const chrome = spawn(process.env.CHROME_PATH || 'C:/Program Files/Google/Chrome/Application/chrome.exe', [
  '--headless=new', '--disable-gpu', '--no-first-run', '--no-default-browser-check',
  '--remote-debugging-port=9353', '--remote-allow-origins=*', `--user-data-dir=${profile}`, 'about:blank',
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
    try { return (await (await fetch('http://127.0.0.1:9353/json/list')).json()).find(p => p.type === 'page') }
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
  const archived=JSON.parse(await readFile('../backend/tests/fixtures/gm4720ef.json','utf8'))
  const variants=[{name:'supplied',hand:'1m 1m 3p 3p 3p 7p 8p 8p 9p 2s 3s 4s C'.split(' ')},
    {name:'archived',hand:archived.hand_tiles}]
  const results=[];await mkdir('tests/artifacts/gm4720ef',{recursive:true})
  for(const variant of variants){
    const payload={...archived,hand_tiles:variant.hand,event:{event_type:'DISCARD',actor_seat:'N',tile:'1m'},
      opponents:archived.opponents.map(p=>({...p,discards:p.seat_wind==='N'?p.discards.slice(0,-1):p.discards}))}
    const response=await fetch('http://127.0.0.1:8000/api/game/step',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)})
    assert.equal(response.status,200)
    const result=await response.json(),decision=result.call_decision
    assert.equal(decision.recommended_action.action_type,'pong')
    await evaluate(`(()=>{
      const s=document.querySelector('#app').__vue_app__._instance.setupState;
      s.soundMuted=true;s.enableEV=true;s.activeUiMode='PVE';s.gameMode='PVE';s.gameState='PLAYING';s.pveOpening=false;
      s.session.tableLocked.value=true;s.godViewWallMode=false;s.dealerSeat='E';s.gameRoundId='gm4720ef-${variant.name}';
      Object.assign(s.roundState,{seatWind:'E',roundWind:'E',dealerTile:'1s',isDealer:true,
        handTiles:${JSON.stringify(variant.hand)},melds:[],discards:${JSON.stringify(archived.discards)},opponents:${JSON.stringify(archived.opponents)}});
      s.wallTiles=Array(66).fill('6p');s.currentTurnSeat='N';s.lastDiscardSeat='N';s.currentPhase='WAIT_RESPONSE';
      s.lastStepResult={...${JSON.stringify(result)},_response_tile:'1m',_table_responses:[{seat:'E',types:['pong']}],pending_hu_queue:[]};
    })()`)
    await until(()=>evaluate(`!!document.querySelector('button[data-action="pong"] .action-recommend-badge')`))
    for(const [width,height] of [[1280,720],[390,844],[844,390]]){
      await command('Emulation.setDeviceMetricsOverride',{width,height,deviceScaleFactor:1,mobile:false});await sleep(180)
      const flags=await evaluate(`(()=>{
        const pong=document.querySelector('button[data-action="pong"]'),pass=document.querySelector('button[data-action="pass"]'),r=pong.getBoundingClientRect();
        return {pongRecommended:!!pong.querySelector('.action-recommend-badge'),passRecommended:!!pass.querySelector('.action-recommend-badge'),
          previewTiles:pong.querySelectorAll('.action-preview-tile').length,visible:r.width>0&&r.height>0&&r.left>=0&&r.right<=innerWidth&&r.top>=0&&r.bottom<=innerHeight};
      })()`)
      assert.ok(flags.pongRecommended&&!flags.passRecommended&&flags.previewTiles===3&&flags.visible,JSON.stringify(flags))
      results.push({variant:variant.name,width,height,...flags})
      const shot=await command('Page.captureScreenshot',{format:'png'});await writeFile(`tests/artifacts/gm4720ef/${variant.name}-${width}.png`,Buffer.from(shot.data,'base64'))
    }
  }
  console.log(JSON.stringify({status:'passed',results},null,2))
} finally {
  if(socket?.readyState===WebSocket.OPEN){try{await command('Browser.close')}catch{}socket.close()}
  chrome.kill()
}
