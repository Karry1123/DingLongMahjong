import { ALL_TILES } from '../src/constants/tiles.js'
import { detectTableResponses } from '../src/utils/callDetector.js'

/** Deterministic physical deck: East has north, with no claims on north. */
export function northDiscardDeal() {
  for (let seed = 1; seed < 1000; seed++) {
    let random = seed
    const deck = ALL_TILES.flatMap((tile) => Array(4).fill(tile))
    for (let i = deck.length - 1; i > 0; i--) {
      random = (Math.imul(random, 1664525) + 1013904223) >>> 0
      const j = random % (i + 1)
      ;[deck[i], deck[j]] = [deck[j], deck[i]]
    }
    const dealer_tile = deck.pop()
    const hands = Object.fromEntries(['E', 'S', 'W', 'N'].map((seat) => [seat, deck.splice(0, seat === 'E' ? 14 : 13)]))
    if (!hands.E.includes('N') || dealer_tile === 'N') continue
    const detection = detectTableResponses({ providerSeat: 'E', discardedTile: 'N', dealerTile: dealer_tile,
      selfSeat: 'E', godView: true, getSeat: (seat) => ({ hand: hands[seat], melds: [] }) })
    if (!detection.hasResponse) return { dealer_tile, hands, dealer_seat: 'E', first_turn_seat: 'E', wall_tiles: deck, wall_count: deck.length }
  }
  throw new Error('No north discard fixture')
}
