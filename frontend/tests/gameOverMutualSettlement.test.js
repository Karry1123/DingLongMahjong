import assert from 'node:assert/strict'
import { test } from 'node:test'
import { createServer } from 'vite'
import { createSSRApp } from 'vue'
import { renderToString } from 'vue/server-renderer'

test('game over separates capped winner payouts from all three uncapped mutual comparisons', async () => {
  const vite = await createServer({ server: { middlewareMode: true }, appType: 'custom' })
  try {
    const Modal = (await vite.ssrLoadModule('/src/components/GameOverModal.vue')).default
    const transfers = [
      { from: 'W', to: 'E', amount: 100, raw_amount: 104, capped: true, transaction_type: 'winner_payout', note: '庄家全额→闲家胡' },
      { from: 'S', to: 'E', amount: 52, raw_amount: 52, capped: false, transaction_type: 'winner_payout', note: '闲家半额→闲家胡' },
      { from: 'N', to: 'E', amount: 52, raw_amount: 52, capped: false, transaction_type: 'winner_payout', note: '闲家半额→闲家胡' },
      { from: 'W', to: 'S', amount: 14, transaction_type: 'mutual_settlement', note: '固有胡头互结 (2→16)' },
      { from: 'W', to: 'N', amount: 0, transaction_type: 'mutual_settlement', note: '固有胡头相等 (2 = 2)' },
      { from: 'N', to: 'S', amount: 7, transaction_type: 'mutual_settlement', note: '固有胡头互结 (2→16)' },
    ]
    const html = await renderToString(createSSRApp(Modal, { seatWind: 'E', dealerSeat: 'W', info: {
      winner_seat: 'E', win_type: 'zimo', final_hu: 104, is_dealer_win: false,
      transfers, payments: { payment_cap: 100, capped_seats: ['W'],
        winner_payout_transactions: transfers.slice(0, 3),
        mutual_settlement_transactions: transfers.slice(3) },
      net_by_seat: { E: 204, S: -31, W: -114, N: -59 },
    }, cumulativeScores: { E: 204, S: -31, W: -114, N: -59 } }))
    assert.match(html, /和牌赔付已封顶 \(100\)/)
    assert.match(html, /未胡家固有胡头互结（独立结算）/)
    assert.match(html, /西 → 南：14/)
    assert.match(html, /西 → 北：0/)
    assert.match(html, /北 → 南：7/)
    assert.match(html, /本盘 -114/)
    const section = html.match(/<section[^>]*aria-label="固有胡头互结明细"[\s\S]*?<\/section>/)?.[0] || ''
    assert.equal((section.match(/<li /g) || []).length, 3)
  } finally { await vite.close() }
})
