import assert from 'node:assert/strict'
import { test } from 'node:test'
import { createSSRApp } from 'vue'
import { createServer } from 'vite'
import { renderToString } from 'vue/server-renderer'

test('PvP and PvE settlement layouts turn only the claimed open chi tile and the winning tile', async () => {
  const vite = await createServer({ server: { middlewareMode: true, hmr: false }, appType: 'custom' })
  try {
    const Modal = (await vite.ssrLoadModule('/src/components/GameOverModal.vue')).default
    const groups = [
      { kind: 'chi', source: 'open', claimed_tile: '5m', provider_seat: 'E', display_tiles: ['3m', '4m', '5m'].map(code => ({ code })) },
      { kind: 'chi', source: 'concealed', display_tiles: ['4m', '5m', '6m'].map(code => ({ code })) },
      { kind: 'head', display_tiles: [{ code: 'C' }, { code: 'C', is_win_tile: true }] },
    ]
    for (const pvp of [false, true]) {
      const html = await renderToString(createSSRApp(Modal, { pvp, seatWind: 'S', dealerSeat: 'E', info: {
        winner_seat: 'S', win_type: 'ron', win_tile: 'C', final_hu: 32,
        seat_details: { S: { winning_hand_groups: groups } },
      } }))
      const tiles = html.match(/<span\b[^>]*class="[^"]*mahjong-tile[^>]*>/g) || []
      const fives = tiles.filter(tag => tag.includes('data-tile="5m"'))
      // PvP renders landscape only; PvE also renders the ordinary layout.
      // Each layout turns one claimed five and keeps the concealed five upright.
      const layouts = pvp ? 1 : 2
      assert.equal(fives.length, 2 * layouts)
      assert.equal(fives.filter(tag => tag.includes('data-sideways="true"')).length, layouts)
      assert.equal(tiles.filter(tag => tag.includes('data-tile="4m"') && tag.includes('data-sideways="true"')).length, 0)
      assert.equal(tiles.filter(tag => tag.includes('data-tile="C"') && tag.includes('data-sideways="true"')).length, layouts)
      const landscape = html.match(/class="landscape-winner-groups"[\s\S]*?class="landscape-winner-breakdown"/)?.[0]
      assert.ok(landscape)
      assert.match(landscape, /data-tile="3m"[\s\S]*data-tile="5m"[^>]*data-sideways="true"[\s\S]*data-tile="4m"/)
    }
  } finally { await vite.close() }
})
