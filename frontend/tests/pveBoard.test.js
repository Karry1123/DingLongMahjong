import assert from 'node:assert/strict'
import { test } from 'node:test'
import { createServer } from 'vite'
import { createSSRApp } from 'vue'
import { renderToString } from 'vue/server-renderer'

test('upgraded pong renders four visible tiles and a ming-kong label', async () => {
  const vite = await createServer({ server: { middlewareMode: true }, appType: 'custom' })
  try {
    const MeldTiles = (await vite.ssrLoadModule('/src/components/MeldTiles.vue')).default
    const html = await renderToString(createSSRApp(MeldTiles, {
      meld: { meld_type: 'ming_gang', tiles: ['1p','1p','1p','1p'] }, dealerTile: '9s',
    }))
    assert.match(html, /data-meld-type="ming_gang"/)
    assert.equal((html.match(/data-tile="1p"/g) || []).length, 4)
    assert.match(html, /明杠/)
  } finally { await vite.close() }
})

test('PvE board hides AI hand faces and labels whiteboard substitution in melds', async () => {
  const vite = await createServer({ server: { middlewareMode: true }, appType: 'custom' })
  try {
    const Board = (await vite.ssrLoadModule('/src/components/PvEBoard.vue')).default
    const html = await renderToString(createSSRApp(Board, {
      seatWind: 'E', currentTurnSeat: 'S', dealerSeat: 'E', dealerTile: '7m',
      opponents: [{ seat_wind: 'S', hand_tiles: ['P', '8m'], melds: [{ meld_type: 'chi', tiles: ['6m', 'P', '8m'], claimed_tile: 'P' }], discards: ['4p'] }],
      cumulativeScores: { E: 0, S: 10, W: 0, N: 0 },
    }))
    assert.match(html, /替七万/)
    assert.match(html, /已隐藏/)
    for (const hidden of html.matchAll(/class="concealed-hand"[\s\S]*?<\/div>/g)) {
      assert.doesNotMatch(hidden[0], /data-tile=/)
    }
    assert.match(html, /四筒/)
    assert.match(html, /data-tile="P" data-sideways="true"/)
    assert.doesNotMatch(html, /data-seat="E"/)
    assert.match(html, /data-seat="N" data-position="left"/)
    assert.match(html, /data-seat="W" data-position="top"/)
    assert.match(html, /data-seat="S" data-position="right"/)
    assert.match(html, /aria-label="白 · 替七万"/)
    const rotated = await renderToString(createSSRApp(Board, { seatWind: 'S', dealerTile: 'P' }))
    assert.match(rotated, /data-seat="E" data-position="left"/)
    assert.match(rotated, /data-seat="N" data-position="top"/)
    assert.match(rotated, /data-seat="W" data-position="right"/)
    assert.doesNotMatch(rotated, /白板承接/)
  } finally { await vite.close() }
})

test('settlement rotates the actual claimed and winning tiles, never an unrelated open tile', async () => {
  const vite = await createServer({ server: { middlewareMode: true }, appType: 'custom' })
  try {
    const Modal = (await vite.ssrLoadModule('/src/components/GameOverModal.vue')).default
    const html = await renderToString(createSSRApp(Modal, { info: {
      winner_seat: 'E', win_type: 'ron', win_tile: '5m', dealer_tile: '8s',
      winning_hand_groups: [
        { kind: 'chi', source: 'open', tiles: ['4s','5s','6s'], claimed_tile: '5s' },
        { kind: 'chi', source: 'concealed', tiles: ['4m','5m','6m'], winning_tile_index: 1 },
        { kind: 'head', tiles: ['2p','2p'] },
      ],
    } }))
    assert.match(html, /data-tile="5s" data-sideways="true"/)
    assert.match(html, /data-tile="5m" data-sideways="true" aria-label="五万 · 胡"/)
    assert.equal((html.match(/data-sideways="true"/g) || []).length, 2)
  } finally { await vite.close() }
})
