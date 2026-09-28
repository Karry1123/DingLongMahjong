/** Server deadlines drive the clock; a stale render tick must never show 11s/7s. */
export function roomActionSeconds(clock, serverOffset = 0, now = Date.now()) {
  return roomClockState(clock, 0, serverOffset, now).seconds
}

/** Interpolate authoritative deadlines so the reserve starts without a broadcast gap. */
export function roomClockState(clock, bankMs = 30000, serverOffset = 0, now = Date.now()) {
  const seconds = ms => Math.max(0, Math.ceil(ms / 1000))
  if (!clock) return { seconds:0, bankSeconds:seconds(bankMs), stage:'idle', paused:false }
  if (clock.paused) return { seconds:seconds(clock.regular_remaining_ms ?? clock.remaining_ms), bankSeconds:seconds(clock.bank_remaining_ms ?? bankMs), stage:'paused', paused:true }
  const serverNow = now + serverOffset
  const regularDeadline = clock.regular_deadline ?? clock.deadline
  const regular = regularDeadline - serverNow
  const bankDeadline = clock.bank_deadline ?? regularDeadline + (clock.bank_remaining_ms ?? bankMs)
  const bank = regular > 0 ? clock.bank_remaining_ms ?? bankMs : Math.max(0, bankDeadline - serverNow)
  const stage = regular <= 0 && bankDeadline > regularDeadline ? 'bank' : 'regular'
  return { seconds:seconds(stage === 'bank' ? bank : Math.min(clock.remaining_ms ?? Infinity, regular)), bankSeconds:seconds(bank), stage, paused:false }
}
