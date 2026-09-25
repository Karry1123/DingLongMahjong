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

/** East starts with a legal self-drawn winning hand for settlement UI tests. */
export function selfWinDeal() {
  const deck = ALL_TILES.flatMap((tile) => Array(4).fill(tile))
  const dealer_tile = '6p'
  const eastHand = ['1m', '1m', '1m', '2m', '2m', '2m', '3m', '3m', '3m', '4m', '4m', '4m', '5m', '5m']
  for (const tile of [dealer_tile, ...eastHand]) {
    const index = deck.indexOf(tile)
    if (index < 0) throw new Error(`Missing fixture tile ${tile}`)
    deck.splice(index, 1)
  }
  const hands = { E: eastHand }
  for (const seat of ['S', 'W', 'N']) hands[seat] = deck.splice(0, 13)
  return { dealer_tile, hands, dealer_seat: 'E', first_turn_seat: 'E', wall_tiles: deck, wall_count: deck.length }
}
