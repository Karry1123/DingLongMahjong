import assert from 'node:assert/strict'
import { test } from 'node:test'
import { createServer } from 'vite'
import { createRenderer, ssrContextKey } from 'vue'
import { useGameSession } from '../src/composables/useGameSession.js'
import { northDiscardDeal } from './pveFixture.js'

test('HandBar waiting clicks never remove tiles; setup removes and discard emits', async () => {
  const vite = await createServer({ server: { middlewareMode: true, hmr: false }, appType: 'custom' })
  try {
    const HandBar = (await vite.ssrLoadModule('/src/components/HandBar.vue')).default
    const renderer = createRenderer({
      createComment: () => ({}), insert() {}, remove() {}, parentNode() {}, nextSibling() {},
    })
    for (const [setupMode, discardMode, disabled, expected] of [
      [false, false, false, []], [false, true, true, []],
      [true, false, false, ['update:modelValue']], [false, true, false, ['discard-tile']],
    ]) {
      const events = []
      const app = renderer.createApp({ ...HandBar, render: () => null }, {
        modelValue: ['1m', '2m'], setupMode, discardMode, disabled,
        'onUpdate:modelValue': () => events.push('update:modelValue'),
        onDiscardTile: () => events.push('discard-tile'),
      })
      app.provide(ssrContextKey, {})
      const instance = app.mount({})
      instance.$.setupState.handleTileClick({ code: '1m', index: 0 })
      assert.deepEqual(events, expected)
      if (!setupMode && (!discardMode || disabled)) {
        const state = instance.$.setupState
        assert.equal(state.canDragTile('1m'), false)
        state.emitMoveJoker(0, 1)
        state.onTilePointerDown({ button: 0, pointerId: 1 }, { code: '1m', index: 0 })
        assert.equal(state.pointerDrag, null)
        let prevented = false
        state.onDragStart({ preventDefault() { prevented = true } }, { code: '1m', index: 0 })
        assert.equal(prevented, true)
        assert.deepEqual(events, [])
      }
      app.unmount()
    }
  } finally { await vite.close() }
})

test('session rejects every off-phase self discard without mutation or request', async () => {
  const originalFetch = globalThis.fetch
  let requests = 0
  globalThis.fetch = async () => { requests++; return { ok: true, json: async () => ({ action_phase: 'WAIT' }) } }
  try {
    const s = useGameSession()
    s.gameState.value = 'PLAYING'
    s.tableLocked.value = true
    s.roundState.handTiles = northDiscardDeal().hands.E
    for (const phase of ['WAITING', 'WAIT_RESPONSE', 'OPPONENT_DISCARD_ACTION', 'IDLE']) {
      s.currentTurnSeat.value = s.roundState.seatWind
      s.currentPhase.value = phase
      const before = [...s.roundState.handTiles]
      await s.discardTile(before[0], 0)
      assert.deepEqual(s.roundState.handTiles, before)
      assert.deepEqual(s.roundState.discards, [])
      assert.equal(s.loading.value, false)
    }
    s.currentPhase.value = 'MY_TURN_DISCARD'
    s.currentTurnSeat.value = 'S'
    await s.discardTile(s.roundState.handTiles[0], 0)
    assert.equal(s.roundState.handTiles.length, 14)
    assert.equal(requests, 0)
  } finally { globalThis.fetch = originalFetch }
})

test('rapid discard is locked during request and remains locked before the next draw', async () => {
  const originalFetch = globalThis.fetch
  let release, discardRequests = 0
  globalThis.fetch = async (url, options) => {
    if (String(url).endsWith('/auto-deal')) return { ok: true, json: async () => northDiscardDeal() }
    const payload = JSON.parse(options.body)
    if (payload.event?.event_type === 'DISCARD') {
      discardRequests++
      assert.equal(payload.current_turn_seat, 'E')
      assert.equal(payload.current_phase, 'DISCARD')
      assert.equal(payload.response_pending, false)
      await new Promise(resolve => { release = resolve })
    }
    return { ok: true, json: async () => ({ action_phase: 'WAIT', need_self_action: false }) }
  }
  try {
    const s = useGameSession()
    await s.startPveGame()
    assert.equal(s.canDiscard.value, true)
    const first = s.discardTile('N', s.roundState.handTiles.indexOf('N'))
    try {
      assert.equal(s.loading.value, true)
      assert.equal(s.canDiscard.value, false)
      await s.discardTile(s.roundState.handTiles[0], 0)
      assert.equal(discardRequests, 1)
      assert.equal(s.roundState.handTiles.length, 13)
    } finally { release(); await first }
    await s.discardTile(s.roundState.handTiles[0], 0)
    assert.equal(discardRequests, 1)
    assert.equal(s.roundState.handTiles.length, 13)
    assert.equal(s.canDiscard.value, false)
  } finally { globalThis.fetch = originalFetch }
})
