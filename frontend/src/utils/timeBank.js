/** Local PvE clock accounting. PvP uses the same public fields from the server. */
export class TimeBank {
  constructor(initialMs = 30000) { this.initialMs = initialMs; this.reset() }
  reset() { this.banks = Object.fromEntries([...'ESWN'].map(wind => [wind,this.initialMs])); this.clocks = {} }
  remaining(wind, now) {
    const clock = this.clocks[wind]
    return Math.max(0,this.banks[wind] - (!clock || clock.paused ? 0 : Math.max(0,now-clock.deadline)))
  }
  stop(wind, now) { this.banks[wind] = this.remaining(wind,now); delete this.clocks[wind] }
  sync(desired, now) {
    for (const wind of Object.keys(this.clocks)) if (!desired[wind] || desired[wind].token !== this.clocks[wind].token) this.stop(wind,now)
    for (const [wind, action] of Object.entries(desired)) {
      let clock = this.clocks[wind]
      if (!clock) clock = this.clocks[wind] = { token:action.token, kind:action.kind, remaining_ms:action.durationMs,
        started_at:now, deadline:action.paused ? null : now+action.durationMs, paused:!!action.paused }
      else if (action.paused && !clock.paused) {
        this.banks[wind] = this.remaining(wind,now)
        clock.remaining_ms = Math.max(0,clock.deadline-now);clock.deadline=null;clock.paused=true
      } else if (!action.paused && clock.paused) { clock.deadline=now+clock.remaining_ms;clock.paused=false }
      clock.kind = action.kind
    }
  }
  expired(now) { return Object.keys(this.clocks).filter(wind=>!this.clocks[wind].paused && now>=this.clocks[wind].deadline+this.banks[wind]) }
  snapshot(now) {
    const banks=Object.fromEntries([...'ESWN'].map(wind=>[wind,this.remaining(wind,now)]))
    const clocks=Object.fromEntries(Object.entries(this.clocks).map(([wind,clock])=>{
      const bank=!clock.paused && now>=clock.deadline
      return [wind,{...clock,stage:bank?'bank':'regular',regular_deadline:clock.deadline,
        regular_remaining_ms:clock.paused?clock.remaining_ms:Math.max(0,clock.deadline-now),
        bank_deadline:clock.paused?null:clock.deadline+this.banks[wind],bank_remaining_ms:banks[wind],
        deadline:bank?clock.deadline+this.banks[wind]:clock.deadline,remaining_ms:bank?banks[wind]:clock.remaining_ms}]
    }))
    return {clocks,banks}
  }
}
