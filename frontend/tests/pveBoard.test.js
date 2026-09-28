import assert from 'node:assert/strict'
import { test } from 'node:test'
import { createServer } from 'vite'
import { createSSRApp } from 'vue'
import { renderToString } from 'vue/server-renderer'

function assertGraphicalSuits(html) {
  const tiles = [...html.matchAll(/data-tile="([1-9][ps])"/g)].map(match => match[1]).sort()
  const graphics = [...html.matchAll(/data-artwork="([1-9][ps])"/g)].map(match => match[1]).sort()
  assert.ok(tiles.length > 0)
  assert.deepEqual(graphics, tiles)
}

test('all 18 bamboo and circle tiles use SVG, including sideways tiles', async () => {
  const vite = await createServer({ server: { middlewareMode: true }, appType: 'custom' })
  try {
    const Tile = (await vite.ssrLoadModule('/src/components/MahjongTile.vue')).default
    for (const suit of ['s', 'p']) for (let n = 1; n <= 9; n++) {
      const html = await renderToString(createSSRApp(Tile, { code: `${n}${suit}`, sideways: n % 2 === 0 }))
      assertGraphicalSuits(html)
      assert.doesNotMatch(html, /class="characters/)
    }
    const wan = await renderToString(createSSRApp(Tile, { code: '9m' }))
    assert.match(wan, /suit-m/)
    assert.doesNotMatch(wan, /data-artwork/)
  } finally { await vite.close() }
})

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
    assertGraphicalSuits(html)
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
    assertGraphicalSuits(html)
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
    assertGraphicalSuits(html)
  } finally { await vite.close() }
})
