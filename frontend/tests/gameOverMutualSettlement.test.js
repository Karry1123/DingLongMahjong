import assert from 'node:assert/strict'
import { test } from 'node:test'
import { createServer } from 'vite'
import { createSSRApp } from 'vue'
import { renderToString } from 'vue/server-renderer'

test('game over shows three full lazi payouts and separate mutual comparisons', async () => {
  const vite = await createServer({ server: { middlewareMode: true }, appType: 'custom' })
  try {
    const Modal = (await vite.ssrLoadModule('/src/components/GameOverModal.vue')).default
    const transfers = [
      { from: 'W', to: 'E', amount: 100, raw_amount: 100, capped: false, transaction_type: 'winner_payout', note: '辣子封顶 · 基础赔付 100 分' },
      { from: 'S', to: 'E', amount: 100, raw_amount: 100, capped: false, transaction_type: 'winner_payout', note: '辣子封顶 · 基础赔付 100 分' },
      { from: 'N', to: 'E', amount: 100, raw_amount: 100, capped: false, transaction_type: 'winner_payout', note: '辣子封顶 · 基础赔付 100 分' },
      { from: 'W', to: 'S', amount: 14, transaction_type: 'mutual_settlement', note: '固有胡头互结 (2→16)' },
      { from: 'W', to: 'N', amount: 0, transaction_type: 'mutual_settlement', note: '固有胡头相等 (2 = 2)' },
      { from: 'N', to: 'S', amount: 7, transaction_type: 'mutual_settlement', note: '固有胡头互结 (2→16)' },
    ]
    const html = await renderToString(createSSRApp(Modal, { seatWind: 'E', dealerSeat: 'W', info: {
      winner_seat: 'E', win_type: 'zimo', final_hu: 104, is_dealer_win: false,
      transfers, payments: { payment_cap: 100, capped_seats: [], is_lazi: true,
        winner_payout_transactions: transfers.slice(0, 3),
        mutual_settlement_transactions: transfers.slice(3) },
      net_by_seat: { E: 300, S: -79, W: -114, N: -107 },
    }, cumulativeScores: { E: 300, S: -79, W: -114, N: -107 } }))
    // Desktop and landscape markup both render each of the three loser labels.
    assert.equal((html.match(/辣子封顶 · 基础赔付 100 分/g) || []).length, 6)
    assert.match(html, /未胡家固有胡头互结（独立结算）/)
    assert.match(html, /西 → 南：14/)
    assert.match(html, /西 → 北：0/)
    assert.match(html, /北 → 南：7/)
    assert.match(html, /本盘 -114/)
    const section = html.match(/<section[^>]*aria-label="固有胡头互结明细"[\s\S]*?<\/section>/)?.[0] || ''
    assert.equal((section.match(/<li /g) || []).length, 3)
  } finally { await vite.close() }
})

test('GM-C4C928 legacy score details name each credited meld and fan', async () => {
  const vite = await createServer({ server: { middlewareMode: true }, appType: 'custom' })
  try {
    const Modal = (await vite.ssrLoadModule('/src/components/GameOverModal.vue')).default
    const html = await renderToString(createSSRApp(Modal, { seatWind: 'W', dealerSeat: 'E', info: {
      game_id: 'GM-C4C928', winner_seat: 'W', win_type: 'ron', win_tile: '3m', final_hu: 64,
      hu_detail: { base_hu: 10, tile_hu: 6, fan: 2, details: {
        pairs: [{ tile: '7p', hu: 0 }],
        melds: [
          { source: 'open', type: 'pong', identity: 'W', tiles: ['W', 'W', 'W'], hu: 4 },
          { source: 'concealed', type: 'pong', tiles: ['3m', '3m', '3m'], hu: 2 },
        ],
        zimo: 0, kanzhang: 0,
        fan_items: ['本门风西风明刻 (翻番 ×2)', '硬碰硬 (翻番 ×2)'],
      } },
      seat_details: { W: { hand_tiles: ['3m', '3m', '7p', '7p'], melds: [{ meld_type: 'pong', tiles: ['W', 'W', 'W'] }] } },
    } }))
    assert.match(html, /明刻 西风 \(\+4胡\)/)
    assert.match(html, /明刻 三万 \(\+2胡\)/)
    assert.match(html, /本门风西风明刻 \(翻番 ×2\)/)
    assert.match(html, /硬碰硬 \(翻番 ×2\)/)
  } finally { await vite.close() }
})
