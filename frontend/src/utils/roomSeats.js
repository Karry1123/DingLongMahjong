export const ROOM_SEATS = [
  { seat: 0, wind: 'E', label: '东', position: 'left' },
  { seat: 1, wind: 'S', label: '南', position: 'bottom' },
  { seat: 2, wind: 'W', label: '西', position: 'right' },
  { seat: 3, wind: 'N', label: '北', position: 'top' },
]

export function countdownNumber(startAt, serverOffset, now = Date.now()) {
  return Math.max(0, Math.min(3, Math.ceil((startAt - now - serverOffset) / 1000)))
}

/** Rotate display coordinates only; all game commands still use physical winds. */
export function relativeRoomSeats(selfWind) {
  const index = ROOM_SEATS.findIndex(seat => seat.wind === selfWind)
  if (index < 0) throw new Error('无效的自家风位')
  const positions = ['bottom', 'right', 'top', 'left']
  const roles = ['自家', '下家', '对家', '上家']
  return ROOM_SEATS.map(seat => {
    const offset = (seat.seat - index + 4) % 4
    return { ...seat, position: positions[offset], role: roles[offset], isSelf: offset === 0 }
  })
}
