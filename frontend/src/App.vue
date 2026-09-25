<script setup>
/**
 * 牌局闭环整合（SETUP 录入 → PLAYING 串行）：
 * 1) SETUP：自由录入 13/14 起手；HandBar 点击=移除；TilePicker 激活
 * 2) 开始对局 → 理牌 → PLAYING；庄家切牌 / 闲家等东
 * 3) 对手回合：OpponentPanel → opponentDiscardTile
 * 4) 吃碰 → takeTurnAfterMeld；过/胡后 → passCall / advanceTurnToNext
 */
import { computed, ref, watch, nextTick, onUnmounted } from 'vue'
import GameConfig from './components/GameConfig.vue'
import DiscardPool from './components/DiscardPool.vue'
import HandBar from './components/HandBar.vue'
import MeldBar from './components/MeldBar.vue'
import OpponentPanel from './components/OpponentPanel.vue'
import ResultCard from './components/ResultCard.vue'
import PvEDiscardHud from './components/PvEDiscardHud.vue'
import ActionPrompt from './components/ActionPrompt.vue'
import TilePicker from './components/TilePicker.vue'
import SelfWinBanner from './components/SelfWinBanner.vue'
import GameOverModal from './components/GameOverModal.vue'
import GodViewTable from './components/GodViewTable.vue'
import PvEBoard from './components/PvEBoard.vue'
import DiscardRiver from './components/DiscardRiver.vue'
import PlayerWorkbench from './components/PlayerWorkbench.vue'
import { usePvEAutomation } from './composables/usePvEAutomation.js'
import PvECircleSummary from './components/PvECircleSummary.vue'
import PveStartDialog from './components/PveStartDialog.vue'
import { useGameSession } from './composables/useGameSession.js'
import { cloudWakeMessage, getRecommendDecision, getOpponentThreats, isAbortError } from './services/api.js'
import { relativeOpponents, tileLabel } from './constants/tiles.js'
import { DEALER_SEAT, windLabel } from './utils/seatLayout.js'
import { createSoundEngine } from './utils/soundEngine.js'
import appInfo from '../package.json'

const appVersion = `v${appInfo.version}`

// ---------------------------------------------------------------------------
// 会话状态（单一真相源）
// ---------------------------------------------------------------------------

const soundEngine = createSoundEngine()
const soundMuted = ref(false)
const soundVolume = ref(70)
watch([soundMuted, soundVolume], () => {
  soundEngine.setVolume(soundVolume.value / 100)
  soundEngine.setMuted(soundMuted.value)
}, { immediate: true })
onUnmounted(() => soundEngine.stop(true))
const session = useGameSession({ onAction: soundEngine.playAction })
const {
  roundState,
  currentPhase,
  currentTurnSeat,
  lastDiscardSeat,
  lastStepResult,
  latestDrawnTile,
  autoSortEnabled,
  gameState,
  targetInitialCount,
  canStartPlaying,
  isSetup,
  isPlaying,
  isGameOver,
  loading: stepLoading,
  errorMsg: sessionError,
  phaseLabel,
  isSelfTurn,
  canUndo,
  historyDepth,
  dispatchStep,
  undoLastStep,
  resetGame,
  resetInProgress,
  startPlaying,
  reopenTable,
  clearSetupHand,
  setSeatWind,
  validateRoundState,
  toHandRequestPayload,
  enterSelfDiscardPhase,
  acknowledgeHu,
  declareSelfWin,
  declareSelfRon,
  declareOpponentWin,
  declareDraw,
  startNewRoundAfterWin,
  startNextRound,
  startPveGame,
  continuePveCircle,
  exitPveGame,
  gameMode,
  dealerPlayerId,
  dealerSeat,
  roundCount,
  showGameOverModal,
  showRoundSummaryModal,
  pveRoundOverPending,
  selfWinSettlement,
  gameRoundId,
  cumulativeScores,
  roundHistory,
  applyHandSort,
  manualSortHand,
  discardTile,
  selfDrawTile,
  opponentDiscardTile,
  passCall,
  passAllCalls,
  isResponseWindow,
  catchWinSeats,
  pendingHuQueue,
  currentHuSeat,
  applySelfMeld,
  applySelfKong,
  executeOpponentMeld,
  executeOpponentAnGang,
  wallTiles,
  applyAutoDeal,
  discardFromGodView,
  setPendingSelfRecommend,
  latestDrawnBySeat,
  recommendDrawToken,
  moveJokerInHand,
  handLayoutPinned,
  abortCurrentRecommend,
  beginRecommendFetch,
  clearRecommendAbortController,
  currentRecommendAbortController,
} = session

const activeUiMode = ref('')
const pveStartLoading = ref(false)
const pveConfigOpen = ref(false)
const enableEV = ref(true)
function openPveConfig() {
  try { enableEV.value = JSON.parse(sessionStorage.getItem('pveConfig') || '{}').enableEV !== false } catch { enableEV.value = true }
  pveConfigOpen.value = true
}
const { status: aiStatus, announcement: aiAnnouncement, thinkingSeat: aiThinkingSeat, busy: aiActionBusy, error: aiError, retry: retryAI } = usePvEAutomation(session)

async function choosePveMode() {
  if (pveStartLoading.value) return
  try { sessionStorage.setItem('pveConfig', JSON.stringify({ enableEV: enableEV.value, aiStyle: 'balanced' })) } catch { /* private browsing */ }
  pveStartLoading.value = true
  analyzeError.value = ''
  try {
    if (!soundMuted.value) soundEngine.unlock()
    await startPveGame()
    activeUiMode.value = 'PVE'
    pveConfigOpen.value = false
  } catch (e) {
    analyzeError.value = e?.message || String(e)
  } finally {
    pveStartLoading.value = false
  }
}

function chooseSandboxMode() { activeUiMode.value = 'SANDBOX' }

function returnHome() {
  soundEngine.stop()
  void onExitPve()
}

/** v-model 代理 → 各录入组件仍写 roundState */
const handTiles = computed({
  get: () => roundState.handTiles,
  set: (v) => {
    roundState.handTiles = v
  },
})
const melds = computed({
  get: () => roundState.melds,
  set: (v) => {
    roundState.melds = v
  },
})
const selfDiscards = computed({
  get: () => roundState.discards,
  set: (v) => {
    roundState.discards = v
  },
})
const opponents = computed({
  get: () => roundState.opponents,
  set: (v) => {
    roundState.opponents = v
  },
})
const dealerTile = computed({
  get: () => roundState.dealerTile,
  set: (v) => {
    roundState.dealerTile = v
  },
})
/** 庄闲只读：由门风推导（东=庄） */
const isDealer = computed(() => roundState.isDealer)
const pveLeaderboard = computed(() => {
  const relativeSeats = relativeOpponents(roundState.seatWind)
  const seatsInViewOrder = [
    { role: '自家', seat_wind: roundState.seatWind },
    relativeSeats.find(({ role }) => role === '下家'),
    relativeSeats.find(({ role }) => role === '对家'),
    relativeSeats.find(({ role }) => role === '上家'),
  ].filter(Boolean)
  return seatsInViewOrder.map(({ role, seat_wind }) => ({
    role,
    score: Number(cumulativeScores.value?.[seat_wind] || 0),
  }))
})

const pvePlayerRoleById = ['自家', '下家', '对家', '上家']
const signedScore = (score) => `${score > 0 ? '+' : ''}${score}`

const seatWind = computed({
  get: () => roundState.seatWind,
  set: (v) => setSeatWind(v),
})

/** 步进未带 recommend 时的本地补算结果 */
const localRecommend = ref(null)
const analyzeLoading = ref(false)
const analyzeError = ref('')
/** 防止同一局面重复打 /api/recommend */
const recommendFetchKey = ref('')

/**
 * 仅牌局步进/切牌等同步动作占用（不含 EV 推演）。
 * EV 计算中手牌仍可点，由 analyzeLoading / isCalculatingEV 单独表达。
 */
const loading = computed(() => stepLoading.value)
/** 后台 /api/recommend 是否进行中（不禁用手牌） */
const isCalculatingEV = analyzeLoading
const errorMsg = computed(() => sessionError.value || aiError.value || analyzeError.value)

// ---------------------------------------------------------------------------
// 容量 / 全场牌池（TilePicker 实时同步）
// ---------------------------------------------------------------------------

/** 待切手牌张数：14 − 3×副露（切牌推荐唯一容量公式） */
const requiredHandCount = computed(() => 14 - melds.value.length * 3)
/** 待摸张数：13 − 3×副露 */
const requiredWaitCount = computed(() => 13 - melds.value.length * 3)

/** HandBar / 录入槽位容量：SETUP 用起手目标，PLAYING 用切牌容量 */
const handCapacity = computed(() =>
  isSetup.value ? targetInitialCount.value : requiredHandCount.value,
)

/** 待摸/响应时键盘上限 */
const pickerMaxCount = computed(() => {
  const slots = handTiles.value.length + 3 * melds.value.length
  if (slots >= 14) return requiredHandCount.value
  return Math.max(0, requiredWaitCount.value)
})

const handCount = computed(() => handTiles.value.length)
/** 暗手 + 3×副露 == 14 → 允许切牌 / 请求 recommend */
const isHandReadyToDiscard = computed(
  () =>
    handCount.value + 3 * melds.value.length === 14 &&
    requiredHandCount.value > 0,
)
const handFullForDiscard = computed(() => isHandReadyToDiscard.value)
const hasHand = computed(() => handCount.value > 0)
const setupHandFull = computed(
  () => handCount.value === targetInitialCount.value,
)

const opponentOccupiedTiles = computed(() => {
  const out = []
  for (const o of opponents.value) {
    for (const t of o.discards || []) out.push(t)
    for (const m of o.melds || []) {
      for (const t of m.tiles || []) out.push(t)
    }
  }
  return out
})

/**
 * TilePicker 占用：副露+四家牌河+财神（不含暗手，暗手由组件内另计）
 * 随 dispatchStep 回写的 updated_state 自动刷新剩余张数
 */
const tilePickerOccupied = computed(() => [
  ...melds.value.flatMap((m) => m.tiles || []),
  ...selfDiscards.value,
  ...opponentOccupiedTiles.value,
  dealerTile.value,
])

const opponentBaseOccupied = computed(() => [
  ...handTiles.value,
  ...melds.value.flatMap((m) => m.tiles || []),
  ...selfDiscards.value,
  dealerTile.value,
])

const meldBarExtra = computed(() => [
  ...opponentOccupiedTiles.value,
  dealerTile.value,
])

const discardPoolExtra = computed(() => [
  ...melds.value.flatMap((m) => m.tiles || []),
  ...opponentOccupiedTiles.value,
])

// ---------------------------------------------------------------------------
// 阶段派生
// ---------------------------------------------------------------------------

/** 已进入 PLAYING */
const livePlay = computed(() => isPlaying.value)

const callDecision = computed(() => lastStepResult.value?.call_decision ?? null)

const pveResponseDecision = computed(() => {
  if (gameMode.value !== 'PVE' || currentHuSeat.value || !isResponseWindow.value) return null
  const option = (lastStepResult.value?._table_responses || []).find((row) => row.seat === seatWind.value)
  if (!option) return null
  const provider = lastDiscardSeat.value || ''
  const providerState = provider === seatWind.value
    ? { discards: roundState.discards }
    : roundState.opponents.find((o) => o.seat_wind === provider)
  const tile = lastStepResult.value?._response_tile || providerState?.discards?.at(-1) || ''
  const actions = []
  if (option.types?.includes('chi')) for (const combo of option.chiCombos || []) actions.push({ action_type: 'chi', tiles: combo, provider_seat: provider })
  if (option.types?.includes('pong')) actions.push({ action_type: 'pong', tiles: [tile, tile, tile], provider_seat: provider })
  if (option.types?.includes('ming_gang')) actions.push({ action_type: 'ming_gang', tiles: [tile, tile, tile, tile], provider_seat: provider })
  if (!actions.length) return null
  actions.push({ action_type: 'pass', tiles: [tile], provider_seat: provider })
  return { recommended_action: actions[0], available_actions: actions, candidates: [], reason: '本地合法副露选项' }
})
const activeCallDecision = computed(() => callDecision.value || pveResponseDecision.value)

const callProviderSeat = computed(() => {
  if (isResponseWindow.value && lastDiscardSeat.value) return lastDiscardSeat.value
  const a = activeCallDecision.value?.recommended_action
  if (a?.provider_seat) return a.provider_seat
  for (const c of activeCallDecision.value?.candidates || []) {
    if (c.action?.provider_seat) return c.action.provider_seat
  }
  return ''
})

const callDiscardedTile = computed(() => {
  const cd = activeCallDecision.value
  if (!cd) return ''
  if (isResponseWindow.value && lastStepResult.value?._response_tile) return lastStepResult.value._response_tile
  // 出牌方牌河末张最可靠（吃/碰/杠均适用）
  const seat =
    cd.recommended_action?.provider_seat ||
    callProviderSeat.value ||
    lastDiscardSeat.value
  if (seat) {
    const opp = roundState.opponents.find((o) => o.seat_wind === seat)
    if (opp?.discards?.length) {
      return opp.discards[opp.discards.length - 1]
    }
  }
  for (const c of cd.candidates || []) {
    const t = c.action?.action_type
    const tiles = c.action?.tiles || []
    if (t === 'hu' && tiles[0]) return tiles[0]
    if ((t === 'pong' || t === 'ming_gang') && tiles[0]) return tiles[0]
    // 吃：面子含上家打出张，用牌河末张已优先；兜底取 recommended
  }
  const rec = cd.recommended_action
  if (rec?.action_type === 'chi' && seat) {
    const opp = roundState.opponents.find((o) => o.seat_wind === seat)
    if (opp?.discards?.length) return opp.discards[opp.discards.length - 1]
  }
  return ''
})

/** 代录对手副露用：最近出牌张（有 CALL 时优先 callDiscardedTile） */
const lastDiscardedTileForClaim = computed(() => {
  if (lastStepResult.value?._pending_add_kong) return lastStepResult.value._response_tile || ''
  if (callDiscardedTile.value) return callDiscardedTile.value
  const seat = lastDiscardSeat.value
  if (!seat) return ''
  if (seat === roundState.seatWind) {
    const river = roundState.discards || []
    return river.length ? river[river.length - 1] : ''
  }
  const opp = roundState.opponents.find((o) => o.seat_wind === seat)
  return opp?.discards?.length ? opp.discards[opp.discards.length - 1] : ''
})

/** 仅当后端明确要求自家响应时呼出 ActionPrompt */
const showActionPrompt = computed(
  () =>
    (currentPhase.value === 'OPPONENT_DISCARD_ACTION' ||
      (gameMode.value === 'PVE' && currentPhase.value === 'WAIT_RESPONSE' && !!pveResponseDecision.value)) &&
    !!activeCallDecision.value &&
    (!!lastStepResult.value?.need_self_action || !!pveResponseDecision.value),
)

/** 出牌后副露响应窗（含仅对手可吃碰、或自家 CALL） */
const responseWindowOpen = computed(() => !!isResponseWindow.value)

/** 响应窗内禁止摸切推进 */
const callOrResponsePending = computed(
  () => showActionPrompt.value || responseWindowOpen.value,
)

async function onPassAllCalls() {
  if (loading.value || !lastDiscardSeat.value) return
  try {
    await passAllCalls(lastDiscardedTileForClaim.value || null)
    localRecommend.value = null
    recommendFetchKey.value = ''
  } catch (e) {
    analyzeError.value = e?.message || String(e)
  }
}

/** 自家行动权且进入切牌阶段 */
const isMyDiscardTurn = computed(
  () =>
    isSelfTurn.value &&
    currentPhase.value === 'MY_TURN_DISCARD' &&
    !showActionPrompt.value,
)

/** 暗手已满且轮到自家 → 点击即切牌（容量 = 14-3×副露，绝非写死 14） */
const handReadyToDiscard = computed(
  () =>
    isSelfTurn.value &&
    isHandReadyToDiscard.value &&
    currentPhase.value !== 'OPPONENT_DISCARD_ACTION',
)

const decisionDockPhase = computed(() => {
  if (showActionPrompt.value) return 'call'
  if (responseWindowOpen.value) return 'wait'
  return isMyDiscardTurn.value || handReadyToDiscard.value ? 'discard' : 'wait'
})

/** 切牌推荐：待切（阶段或手牌已满）时展示；优先本地最新摸牌后的补算 */
const displayRecommend = computed(() => {
  if (!isMyDiscardTurn.value && !handReadyToDiscard.value) return null
  // 刚摸入后以 localRecommend 为准（避免步进里旧 recommend 挡住）
  if (latestDrawnTile.value && localRecommend.value?.best_tile) {
    return localRecommend.value
  }
  const fromStep = lastStepResult.value?.recommend_discard
  if (fromStep?.best_tile && !latestDrawnTile.value) return fromStep
  return localRecommend.value || fromStep || null
})

const bestDiscardTile = computed(
  () => displayRecommend.value?.best_tile || '',
)

const selfGangCandidates = computed(
  () => displayRecommend.value?.self_gang_candidates || [],
)

/** 自摸提醒：来自推荐或 step；用户可 dismiss 后继续切牌 */
const selfWinDismissed = ref(false)
const selfWinInfo = computed(() => {
  const fromRec = displayRecommend.value?.self_win_info
  if (fromRec) return fromRec
  return lastStepResult.value?.self_win_info || null
})
const canSelfWin = computed(() => {
  if (selfWinDismissed.value || isGameOver.value) return false
  if (!(handReadyToDiscard.value || isMyDiscardTurn.value)) return false
  return !!(
    displayRecommend.value?.can_self_win ||
    lastStepResult.value?.can_self_win ||
    selfWinInfo.value?.is_win
  )
})

watch(
  () =>
    [
      roundState.handTiles.join(','),
      roundState.melds.length,
      latestDrawnTile.value,
    ].join('#'),
  () => {
    selfWinDismissed.value = false
  },
)

const canStartDiscardTurn = computed(
  () =>
    isPlaying.value &&
    isSelfTurn.value &&
    handFullForDiscard.value &&
    !loading.value &&
    currentPhase.value !== 'OPPONENT_DISCARD_ACTION' &&
    currentPhase.value !== 'MY_TURN_DISCARD',
)

const canSelfDraw = computed(() => {
  if (!isPlaying.value || !isSelfTurn.value) return false
  if (currentPhase.value === 'OPPONENT_DISCARD_ACTION') return false
  // 待摸：hand + 3*melds === 13（含杠后岭上补牌）
  const slots = handTiles.value.length + 3 * melds.value.length
  return slots === 13 && !loading.value
})

/** TilePicker 上限：SETUP=起手目标；PLAYING 摸牌=+1 */
const setupPickerMax = computed(() => {
  if (isSetup.value) return targetInitialCount.value
  if (canSelfDraw.value) return handTiles.value.length + 1
  return pickerMaxCount.value
})

/** SETUP 始终可点选；PLAYING 仅自家待摸时可点 */
const tilePickerEnabled = computed(
  () => isSetup.value || canSelfDraw.value,
)

// ---------------------------------------------------------------------------
// 顶部轮次状态条（Turn StatusBar）
// ---------------------------------------------------------------------------

/** 座次 → 上家/对家/下家/自家 */
const seatRoleMap = computed(() => {
  const map = Object.create(null)
  map[roundState.seatWind] = '自家'
  for (const { role, seat_wind } of relativeOpponents(roundState.seatWind)) {
    map[seat_wind] = role
  }
  return map
})

const opponentThreats = ref([])
let threatTimer = null
let threatRequest = null
watch(() => JSON.stringify({
  mode: gameMode.value, playing: isPlaying.value, dealer: roundState.dealerTile,
  wall: wallTiles.value.length,
  opponents: roundState.opponents.map((o) => ({ seat_wind: o.seat_wind,
    is_dealer: o.is_dealer, melds: o.melds, discards: o.discards })),
}), () => {
  clearTimeout(threatTimer)
  threatRequest?.abort()
  opponentThreats.value = []
  if (gameMode.value !== 'PVE' || !isPlaying.value) { opponentThreats.value = []; return }
  threatTimer = setTimeout(async () => {
    const controller = new AbortController()
    threatRequest = controller
    try {
      const result = await getOpponentThreats({ dealer_tile: roundState.dealerTile,
        wall_count: wallTiles.value.length,
        opponents: roundState.opponents.map((o) => ({ seat_wind: o.seat_wind,
          is_dealer: !!o.is_dealer,
          melds: o.melds || [], discards: o.discards || [] })) }, { signal: controller.signal })
      if (!controller.signal.aborted) opponentThreats.value = result.threats || []
    } catch (error) {
      if (!isAbortError(error)) console.warn('[opponent-threats]', error)
    }
  }, 150)
}, { immediate: true })
onUnmounted(() => { clearTimeout(threatTimer); threatRequest?.abort() })

const opponentWarning = computed(() => {
  if (wallTiles.value.length > 55) {
    return { level: 'safe', text: '三家 AI 摸打思考中… 当前局势平稳' }
  }
  if (wallTiles.value.length <= 25 && isPlaying.value) {
    return { level: 'high', text: '局势进入尾盘，提防点铳，建议跟切熟张' }
  }
  const ranked = [...opponentThreats.value].sort((a, b) =>
    ({ high: 2, warn: 1, safe: 0 })[b.level] - ({ high: 2, warn: 1, safe: 0 })[a.level]
    || b.probability - a.probability)
  const threat = ranked[0]
  if (!threat || threat.level === 'safe') return { level: 'safe', text: '三家 AI 摸打思考中… 当前局势平稳' }
  const who = `${seatRoleMap.value[threat.seat_wind] || '对手'}·${windLabel(threat.seat_wind)}风`
  if (threat.meld_count >= 3) return { level: 'warn', text: `注意：${who} 已三副露，注意防守！` }
  return { level: 'warn', text: `注意：${who} 已多组副露，注意防守！` }
})

/**
 * @param {string} seat
 * @returns {string} 如「上家/东风/庄家」或「自家/南风」
 */
function formatActorLabel(seat) {
  if (!seat) return '—'
  const role = seatRoleMap.value[seat] || ''
  const wind = `${windLabel(seat)}风`
  const parts = [role, wind]
  if (seat === dealerSeat.value) parts.push('庄家')
  return parts.filter(Boolean).join('/')
}

/** 全场已出张数 → 巡目（四方各打 1 张为一巡） */
const totalDiscardCount = computed(() => {
  let n = roundState.discards?.length || 0
  for (const o of roundState.opponents || []) {
    n += o.discards?.length || 0
  }
  return n
})

const turnCount = computed(() => Math.floor(totalDiscardCount.value / 4) + 1)

const handInRound = computed(() => (totalDiscardCount.value % 4) + 1)

/**
 * 状态条模式：call | self | opponent | idle
 * @type {import('vue').ComputedRef<{
 *   mode: 'call'|'self'|'opponent'|'idle'|'setup',
 *   tone: 'rose'|'emerald'|'amber'|'slate',
 *   emoji: string,
 *   headline: string,
 *   detail: string,
 * }>}
 */
const turnStatus = computed(() => {
  if (gameMode.value === 'PVE') {
    const responding = isResponseWindow.value
    return {
      tone: responding ? 'rose' : isSelfTurn.value ? 'emerald' : 'amber',
      emoji: responding ? '🔴' : '🟢',
      headline: responding ? '等待副露响应' : isSelfTurn.value ? '轮到自家出牌' : `${formatActorLabel(currentTurnSeat.value)}行动中`,
      detail: showActionPrompt.value ? '请选择吃、碰、杠、和或过牌' : aiStatus.value || '点击手牌或右侧 EV 推荐切牌；摸牌由牌墙自动完成',
    }
  }
  if (isSetup.value) {
    const need = targetInitialCount.value
    const n = handCount.value
    const role = roundState.isDealer ? '庄家' : '闲家'
    return {
      mode: 'setup',
      tone: setupHandFull.value ? 'emerald' : 'slate',
      emoji: setupHandFull.value ? '🟢' : '⚪',
      headline: setupHandFull.value
        ? `起手已满 ${need} 张（${role}）· 可开始对局`
        : `开局准备：录入起手 ${n}/${need}（${role}）`,
      detail: setupHandFull.value
        ? '点击「开始对局」自动理牌并进入时序'
        : '用下方选牌键盘点选；HandBar 点击可移除单张',
    }
  }

  if (showActionPrompt.value) {
    const provider =
      callProviderSeat.value || lastDiscardSeat.value || currentTurnSeat.value
    const tile = callDiscardedTile.value
    const who = formatActorLabel(provider)
    return {
      mode: 'call',
      tone: 'rose',
      emoji: '🔴',
      headline: `${who} 打出 ${tile ? tileLabel(tile) : '—'}，请选择响应动作`,
      detail:
        '自家吃/碰/杠/胡/过 · 亦可在上方对手卡片代录其余家吃碰杠（将打断时序）',
    }
  }

  // 对手副露/暗杠后：lastDiscardSeat 已清空，仍需提示录入切牌
  if (
    isPlaying.value &&
    !isSelfTurn.value &&
    !showActionPrompt.value &&
    (lastStepResult.value?.note?.includes('副露成功') ||
      lastStepResult.value?.note?.includes('宣告暗杠'))
  ) {
    const who = formatActorLabel(currentTurnSeat.value)
    const isAnGangNote = lastStepResult.value?.note?.includes('宣告暗杠')
    return {
      mode: 'opp-meld',
      tone: 'amber',
      emoji: '🟠',
      headline: isAnGangNote
        ? `${who} 宣告暗杠，正在补牌，请录入其切出的牌`
        : `${who} 副露成功，请录入其切出的牌`,
      detail: '在对手卡片键盘点选 1 张打出 · 可撤销回退',
    }
  }

  if (isPlaying.value && lastDiscardedTileForClaim && lastDiscardSeat.value) {
    const provider = lastDiscardSeat.value
    const tile = lastDiscardedTileForClaim
    if (
      !showActionPrompt.value &&
      !isSelfTurn.value &&
      currentTurnSeat.value !== provider
    ) {
      // 下家待摸/待打，仍可代录响应
      const who = formatActorLabel(provider)
      return {
        mode: 'claim-window',
        tone: 'amber',
        emoji: '🟡',
        headline: `${who} 打出 ${tileLabel(tile)} · 可代录其余家吃碰杠`,
        detail: `或轮到 ${formatActorLabel(currentTurnSeat.value)} 出牌`,
      }
    }
  }

  if (isSelfTurn.value) {
    const who = formatActorLabel(roundState.seatWind)
    if (canSelfDraw.value) {
      const need = requiredHandCount.value
      const wait = requiredWaitCount.value
      return {
        mode: 'self',
        tone: 'emerald',
        emoji: '🟢',
        headline: `轮到 [${who}] 摸牌（${handCount.value}/${wait} → 切牌目标 ${need}）`,
        detail:
          lastStepResult.value?.action_phase === 'DRAW'
            ? '杠牌成功：请录入岭上补牌 1 张，随后进入切牌推荐'
            : `在选牌键盘点 1 张摸入（副露 ${melds.value.length} 组，切牌需 ${need} 张暗手）`,
      }
    }
    const tip = bestDiscardTile.value
      ? `推荐打出 [${tileLabel(bestDiscardTile.value)}]`
      : '点击手牌切出 1 张'
    return {
      mode: 'self',
      tone: 'emerald',
      emoji: '🟢',
      headline: `轮到 [${who}] 切牌：${tip}`,
      detail: '仅自家手牌可点；其余面板已降透防误触',
    }
  }

  const who = formatActorLabel(currentTurnSeat.value)
  return {
    mode: 'opponent',
    tone: 'amber',
    emoji: '🟡',
    headline: `轮到 [${who}] 出牌`,
    detail: '请在其面板选牌键盘打出 1 张（不可任意添加弃牌）',
  }
})

const statusBarToneClass = computed(() => {
  const t = turnStatus.value.tone
  if (t === 'rose') {
    return 'border-rose-500/50 bg-rose-950/45 shadow-rose-950/30'
  }
  if (t === 'emerald') {
    return 'border-emerald-500/50 bg-emerald-950/50 shadow-emerald-950/25'
  }
  if (t === 'amber') {
    return 'border-amber-500/45 bg-amber-950/40 shadow-amber-950/25'
  }
  return 'border-teal-700/40 bg-teal-950/45'
})

/** 自家手牌区是否处于行动聚焦 */
const selfPanelFocused = computed(
  () =>
    isPlaying.value &&
    isSelfTurn.value &&
    !showActionPrompt.value,
)

// ---------------------------------------------------------------------------
// 自动推荐：摸牌 token（优先）+ 阶段/手牌 watch（兜底）
// ---------------------------------------------------------------------------

/** 摸牌后显式触发：nextTick 保证 14 张已入响应式，再打 /api/recommend */
async function triggerRecommendAsync(reason = 'manual') {
  const slots =
    roundState.handTiles.length + 3 * (roundState.melds?.length || 0)
  const need = 14 - 3 * (roundState.melds?.length || 0)
  console.log('[recommend] trigger', reason, {
    slots,
    need,
    hand: [...roundState.handTiles],
    drawn: latestDrawnTile.value,
    phase: currentPhase.value,
    turn: currentTurnSeat.value,
  })
  if (slots !== 14) {
    console.warn('[recommend] 跳过：slots≠14', slots)
    return null
  }
  if (!isSelfTurn.value || showActionPrompt.value) return null

  const handKey = [
    roundState.handTiles.join(','),
    roundState.melds.length,
    roundState.dealerTile,
    latestDrawnTile.value || '',
  ].join('#')
  if (handKey === recommendFetchKey.value && localRecommend.value?.best_tile) {
    return localRecommend.value
  }
  recommendFetchKey.value = handKey
  console.time('recommend-fetch')
  try {
    await refreshLocalRecommend()
    return localRecommend.value
  } finally {
    console.timeEnd('recommend-fetch')
  }
}

watch(recommendDrawToken, async (token, prev) => {
  if (!token || token === prev) return
  // 等 DOM / 响应式提交完成，避免仍按 13 张拦截
  await nextTick()
  await triggerRecommendAsync('draw-token')
})

watch(
  () =>
    [
      currentPhase.value,
      currentTurnSeat.value,
      latestDrawnTile.value,
      roundState.handTiles.join(','),
      roundState.melds.length,
      roundState.dealerTile,
    ].join('#'),
  async () => {
    if (!isMyDiscardTurn.value && !handReadyToDiscard.value) return
    if (!isHandReadyToDiscard.value) return

    await nextTick()

    const handKey = [
      roundState.handTiles.join(','),
      roundState.melds.length,
      roundState.dealerTile,
      latestDrawnTile.value || '',
    ].join('#')

    const stepRec = lastStepResult.value?.recommend_discard
    if (stepRec?.best_tile && !latestDrawnTile.value) {
      recommendFetchKey.value = handKey
      localRecommend.value = null
      return
    }

    if (handKey === recommendFetchKey.value && localRecommend.value?.best_tile) {
      return
    }
    await triggerRecommendAsync('phase-watch')
  },
)

/** SETUP 才按容量截断；PLAYING 禁止因 capacity 抖动裁切手牌（曾误伤摸牌） */
watch(handCapacity, (cap) => {
  if (!isSetup.value) return
  if (roundState.handTiles.length > cap) {
    roundState.handTiles = roundState.handTiles.slice(0, cap)
  }
})

/** 财神变更 → PLAYING 时重新理牌；SETUP 不强制理牌以免打乱录入顺序 */
watch(
  () => roundState.dealerTile,
  () => {
    if (!roundState.handTiles.length || isSetup.value) return
    applyHandSort({
      force: false,
      keepDrawn: !!latestDrawnTile.value,
    })
  },
)

async function refreshLocalRecommend() {
  const signal = beginRecommendFetch()
  analyzeLoading.value = true
  analyzeError.value = ''
  try {
    const slots =
      roundState.handTiles.length + 3 * (roundState.melds?.length || 0)
    if (slots !== 14) {
      throw new Error(
        `切牌推荐需待切状态：暗手 ${roundState.handTiles.length}/` +
          `${14 - 3 * (roundState.melds?.length || 0)}` +
          `（副露 ${roundState.melds?.length || 0}，slots=${slots}≠14）`,
      )
    }
    validateRoundState()
    const payload = toHandRequestPayload()
    if (latestDrawnTile.value) payload.latest_drawn_tile = latestDrawnTile.value
    console.log('[recommend] POST hand_tiles=', payload.hand_tiles, {
      drawn: latestDrawnTile.value,
      len: payload.hand_tiles?.length,
    })
    for (const o of payload.opponents || []) {
      if (
        Object.keys(o).some((k) =>
          ['hand_tiles', 'handTiles', 'closed_hand'].includes(k),
        )
      ) {
        throw new Error('数据隔离失败：禁止将三家暗手送入 /api/recommend')
      }
    }
    const recommendation = await getRecommendDecision(payload, { signal })
    if (signal.aborted) return
    localRecommend.value = recommendation
    setPendingSelfRecommend(localRecommend.value)
  } catch (e) {
    if (signal.aborted || isAbortError(e)) {
      // 人为切牌 / 新一轮推荐取消：静默，不 Toast、不污染控制台
      return
    }
    localRecommend.value = null
    setPendingSelfRecommend(null)
    analyzeError.value = e?.message || String(e)
    console.warn('[recommend] failed', e)
  } finally {
    clearRecommendAbortController(signal)
    // 仅当没有更新一轮在飞时复位 Loading（避免被替换请求误关）
    if (!currentRecommendAbortController.value) {
      analyzeLoading.value = false
    }
  }
}

// ---------------------------------------------------------------------------
// 交互：摸 / 切 / 对手打出 / 副露响应 / 撤回
// ---------------------------------------------------------------------------

function clearHand() {
  if (loading.value || isPlaying.value) return
  clearSetupHand()
  localRecommend.value = null
  analyzeError.value = ''
}

function onConfirmStart() {
  if (!startPlaying()) return
  localRecommend.value = null
  recommendFetchKey.value = ''
  analyzeError.value = ''
}

async function onAutoDeal() {
  if (loading.value || isPlaying.value) return
  analyzeError.value = ''
  try {
    await applyAutoDeal()
    localRecommend.value = null
    recommendFetchKey.value = ''
  } catch (e) {
    analyzeError.value = e?.message || String(e)
  }
}

/** 上帝视角沙盘：点击当前行动方暗手 → 切出流转 */
async function onGodViewDiscard({ seat_wind, tile, index }) {
  if (stepLoading.value || !isPlaying.value) return
  // 打断 EV（含自家沙盘切牌）
  abortCurrentRecommend()
  analyzeLoading.value = false
  localRecommend.value = null
  recommendFetchKey.value = ''
  setPendingSelfRecommend(null)
  analyzeError.value = ''
  try {
    await discardFromGodView(seat_wind, tile, index)
  } catch (e) {
    analyzeError.value = e?.message || String(e)
  }
}

/** 上帝视角：仅移动「得」插嵌组牌 */
function onGodViewMoveJoker({ seat_wind, fromIndex, toIndex }) {
  try {
    moveJokerInHand(seat_wind, fromIndex, toIndex)
  } catch (e) {
    analyzeError.value = e?.message || String(e)
  }
}

function onReopenTable() {
  reopenTable()
  localRecommend.value = null
  recommendFetchKey.value = ''
  analyzeError.value = ''
}

/** 庄家起手 14 张录入完 → 进入切牌（PLAYING 内） */
function onStartSelfDiscard() {
  if (!canStartDiscardTurn.value) return
  localRecommend.value = null
  recommendFetchKey.value = ''
  enterSelfDiscardPhase()
}

/**
 * TilePicker：
 * - SETUP：直接写入手牌
 * - PLAYING 待摸：走 selfDrawTile（本地先入账，绝不回滚上家出牌）
 */
async function onTilePickerUpdate(nextHand) {
  // 只接受纯字符串牌码列表，过滤 Event / 非字符串脏值
  const cleanHand = (Array.isArray(nextHand) ? nextHand : [])
    .map((t) => (typeof t === 'string' ? t.trim() : null))
    .filter((t) => !!t)

  if (isSetup.value) {
    const capped =
      cleanHand.length > targetInitialCount.value
        ? cleanHand.slice(0, targetInitialCount.value)
        : cleanHand
    roundState.handTiles = capped
    latestDrawnTile.value = null
    return
  }

  if (canSelfDraw.value && cleanHand.length === handTiles.value.length + 1) {
    const drawn = cleanHand[cleanHand.length - 1]
    if (typeof drawn !== 'string') {
      analyzeError.value = '摸入张必须是牌码字符串'
      return
    }
    console.log('[App] selfDraw attempt', {
      drawn,
      handBefore: handTiles.value.length,
      turn: currentTurnSeat.value,
      phase: currentPhase.value,
    })
    try {
      await selfDrawTile(drawn)
      localRecommend.value = null
      recommendFetchKey.value = ''
    } catch (e) {
      analyzeError.value = e?.message || String(e)
      console.warn('[App] selfDraw failed (对手牌河应仍保留)', e)
    }
    return
  }

  if (isPlaying.value) {
    console.warn('[App] ignore TilePicker update outside draw window', {
      nextLen: cleanHand.length,
      handLen: handTiles.value.length,
      canSelfDraw: canSelfDraw.value,
    })
    return
  }
  roundState.handTiles = cleanHand
}

async function onDiscardTile(tile, index) {
  if (isSetup.value) {
    return
  }
  if (!isPlaying.value) {
    analyzeError.value = '请先「开始对局」'
    return
  }
  if (!isSelfTurn.value) {
    analyzeError.value = `当前行动权在 ${currentTurnSeat.value}，尚轮不到自家`
    return
  }
  if (isResponseWindow.value) {
    analyzeError.value = '请先完成吃碰过响应'
    return
  }
  // EV 推演中仍允许切牌：仅拦截真正的步进 loading
  if (!tile || stepLoading.value) return

  // 副露后与自摸后统一：slots===14 即可切
  if (!isHandReadyToDiscard.value) {
    analyzeError.value =
      `非待切状态：暗手 ${handTiles.value.length}/` +
      `${requiredHandCount.value}（副露 ${melds.value.length}）`
    return
  }

  // 最高优先级：打断后台 EV，清空推荐 Loading，立刻切牌推进
  abortCurrentRecommend()
  analyzeLoading.value = false
  localRecommend.value = null
  recommendFetchKey.value = ''
  setPendingSelfRecommend(null)
  analyzeError.value = ''

  try {
    await discardTile(tile, index)
  } catch (e) {
    analyzeError.value = e?.message || String(e)
  }
}

/** ResultCard 确认切出（无 index：同名仅一张时可切） */
async function onSelfDiscardFromRecommend(tile) {
  if (!tile || stepLoading.value) return
  const matches = []
  roundState.handTiles.forEach((t, i) => {
    if (t === tile) matches.push(i)
  })
  if (!matches.length) return
  // 多张同名时优先切摸进张（若匹配），否则第一张
  let index = matches[0]
  if (
    latestDrawnTile.value === tile &&
    roundState.handTiles[roundState.handTiles.length - 1] === tile
  ) {
    index = roundState.handTiles.length - 1
  }
  await onDiscardTile(tile, index)
}

/** 宣布暗杠 / 补杠 → 岭上补牌 */
async function onDeclareSelfKong(gang) {
  if (!gang || loading.value) return
  try {
    await applySelfKong({
      action_type: gang.action_type,
      tile: gang.tile,
      tiles: gang.tiles || [gang.tile, gang.tile, gang.tile, gang.tile],
    })
    localRecommend.value = null
    recommendFetchKey.value = ''
  } catch (e) {
    analyzeError.value = e?.message || String(e)
  }
}

async function onDeclareSelfWin() {
  const info = selfWinInfo.value
  if (!info) {
    analyzeError.value = '无自摸明细'
    return
  }
  try {
    await declareSelfWin(info)
  } catch (e) {
    analyzeError.value = e?.message || String(e)
  }
}

async function onOpponentWin(payload) {
  if (!payload?.seat || loading.value) return
  try {
    if (payload.seat === seatWind.value && payload.winType === 'catch_win') {
      await declareSelfRon(payload.winTile, payload.discarderSeat)
    } else {
      await declareOpponentWin(payload)
    }
    analyzeError.value = ''
  } catch (e) {
    analyzeError.value = e?.message || String(e)
  }
}

function onDismissSelfWin() {
  selfWinDismissed.value = true
}

function onStartNextRound(payload) {
  if (gameMode.value === 'PVE' && payload?.isRoundOver && pveRoundOverPending.value) {
    showGameOverModal.value = false
    showRoundSummaryModal.value = true
    return
  }
  localRecommend.value = null
  recommendFetchKey.value = ''
  analyzeError.value = ''
  Promise.resolve(startNextRound(
    payload?.lastWinnerSeat ?? null,
    !!payload?.isDealerWin,
    { isDraw: !!payload?.isDraw },
  )).then(() => { localRecommend.value = null }).catch((e) => { analyzeError.value = e?.message || String(e) })
}

async function onContinuePveCircle() {
  try {
    localRecommend.value = null
    recommendFetchKey.value = ''
    await continuePveCircle()
  } catch (e) { analyzeError.value = e?.message || String(e) }
}

async function onExitPve() {
  try {
    await exitPveGame()
    activeUiMode.value = ''
    localRecommend.value = null
    recommendFetchKey.value = ''
  } catch (e) { analyzeError.value = e?.message || String(e) }
}

/** 荒牌流局（可选入口） */
function onDeclareDraw() {
  declareDraw('荒牌流局').catch((e) => {
    analyzeError.value = e?.message || String(e)
  })
}

/**
 * 对手行动权打出 1 张（唯一对手弃牌入口）
 */
async function onOpponentDiscard({ seat_wind, tile }) {
  if (!seat_wind || !tile || loading.value) return
  if (showActionPrompt.value) {
    analyzeError.value =
      '请先完成自家吃碰过，或在上方卡片代录其他家副露'
    return
  }
  try {
    await opponentDiscardTile(seat_wind, tile)
    localRecommend.value = null
    recommendFetchKey.value = ''
  } catch (e) {
    analyzeError.value = e?.message || String(e)
  }
}

/** 代录对手吃/碰/明杠/暗杠 → 行动权跳到该对手切牌 */
async function onOpponentMeld(payload) {
  if (!payload?.seat || loading.value) return
  try {
    if (payload.meld_type === 'an_gang') {
      const face = payload.tiles?.[0]
      await executeOpponentAnGang(payload.seat, face)
    } else {
      await executeOpponentMeld(payload)
    }
    localRecommend.value = null
    recommendFetchKey.value = ''
    analyzeError.value = ''
    // 对手暗杠抬高胡头后：预取一次 recommend，使下一拍自家切牌立即感知威胁
    // （当前仍为对手 DISCARD，结果缓存至轮到自家时复用 key 会失效，故仅清缓存）
  } catch (e) {
    analyzeError.value = e?.message || String(e)
  }
}

/**
 * ActionPrompt：过 → passCall；吃碰 → applySelfMeld 切牌；明杠 → 副露后补牌再切；胡 → acknowledgeHu
 */
async function onActionSelected(payload) {
  analyzeError.value = ''
  const type = payload.action_type
  const provider =
    lastDiscardSeat.value ||
    payload.provider_seat ||
    callProviderSeat.value ||
    ''

  let claimed = callDiscardedTile.value
  if (!claimed && (type === 'pong' || type === 'ming_gang' || type === 'hu')) {
    // 碰/杠 tiles 均为同名，任取一张即可
    claimed = payload.tiles?.[0] || ''
  }
  if (!claimed && provider) {
    const opp = roundState.opponents.find((o) => o.seat_wind === provider)
    if (opp?.discards?.length) {
      claimed = opp.discards[opp.discards.length - 1]
    }
  }

  try {
    if (payload.provider_seat && lastDiscardSeat.value && payload.provider_seat !== lastDiscardSeat.value) {
      throw new Error('响应已失效：供牌方不是最近出牌者')
    }
    if (type === 'pass') {
      if (gameMode.value === 'PVE' && !currentHuSeat.value) {
        const remaining = (lastStepResult.value?._table_responses || []).filter((row) => row.seat !== seatWind.value)
        lastStepResult.value = { ...lastStepResult.value, _table_responses: remaining, call_decision: null, need_self_action: false, action_phase: 'WAIT', note: '' }
        currentPhase.value = 'WAIT_RESPONSE'
        if (!remaining.length && !pendingHuQueue.value.length) await passAllCalls(claimed || null)
        return
      }
      await passCall(claimed || null)
      return
    }
    if (type === 'hu' || type === 'catch_win') {
      await declareSelfRon(claimed, provider)
      return
    }
    if (type === 'chi' || type === 'pong' || type === 'ming_gang') {
      await applySelfMeld({
        meld_type: type,
        tiles: [...(payload.tiles || [])],
        claimed_tile: claimed,
        provider_seat: provider,
      })
      localRecommend.value = null
      recommendFetchKey.value = ''
      // 明杠后待补牌：不请求切牌推荐；吃碰后暗手满则补算
      if (
        type !== 'ming_gang' &&
        handReadyToDiscard.value &&
        !lastStepResult.value?.recommend_discard?.best_tile
      ) {
        await refreshLocalRecommend()
      }
    }
  } catch (e) {
    analyzeError.value = e?.message || String(e)
  }
}

function onUndo() {
  if (!canUndo.value || loading.value) return
  undoLastStep()
  localRecommend.value = null
  recommendFetchKey.value = ''
  analyzeError.value = ''
}

async function onReset(clearHistory = false) {
  localRecommend.value = null
  recommendFetchKey.value = ''
  analyzeError.value = ''
  analyzeLoading.value = false
  selfWinDismissed.value = false
  try {
    await resetGame({ clearHistory })
  } catch (error) {
    analyzeError.value = error?.message || String(error)
  }
}
</script>

<template>
  <div
    class="min-h-screen bg-gradient-to-br from-emerald-950 via-teal-900 to-slate-900 px-4 py-8 sm:px-6 sm:py-10"
    :class="gameMode === 'PVE' && activeUiMode === 'PVE' ? 'pve-portrait-shell' : ''"
  >
    <section v-if="!activeUiMode" class="mx-auto flex min-h-[75vh] max-w-5xl flex-col items-center justify-center text-center">
      <p class="text-sm font-semibold tracking-[0.25em] text-amber-300">台州麻将 · 实战练习</p>
      <h1 class="mt-3 text-4xl font-bold text-amber-50 sm:text-5xl">选择对局模式</h1>
      <p class="mt-3 max-w-xl text-sm leading-6 text-teal-100/70">使用实时净 EV 辅助练习，或进入全景沙盘自由推演。</p>
      <div class="mt-9 grid w-full max-w-3xl gap-4 sm:grid-cols-2">
        <button class="rounded-3xl border border-amber-300/60 bg-amber-400/15 p-7 text-left transition hover:-translate-y-1 hover:bg-amber-400/25 disabled:cursor-wait disabled:opacity-65" :disabled="pveStartLoading" @click="openPveConfig">
          <span class="text-2xl">人机对战</span><span class="mt-2 block text-sm text-amber-100/70">带 EV 辅助 · 三家 AI 自主决策</span>
        </button>
        <button class="rounded-3xl border border-teal-300/35 bg-teal-900/40 p-7 text-left transition hover:-translate-y-1 hover:bg-teal-800/50 disabled:cursor-wait disabled:opacity-65" :disabled="pveStartLoading" @click="chooseSandboxMode">
          <span class="text-2xl text-teal-50">全景上帝视角沙盘</span><span class="mt-2 block text-sm text-teal-100/65">自定义牌局 · 手动推演四方行动</span>
        </button>
      </div>
      <p v-if="pveStartLoading" class="mt-5 text-sm text-teal-100" role="status">正在连接云端计算引擎并初始化对局…</p>
      <p v-if="cloudWakeMessage" class="mt-2 text-sm text-amber-200" role="status">{{ cloudWakeMessage }}</p>
      <p v-if="errorMsg" class="mt-5 text-sm text-rose-200">{{ errorMsg }}</p>
      <PveStartDialog v-if="pveConfigOpen" v-model:enableEV="enableEV" :busy="pveStartLoading" @close="pveConfigOpen = false" @start="choosePveMode" />
    </section>
    <div v-else :class="gameMode === 'PVE' ? 'pve-session-view' : ''">
    <div v-if="gameMode === 'PVE'" class="pve-landscape-hint" role="note">建议横屏使用，体验完整牌桌视野</div>
    <header class="mb-8 text-center">
      <h1
        class="text-3xl font-semibold tracking-wide text-amber-50 sm:text-4xl"
      >
        台州麻将切牌决策助手
      </h1>
      <p class="mt-2 text-sm text-teal-200/75">
        {{ gameMode === 'PVE' ? '牌墙自动发牌 · 三家 AI 自主决策 · 实时 EV 辅助切牌' : '先录入起手（庄 14 / 闲 13）→ 开始对局 → 按串行时序推演' }}
      </p>
      <p v-if="cloudWakeMessage" class="mt-2 text-sm text-amber-200" role="status">{{ cloudWakeMessage }}</p>
    </header>

    <main class="mx-auto flex flex-col gap-6" :class="gameMode === 'PVE' ? ['pve-game-main', 'max-w-7xl pb-24'] : 'max-w-6xl pb-16'">
      <!-- ========== 顶部全局轮次状态条 ========== -->
      <section
        class="rounded-2xl border p-4 shadow-lg transition-colors duration-300 sm:p-5"
        :class="statusBarToneClass"
        aria-live="polite"
        aria-label="轮次状态"
      >
        <div v-if="gameMode === 'PVE'" class="mb-3 flex flex-wrap items-center justify-between gap-2 rounded-xl border border-amber-300/20 bg-black/15 px-3 py-2 text-xs text-amber-100">
          <span>第 {{ roundCount }} 圈 · 当前庄家：{{ pvePlayerRoleById[dealerPlayerId] }} · 东风</span>
          <span class="flex flex-wrap items-center gap-x-2 gap-y-1">
            <b class="text-amber-100">累计积分：</b>
            <span v-for="(row, index) in pveLeaderboard" :key="row.role" class="whitespace-nowrap" :class="row.score > 0 ? 'text-emerald-300' : row.score < 0 ? 'text-rose-300' : 'text-amber-100/80'">
              {{ index ? '· ' : '' }}{{ row.role }} {{ signedScore(row.score) }}
            </span>
          </span>
          <div class="flex items-center gap-2" aria-label="对局音效设置">
            <button type="button" class="rounded-lg border border-amber-300/30 px-2 py-1" :aria-label="soundMuted ? '开启音效' : '静音'" :aria-pressed="soundMuted" @click="soundMuted = !soundMuted; if (!soundMuted) soundEngine.unlock()">{{ soundMuted ? '🔇 静音' : '🔊 音效' }}</button>
            <label class="flex items-center gap-1 whitespace-nowrap">音量 <input v-model.number="soundVolume" type="range" min="0" max="100" step="5" class="w-20 accent-amber-300" aria-label="音效音量" /></label>
          </div>
          <button class="rounded-lg border border-slate-500/50 px-2 py-1 text-slate-200" @click="returnHome">返回主页</button>
        </div>
        <div class="mb-3 flex flex-wrap items-start justify-between gap-3">
          <div class="min-w-0 flex-1">
            <div class="mb-1.5 flex flex-wrap items-center gap-2">
              <span
                class="rounded-md bg-black/25 px-2 py-0.5 text-[11px] font-semibold tabular-nums text-amber-100/95"
              >
                <template v-if="isSetup">准备中</template>
                <template v-else>第 {{ turnCount }} 巡</template>
              </span>
              <span
                v-if="isPlaying"
                class="rounded-md bg-black/20 px-2 py-0.5 text-[11px] tabular-nums text-teal-100/80"
              >
                本巡第 {{ handInRound }} 手 · 累计 {{ totalDiscardCount }} 张
              </span>
              <span
                v-if="isPlaying"
                class="rounded-md bg-teal-900/50 px-2 py-0.5 text-[11px] text-teal-200/85"
              >
                权={{ currentTurnSeat }}
              </span>
              <span
                class="rounded-md px-2 py-0.5 text-[11px] font-medium"
                :class="
                  isSetup
                    ? 'bg-sky-900/50 text-sky-100/90'
                    : 'bg-emerald-900/50 text-emerald-100/90'
                "
              >
                {{ gameState }}
              </span>
            </div>
            <p class="text-base font-semibold leading-snug text-amber-50 sm:text-lg">
              <span class="mr-1.5" aria-hidden="true">{{
                turnStatus.emoji
              }}</span>
              {{ turnStatus.headline }}
            </p>
            <p class="mt-1 text-xs leading-relaxed text-teal-200/75">
              {{ turnStatus.detail }}
            </p>
          </div>
          <p class="shrink-0 text-[11px] text-teal-300/65">
            已推演 {{ historyDepth }} 步
          </p>
        </div>

        <div v-if="gameMode !== 'PVE'" class="flex flex-wrap gap-2">
          <button
            v-if="isSetup"
            type="button"
            class="rounded-xl border-2 border-emerald-400/70 bg-emerald-500/20 px-4 py-2 text-sm font-bold text-emerald-50 shadow-md transition hover:bg-emerald-400/30 disabled:cursor-not-allowed disabled:opacity-40"
            :disabled="loading || isPlaying"
            title="洗牌发牌：四家暗手明牌 + 牌墙（上帝视角）"
            @click="onAutoDeal"
          >
            自动发牌（上帝视角）
          </button>
          <button
            v-if="isSetup"
            type="button"
            class="rounded-xl px-4 py-2 text-sm font-bold shadow-md transition disabled:cursor-not-allowed disabled:opacity-40"
            :class="
              canStartPlaying
                ? 'border-2 border-amber-300 bg-amber-500 text-emerald-950 hover:bg-amber-400'
                : 'border border-teal-600/40 bg-teal-900/40 text-teal-400/70'
            "
            :disabled="!canStartPlaying || loading"
            @click="onConfirmStart"
          >
            开始对局（{{ targetInitialCount }} 张）
          </button>
          <button
            type="button"
            class="rounded-xl border-2 border-amber-400/70 bg-amber-500/15 px-4 py-2 text-sm font-bold text-amber-100 shadow-md shadow-amber-950/30 transition hover:bg-amber-400/25 disabled:cursor-not-allowed disabled:opacity-40"
            :disabled="!canUndo || loading || isSetup"
            title="回退上一手打牌，恢复行动权"
            @click="onUndo"
          >
            ↩ 撤销上一步打牌 (Undo)
          </button>
          <button
            type="button"
            class="rounded-xl border border-rose-500/40 px-3 py-2 text-xs text-rose-100 hover:bg-rose-900/30 disabled:opacity-40"
            :disabled="resetInProgress"
            @click="onReset()"
          >
            {{ resetInProgress ? '重新发牌中…' : '重开本局（保留计分）' }}
          </button>
          <button type="button" class="rounded-xl border border-slate-500/40 px-3 py-2 text-xs text-slate-200 disabled:opacity-40"
            :disabled="resetInProgress" @click="onReset(true)">
            全部重置（清空历史计分）
          </button>
          <button
            v-if="isPlaying"
            type="button"
            class="rounded-xl border border-slate-400/40 bg-slate-900/40 px-3 py-2 text-xs font-semibold text-slate-100 hover:bg-slate-800/50 disabled:opacity-40"
            :disabled="loading"
            title="荒牌流局：下局下庄"
            @click="onDeclareDraw"
          >
            荒牌流局
          </button>
          <button
            v-if="isPlaying"
            type="button"
            class="rounded-xl border border-amber-500/45 bg-amber-500/10 px-3 py-2 text-xs font-semibold text-amber-100 hover:bg-amber-500/20 disabled:opacity-40"
            :disabled="!canStartDiscardTurn"
            @click="onStartSelfDiscard"
          >
            开始切牌（{{ requiredHandCount }} 张）
          </button>
        </div>

        <p class="mt-3 text-[10px] text-teal-400/60">
          阶段 {{ phaseLabel }}
          <span v-if="isPlaying" class="text-teal-500/50"
            >({{ currentPhase }})</span
          >
        </p>
      </section>

      <!-- 手动沙盘沿用悬浮响应面板；PvE 响应卡放在自家手牌下方。 -->
      <ActionPrompt
        v-if="showActionPrompt && gameMode !== 'PVE'"
        :call-decision="activeCallDecision"
        :seat-wind="seatWind"
        :provider-seat="callProviderSeat"
        :dealer-tile="dealerTile"
        :discarded-tile="callDiscardedTile"
        :disabled="loading || (gameMode === 'PVE' && aiActionBusy)"
        @action-selected="onActionSelected"
      />

      <GameConfig
        v-if="gameMode !== 'PVE'"
        v-model:dealer-tile="dealerTile"
        v-model:seat-wind="seatWind"
        :locked="isPlaying"
        :can-start="canStartPlaying"
        :target-hand-count="targetInitialCount"
        :hand-count="handCount"
        @confirm-start="onConfirmStart"
        @reopen-table="onReopenTable"
      />

      <!-- 全景上帝视角沙盘：四家暗手本地明牌；推荐请求不含三家暗手 -->
      <GodViewTable
        v-if="gameMode !== 'PVE'"
        :table-responses="lastStepResult?._table_responses || []"
        :key="'table-' + gameRoundId"
        :seat-wind="seatWind"
        :is-dealer="isDealer"
        :dealer-tile="dealerTile"
        :current-turn-seat="currentTurnSeat"
        :self-hand="handTiles"
        :self-melds="melds"
        :self-discards="selfDiscards"
        :opponents="opponents"
        :recommend="displayRecommend"
        :recommend-loading="analyzeLoading"
        :best-tile="bestDiscardTile"
        :self-gang-candidates="selfGangCandidates"
        :table-locked="isPlaying"
        :call-pending="callOrResponsePending"
        :response-window="responseWindowOpen"
        :catch-win-seats="catchWinSeats"
        :last-discard-seat="lastDiscardSeat || ''"
        :last-discarded-tile="lastDiscardedTileForClaim"
        :disabled="stepLoading || isGameOver"
        :wall-count="wallTiles.length"
        :latest-drawn-by-seat="latestDrawnBySeat"
        :hand-layout-pinned="handLayoutPinned"
        @discard-tile="onGodViewDiscard"
        @move-joker="onGodViewMoveJoker"
        @select-self-gang="onDeclareSelfKong"
        @pass-all-calls="onPassAllCalls"
        @catch-win="onOpponentWin"
      />

      <!-- 串行时序：仅 PLAYING 且 currentTurnSeat 对手可打出 -->
      <OpponentPanel
        v-if="gameMode !== 'PVE'"
        :key="'opponents-' + gameRoundId"
        v-model="opponents"
        :self-is-dealer="isDealer"
        :seat-wind="seatWind"
        :current-turn-seat="currentTurnSeat"
        :last-discard-seat="lastDiscardSeat || ''"
        :last-discarded-tile="lastDiscardedTileForClaim"
        :dealer-tile="dealerTile"
        :last-step-note="lastStepResult?.note || ''"
        :base-occupied="opponentBaseOccupied"
        :table-locked="isPlaying"
        :call-pending="callOrResponsePending"
        :response-window="responseWindowOpen"
        :catch-win-seats="catchWinSeats"
        :disabled="loading || isSetup || isGameOver"
        @opponent-discard="onOpponentDiscard"
        @opponent-meld="onOpponentMeld"
        @opponent-win="onOpponentWin"
        @pass-all-calls="onPassAllCalls"
      />

      <PvEBoard
        v-if="gameMode === 'PVE'"
        :seat-wind="seatWind"
        :dealer-seat="dealerSeat"
        :dealer-tile="dealerTile"
        :current-turn-seat="currentTurnSeat"
        :opponents="opponents"
        :round-count="roundCount"
        :wall-count="wallTiles.length"
        :cumulative-scores="cumulativeScores"
        :ai-status="aiStatus"
        :ai-announcement="aiAnnouncement"
        :thinking-seat="aiThinkingSeat"
        :risk-message="opponentWarning.text"
        :risk-level="opponentWarning.level"
      />

      <PlayerWorkbench :pve="gameMode === 'PVE'" :show-recommendation="gameMode !== 'PVE' || enableEV || decisionDockPhase === 'call' || canSelfWin">
      <template #heading><header v-if="gameMode === 'PVE'" class="flex flex-wrap items-center justify-between gap-2 rounded-xl border border-amber-400/30 bg-teal-950 px-4 py-3 text-amber-50 lg:col-span-2" aria-label="自家信息">
        <b>自家 · {{ windLabel(seatWind) }}风 <span v-if="seatWind === dealerSeat" class="text-amber-300">庄家</span></b>
        <span>累计 {{ cumulativeScores[seatWind] || 0 }} 分</span>
      </header></template>
      <!-- SETUP：点击移除；PLAYING：仅自家行动权可切 -->
      <HandBar
        class="pve-self-hand"
        :wall-driven="gameMode === 'PVE'"
        v-model="handTiles"
        v-model:auto-sort="autoSortEnabled"
        :capacity="handCapacity"
        :dealer-tile="dealerTile"
        :latest-drawn-tile="isSetup ? '' : latestDrawnTile || ''"
        :highlight-tile="
          enableEV && isPlaying && (handReadyToDiscard || isMyDiscardTurn)
            ? bestDiscardTile
            : ''
        "
        :setup-mode="isSetup"
        :discard-mode="
          isPlaying && (handReadyToDiscard || isMyDiscardTurn)
        "
        :can-self-win="canSelfWin"
        :turn-focused="selfPanelFocused"
        :layout-pinned="!!handLayoutPinned?.[seatWind]"
        :disabled="
          stepLoading ||
          showActionPrompt ||
          (isPlaying && !isSelfTurn)
        "
        :ev-calculating="enableEV && isCalculatingEV && (handReadyToDiscard || isMyDiscardTurn)"
        @discard-tile="(tile, index) => onDiscardTile(tile, index)"
        @move-joker="
          ({ fromIndex, toIndex }) =>
            onGodViewMoveJoker({
              seat_wind: seatWind,
              fromIndex,
              toIndex,
            })
        "
        @manual-sort="manualSortHand"
      />

      <MeldBar
        :read-only="gameMode === 'PVE'"
        :compact="gameMode === 'PVE'"
        :dealer-tile="dealerTile"
        v-model="melds"
        :hand-tiles="handTiles"
        :discarded-tiles="selfDiscards"
        :extra-occupied="meldBarExtra"
        :class="
          isPlaying && !selfPanelFocused
            ? 'pointer-events-none opacity-75'
            : isSetup
              ? 'opacity-90'
              : ''
        "
      />
      <div v-if="gameMode === 'PVE' && selfDiscards.length" class="rounded-xl border border-teal-700/40 p-2.5" aria-label="自家牌河">
        <p class="mb-1 text-xs text-teal-200">自家牌河</p>
        <DiscardRiver :tiles="selfDiscards" compact layout="self" />
      </div>

      <SelfWinBanner
        v-if="gameMode !== 'PVE' && canSelfWin && selfWinInfo && !loading"
        class="mb-3"
        :info="selfWinInfo"
        :disabled="loading"
        @declare="onDeclareSelfWin"
        @dismiss="onDismissSelfWin"
      />

      <div
        v-if="
          isPlaying &&
          (handReadyToDiscard || isMyDiscardTurn) &&
          selfGangCandidates.length &&
          !loading &&
          !showActionPrompt
        "
        class="mb-3 flex flex-wrap gap-2"
        aria-label="暗杠补杠操作"
      >
        <button
          v-for="(g, gi) in selfGangCandidates"
          :key="`${g.action_type}-${g.tile}-${gi}`"
          type="button"
          class="inline-flex items-center gap-2 rounded-xl border border-violet-400/55 bg-violet-950/75 px-3.5 py-2.5 text-sm font-semibold text-violet-50 shadow-md transition hover:-translate-y-0.5 hover:border-violet-300 hover:bg-violet-900/90 focus:outline-none focus-visible:ring-2 focus-visible:ring-violet-300"
          @click="onDeclareSelfKong(g)"
        >
          <span>
            {{ g.action_type === 'bu_gang' ? '宣布补杠' : '宣布暗杠' }}：{{
              tileLabel(g.tile)
            }}
          </span>
          <span class="rounded-md bg-violet-500/30 px-1.5 py-0.5 text-[11px] font-bold text-amber-100">
            预估胡头 +{{ g.est_hu_bonus }}
          </span>
          <span class="text-[11px] font-medium text-violet-200/80">
            EV {{ Number(g.ev_score) >= 0 ? '+' : '' }}{{ Number(g.ev_score).toFixed(1) }}
          </span>
        </button>
      </div>

      <template #recommendation>
      <SelfWinBanner
        v-if="gameMode === 'PVE' && canSelfWin && selfWinInfo && !loading"
        class="pve-self-win-prompt"
        :info="selfWinInfo"
        :disabled="loading"
        @declare="onDeclareSelfWin"
        @dismiss="onDismissSelfWin"
      />
      <ActionPrompt
        v-else-if="gameMode === 'PVE' && decisionDockPhase === 'call'"
        inline
        dock
        keyboard-shortcuts
        :call-decision="activeCallDecision"
        :seat-wind="seatWind"
        :provider-seat="callProviderSeat"
        :dealer-tile="dealerTile"
        :discarded-tile="callDiscardedTile"
        :disabled="loading || aiActionBusy"
        :show-recommendation="enableEV"
        @action-selected="onActionSelected"
      />
      <PvEDiscardHud
        v-else-if="gameMode === 'PVE' && enableEV && (displayRecommend || analyzeLoading) && decisionDockPhase === 'discard' && !stepLoading"
        :best-tile="displayRecommend?.best_tile || ''"
        :candidates="displayRecommend?.candidates || []"
        :loading="analyzeLoading"
        :interactive="!analyzeLoading && !!displayRecommend?.best_tile"
        @select-tile="onSelfDiscardFromRecommend"
      />
      <ResultCard
        v-else-if="gameMode !== 'PVE' &&
          (displayRecommend || analyzeLoading) &&
          decisionDockPhase === 'discard' &&
          !stepLoading
        "
        :best-tile="displayRecommend?.best_tile || ''"
        :best-action="displayRecommend?.best_action || null"
        :candidates="displayRecommend?.candidates || []"
        :self-gang-candidates="selfGangCandidates"
        :seat-wind="seatWind"
        :is-dealer="isDealer"
        :can-self-win-hint="canSelfWin"
        :compact="gameMode === 'PVE'"
        :loading="analyzeLoading"
        :interactive="!analyzeLoading && !!displayRecommend?.best_tile"
        @select-tile="onSelfDiscardFromRecommend"
        @select-self-gang="onDeclareSelfKong"
      />
      </template>
      </PlayerWorkbench>

      <DiscardPool
        v-if="gameMode !== 'PVE'"
        v-model="selfDiscards"
        :hand-tiles="handTiles"
        :dealer-tile="dealerTile"
        :extra-occupied="discardPoolExtra"
        :class="isPlaying ? 'pointer-events-none opacity-75' : ''"
      />

      <!-- SETUP 始终可点；PLAYING 仅待摸可点 -->
      <TilePicker
        v-if="gameMode !== 'PVE'"
        :model-value="handTiles"
        :max-count="setupPickerMax"
        :occupied-tiles="tilePickerOccupied"
        :disabled="!tilePickerEnabled || loading || gameMode === 'PVE'"
        :class="[
          isSetup || canSelfDraw
            ? 'ring-2 ring-emerald-500/80 shadow-lg'
            : 'pointer-events-none opacity-75',
        ]"
        @update:model-value="onTilePickerUpdate"
      />

      <section
        v-if="gameMode !== 'PVE'"
        class="flex flex-col gap-3 rounded-2xl border border-teal-700/40 bg-teal-950/40 p-4 sm:flex-row sm:items-center sm:justify-between sm:p-5"
      >
        <button
          type="button"
          class="rounded-xl border border-teal-600/50 px-4 py-2.5 text-sm font-medium text-teal-100 transition hover:border-rose-400/50 hover:bg-rose-500/10 hover:text-rose-100 disabled:cursor-not-allowed disabled:opacity-40"
          :disabled="!hasHand || loading || isPlaying"
          @click="clearHand"
        >
          清空重选
        </button>
        <p class="text-center text-xs text-teal-300/70 sm:text-right">
          暗手 {{ handCount }}/{{ handCapacity }}
          <template v-if="isSetup">
            · 起手目标 {{ targetInitialCount }}（{{
              isDealer ? '庄' : '闲'
            }}）
          </template>
          · 键盘占用已同步全场可见牌
        </p>
      </section>

      <p
        v-if="errorMsg"
        class="rounded-xl border border-rose-500/40 bg-rose-950/40 px-4 py-3 text-center text-sm text-rose-200"
        role="alert"
      >
        {{ errorMsg }}
        <button v-if="aiError" class="ml-3 underline" @click="retryAI">重试 AI 行动</button>
      </p>

      <div
        v-if="stepLoading"
        class="flex flex-col items-center gap-3 rounded-2xl border border-teal-700/30 bg-teal-950/30 px-6 py-10"
        aria-live="polite"
        aria-busy="true"
      >
        <div
          class="h-10 w-10 animate-spin rounded-full border-2 border-amber-400/30 border-t-amber-400"
        />
        <p class="text-sm text-teal-100/90">牌局推进中…</p>
      </div>

      <!-- 自家切牌：自动展示净 EV 排序，点击确认切出 -->
      <!-- 自家切牌：自摸后或副露后均可展示净 EV -->

    </main>

    <GameOverModal
      v-if="showGameOverModal && isGameOver && selfWinSettlement"
      :info="selfWinSettlement"
      :seat-wind="seatWind"
      :is-dealer="isDealer"
      :dealer-seat="dealerSeat"
      :opponents="opponents"
      :cumulative-scores="cumulativeScores"
      :round-history="roundHistory"
      :is-round-over="gameMode === 'PVE' && pveRoundOverPending"
      @next-round="onStartNextRound"
      @review-history="() => {}"
    />
    <PvECircleSummary v-if="gameMode === 'PVE' && showRoundSummaryModal" :round-count="roundCount" :scores="cumulativeScores" :seat-wind="seatWind" @continue="onContinuePveCircle" @exit="onExitPve" />
    </div>
    <footer class="app-version-footer mt-4 text-center text-xs text-teal-200/55" aria-label="当前版本">{{ appVersion }}</footer>
  </div>
</template>
