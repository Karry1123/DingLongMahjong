import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { TimeBank } from '../utils/timeBank.js'

/** Timers follow actual local turn/claim state; opening and network actions pause them. */
export function usePvEClocks(session, options = {}) {
  const s=session, store=new TimeBank(), state=ref(store.snapshot(Date.now())), error=ref('')
  let interval, executing=false, round='', expiredToken=''
  const player=wind=>wind===s.roundState.seatWind?{hand_tiles:s.roundState.handTiles,melds:s.roundState.melds}:s.roundState.opponents.find(p=>p.seat_wind===wind)
  const responseTile=()=>s.lastStepResult.value?._response_tile||s.roundState.opponents.find(p=>p.seat_wind===s.lastDiscardSeat.value)?.discards?.at(-1)||s.roundState.discards.at(-1)
  const desired=computed(()=>{
    if(s.gameMode.value!=='PVE'||s.gameState.value!=='PLAYING'||s.pveOpening?.value)return {}
    const active={},self=s.roundState.seatWind,provider=s.lastDiscardSeat.value
    if(s.isResponseWindow.value){
      const rows=(s.lastStepResult.value?._table_responses||[]).map(row=>({...row,types:row.types.filter(type=>!['hu','catch_win'].includes(type)||s.pendingHuQueue.value.includes(row.seat))}))
      const hu=s.currentHuSeat.value
      if(hu&&!rows.some(row=>row.seat===hu))rows.push({seat:hu,types:['hu']})
      const local=s.lastStepResult.value?.call_decision?.available_actions||[]
      if(!rows.some(row=>row.seat===self)&&s.lastStepResult.value?.need_self_action&&local.length)rows.push({seat:self,types:local.map(a=>a.action_type)})
      const face=responseTile()
      const token=`response:${provider}:${face}:${s.wallTiles.value.length}:${s.roundState.discards.length}:${s.roundState.opponents.map(p=>p.discards.length).join(',')}`
      for(const row of rows){
        if(!row.types.some(type=>['hu','catch_win','chi','pong','ming_gang'].includes(type)))continue
        const win=row.seat===hu
        const paused=!!s.loading.value||!!hu&&!win||!win&&row.types.includes('chi')&&!row.types.some(t=>['pong','ming_gang'].includes(t))&&rows.some(other=>other.seat!==row.seat&&other.types.some(t=>['pong','ming_gang'].includes(t)))
        active[row.seat]={token:`${token}:${row.seat}`,kind:win?'win':'response',durationMs:6000,paused}
      }
    }else{
      const wind=s.currentTurnSeat.value,p=player(wind)
      if(p&&p.hand_tiles.length+3*p.melds.length===14){
        const win=wind===self&&options.canSelfWin?.()
        active[wind]={token:`discard:${wind}:${[...p.hand_tiles].sort().join(',')}:${JSON.stringify(p.melds)}:${s.wallTiles.value.length}:${win?'win':''}`,kind:win?'win':'discard',durationMs:win?6000:10000,paused:!!s.loading.value}
      }
    }
    return active
  })
  function sync(){
    const id=s.gameRoundId.value
    if(id!==round){store.reset();round=id;expiredToken='';error.value=''}
    store.sync(desired.value,Date.now());state.value=store.snapshot(Date.now())
  }
  watch([desired,s.gameRoundId],sync,{deep:true,immediate:true,flush:'sync'})
  async function tick(){
    const now=Date.now();state.value=store.snapshot(now)
    if(executing||s.loading.value)return
    const wind=store.expired(now)[0],clock=store.clocks[wind]
    if(!clock||expiredToken===clock.token)return
    expiredToken=clock.token;executing=true
    try{
      const self=wind===s.roundState.seatWind
      if(s.isResponseWindow.value){
        const face=responseTile()
        if(clock.kind==='win'){
          if(self)await s.declareSelfRon(face,s.lastDiscardSeat.value)
          else await s.declareOpponentWin({seat:wind,winType:s.lastStepResult.value?._pending_add_kong?'rob_kong':'catch_win',winTile:face,discarderSeat:s.lastDiscardSeat.value})
        }else await s.passCall(face,wind)
      }else if(self&&options.canSelfWin?.())await options.onSelfWin()
      else{
        const p=player(wind),drawn=s.latestDrawnBySeat.value[wind]||p.hand_tiles.at(-1),index=p.hand_tiles.lastIndexOf(drawn)
        if(self)await s.discardTile(drawn,index)
        else await s.discardFromGodView(wind,drawn,index)
      }
    }catch(e){error.value=e.message||String(e)}finally{executing=false;sync()}
  }
  onMounted(()=>{interval=setInterval(tick,100)})
  onUnmounted(()=>{clearInterval(interval);store.sync({},Date.now())})
  return {clocks:computed(()=>state.value.clocks),timeBanks:computed(()=>state.value.banks),error}
}
