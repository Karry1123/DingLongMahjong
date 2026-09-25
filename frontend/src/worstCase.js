import { createApp, h, nextTick, ref } from 'vue'
import './style.css'
import PvEBoard from './components/PvEBoard.vue'
import PlayerWorkbench from './components/PlayerWorkbench.vue'
import HandBar from './components/HandBar.vue'
import MeldBar from './components/MeldBar.vue'
import DiscardRiver from './components/DiscardRiver.vue'
import ResultCard from './components/ResultCard.vue'

// Visual stress fixture only. It deliberately ignores the physical tile-count limit.
const tileCodes = ['1m', '2m', '3m', '4m', '5m', '6m', '7m', '8m', '9m', '1p', '2p', '3p', '4p', '5p', '6p', '7p', '8p', '9p', '1s', '2s', '3s', '4s', '5s', '6s']
const fullRiver = [...tileCodes]
const melds = ['1m', '4p', '7s', 'C'].map((tile) => ({ meld_type: 'ming_gang', tiles: Array(4).fill(tile) }))
const opponents = ['N', 'W', 'S'].map((seat_wind) => ({ seat_wind, hand_tiles: ['P'], melds, discards: fullRiver }))
const fullHand = ['1m', '1m', '2m', '3m', '4m', '4p', '5p', '4p', '6p', '7p', '2s', '3s', 'E', 'N']
const candidates = ['N', 'E', '4p'].map((tile, index) => ({
  tile, ev_score: 89.8 - index * 15, attack_ev: 100 - index * 10,
  defense_loss: 10.2 + index * 5, effective_count: 8 - index,
  est_final_points: 32, deal_in_risks: { N: 0.02, W: 0.03, S: 0.04 },
}))
const turn = ref(15)
window.__setWorstCaseTurn = async (value) => {
  turn.value = Math.max(0, Math.min(15, Number(value) || 0))
  await nextTick()
  return turn.value
}

createApp({
  render() {
    const n = turn.value
    const meldCount = Math.min(4, Math.floor(n / 3))
    const river = fullRiver.slice(0, Math.min(24, Math.ceil(n * 24 / 15)))
    const shownMelds = melds.slice(0, meldCount)
    const shownOpponents = opponents.map((opponent) => ({
      ...opponent,
      hand_tiles: Array(Math.max(1, 13 - meldCount * 3)).fill('P'),
      melds: shownMelds,
      discards: river,
    }))
    return h('div', { class: 'pve-portrait-shell min-h-screen bg-gradient-to-br from-emerald-950 via-teal-900 to-slate-900 px-4 py-8' }, [
      h('div', { class: 'pve-session-view' }, [
        h('main', { class: 'pve-game-main mx-auto flex max-w-7xl flex-col gap-6', 'aria-label': '极端流局布局沙盒', 'data-turn': n }, [
          h('section', { class: 'rounded-2xl border border-amber-400/40 bg-teal-950 p-4 text-amber-100', 'aria-label': '轮次状态' }, [
            h('div', { class: 'flex flex-wrap items-center justify-between gap-2' }, [
              h('span', `第 ${n} 巡 · 庄家 自家`),
              h('span', '累计积分：自家 0 · 下家 0 · 对家 0 · 上家 0'),
              h('button', { type: 'button' }, '音效'),
            ]),
          ]),
          h(PvEBoard, { seatWind: 'E', dealerSeat: 'E', currentTurnSeat: 'E', dealerTile: '8s', wallCount: Math.max(0, 60 - n * 4), roundCount: 4, opponents: shownOpponents }),
          h(PlayerWorkbench, { pve: true }, {
            default: () => [
              h(HandBar, { class: 'pve-self-hand', modelValue: fullHand, capacity: 14, wallDriven: true, discardMode: true, dealerTile: '8s' }),
              h(MeldBar, { modelValue: shownMelds, readOnly: true, compact: true, dealerTile: '8s' }),
              h('div', { class: 'rounded-xl border border-teal-700/40 p-2.5', 'aria-label': '自家牌河' }, [
                h('p', '自家牌河'),
                h(DiscardRiver, { tiles: river, compact: true, layout: 'self' }),
              ]),
            ],
            recommendation: () => n === 0
              ? h('section', { class: 'pve-ev-placeholder rounded-xl border border-amber-400/40 bg-teal-950', 'aria-label': '等待切牌推荐' }, '等待切牌推荐')
              : h(ResultCard, { bestTile: 'N', candidates: candidates.slice(0, 1 + n % 3), loading: n % 5 === 0, compact: true, interactive: true, seatWind: 'E' }),
          }),
        ]),
      ]),
    ])
  },
}).mount('#app')
