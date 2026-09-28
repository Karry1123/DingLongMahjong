import { relativeOpponents, tileLabel } from '../constants/tiles.js'

export function gameStatusHint({ wallCount=82, opponents=[], selfMelds=[] } = {}) {
  const totalMelds=selfMelds.length+opponents.reduce((n,p)=>n+(p.melds?.length||0),0)
  if (wallCount<20) return {level:'high',text:'海底绝张危险期，尽量跟打熟张！'}
  if (wallCount<=40) return {level:'warn',text:'局势进入白热化，谨防点炮放铳！'}
  if (wallCount<=65 || totalMelds>=3) return {level:'safe',text:'牌局步入中盘，各家搭子已成。'}
  return {level:'safe',text:'牌局平稳，四家摸打试探…'}
}

const HOLD_DRAWS=8 // Approximately two turns around the table, independent of API latency.
const keyOfMeld=m=>`${m.meld_type}|${[...(m.tiles||[])].sort().join(',')}`
function valuableMeld(m,player,dealerTile) {
  if (!['pong','ming_gang','an_gang','bu_gang'].includes(m.meld_type)) return ''
  const physical=m.tiles?.[0]
  if (!physical) return ''
  const face=physical==='P'&&dealerTile!=='P'?dealerTile:physical
  // Whiteboard triplets retain the physical dragon fan; fixed substitution
  // can identify the opponent's own wind, but never an invented round-wind fan.
  if (['P','C','F'].includes(physical)) return tileLabel(physical)
  if (face===player.seat_wind) return tileLabel(face)
  if (/^[19][mps]$/.test(face)) return tileLabel(face)
  return ''
}

/** Stateful event detection: public signals only, bounded warnings, no repeat renewal. */
export function createGameStatusTracker() {
  let round=null, previousWall=null, progress=0, active=null
  let players=new Map()
  function reset() { round=null; previousWall=null; progress=0; active=null; players=new Map() }
  function update(input={}) {
    const {wallCount=82,turnCount=1,opponents=[],seatWind='E',dealerTile='',
      threats=[],selfDiscards=[],roundId='',playing=true}=input
    const base=gameStatusHint(input)
    if (!playing) { reset(); return base }
    if (round!==roundId || (previousWall!==null&&wallCount>previousWall)) reset()
    round=roundId
    // River tiles disappear on claims. Count wall consumption as well so expiry
    // remains monotonic through chi/pong/kong and asynchronous model updates.
    const discards=selfDiscards.length+opponents.reduce((n,p)=>n+(p.discards?.length||0)+(p.melds?.length||0),0)
    progress=Math.max(progress,82-wallCount,(turnCount-1)*4,discards)
    previousWall=wallCount
    if (active && progress>=active.expires) active=null
    const roles=Object.fromEntries(relativeOpponents(seatWind).map(p=>[p.seat_wind,p.role]))
    const seen=new Map()
    for (const tile of selfDiscards) seen.set(tile,(seen.get(tile)||0)+1)
    for (const p of opponents) {
      for (const tile of p.discards||[]) seen.set(tile,(seen.get(tile)||0)+1)
      for (const m of p.melds||[]) for (const tile of m.tiles||[]) seen.set(tile,(seen.get(tile)||0)+1)
    }
    const events=[]
    for (const player of opponents) {
      const seat=player.seat_wind, melds=player.melds||[], n=melds.length
      const old=players.get(seat)||{melds:new Map(),n:0,probability:0,history:[],fresh:''}
      const who=(roles[seat]||`${seat}风`)+(player.is_dealer?'庄家':'')
      const counts=new Map(), values=[]
      for (const meld of melds) {
        const key=keyOfMeld(meld), count=(counts.get(key)||0)+1
        counts.set(key,count)
        if (count>(old.melds.get(key)||0)) {
          const label=valuableMeld(meld,player,dealerTile)
          if (label) values.push(label)
        }
      }
      const model=threats.find(t=>t.seat_wind===seat)
      const modelKnown=Number.isFinite(model?.probability)
      const p=Math.min(.99,Math.max(Number(model?.probability)||0,n>=3?.9:n>=2?.4:0))
      const history=old.history.filter(point=>point.tick>=progress-HOLD_DRAWS)
      const recentLow=history.length?Math.min(...history.map(point=>point.p)):old.probability
      const jump=old.modelKnown&&p>=.45&&p-recentLow>=.18
      const crossedHigh=p>=.8&&old.probability<.8
      const newMeldDanger=n>=2&&n>old.n
      const recent=(player.discards||[]).slice(-2)
      const freshSignature=(player.discards||[]).length+':'+recent.join(',')
      const fresh=progress>=12&&recent.length===2&&recent.every(t=>/^[3-7][mps]$/.test(t)&&seen.get(t)===1)
      const freshEvent=fresh&&freshSignature!==old.fresh
      if (values.length) events.push({priority:100+p+(player.is_dealer?.1:0),level:'high',
        text:`${who}大番（${values[0]}），防点炮！`})
      if (jump||crossedHigh||newMeldDanger||freshEvent) {
        const text=newMeldDanger?`${who}${n}副露，谨防听牌！`
          :freshEvent?`${who}连切生张，谨防放铳！`:`${who}听牌骤增，谨防放铳！`
        events.push({priority:(n>=3||p>=.8?110:80)+p+(player.is_dealer?.1:0),level:'high',
          text})
      }
      // Consume the probability rise once; identical or slowly rising model
      // responses cannot keep a warning alive indefinitely.
      const nextHistory=jump||crossedHigh?[{tick:progress,p}]:[...history.filter(point=>point.tick!==progress),{tick:progress,p}]
      players.set(seat,{melds:counts,n,probability:p,history:nextHistory,fresh:freshSignature,modelKnown:modelKnown||old.modelKnown})
    }
    events.sort((a,b)=>b.priority-a.priority)
    const event=events[0]
    if (event && (!active||event.priority>=active.priority)) active={...event,expires:progress+HOLD_DRAWS}
    return active?{level:active.level,text:active.text}:base
  }
  return {update,reset}
}
