import { WIND_ORDER } from '../constants/tiles.js'

export const PVE_PLAYER_ROLES = ['自家', '下家', '对家', '上家']

/** Map a fixed relative player identity to this hand's wind (dealer is East). */
export function pveWindForPlayer(playerId, dealerPlayerId) {
  const offset = (playerId - dealerPlayerId + WIND_ORDER.length) % WIND_ORDER.length
  return WIND_ORDER[offset]
}

/** Build opponents by stable table position, with their current hand winds. */
export function pveOpponentsForDealer(dealerPlayerId) {
  return [
    { playerId: 1, role: PVE_PLAYER_ROLES[1] },
    { playerId: 2, role: PVE_PLAYER_ROLES[2] },
    { playerId: 3, role: PVE_PLAYER_ROLES[3] },
  ].map(({ playerId, role }) => ({
    role,
    seat_wind: pveWindForPlayer(playerId, dealerPlayerId),
    is_dealer: false,
    melds: [],
    discards: [],
    hand_tiles: [],
  }))
}

/** Preserve each player's accumulated total while the wind assignment rotates. */
export function remapPveScores(scores, oldDealerPlayerId, newDealerPlayerId) {
  const remapped = { E: 0, S: 0, W: 0, N: 0 }
  for (let offset = 0; offset < WIND_ORDER.length; offset += 1) {
    const oldWind = WIND_ORDER[offset]
    const playerId = (oldDealerPlayerId + offset) % WIND_ORDER.length
    const newWind = pveWindForPlayer(playerId, newDealerPlayerId)
    remapped[newWind] = Number(scores?.[oldWind] || 0)
  }
  return remapped
}
