/** Clock identity stays unchanged across bank heartbeats; every new actionable window chimes once. */
export function selfTurnCueKey(game) {
  if (!game || !['discard','response'].includes(game.phase)) return ''
  const clock = game.clocks?.[game.seat_wind]
  if (!clock || clock.paused || !game.actions?.length) return ''
  return `${game.game_id}:${game.seat_wind}:${game.phase}:${clock.started_at}`
}
