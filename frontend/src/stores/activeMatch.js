import { reactive } from 'vue'
import { getMatch } from '../services/matchApi.js'
export const activeMatch = reactive({ match: null, game: null, connection: 'idle', snapshotVersion: 0 })
let generation = 0
export function clearActiveMatch() { generation++; Object.assign(activeMatch, { match: null, game: null, connection: 'idle', snapshotVersion: 0 }) }
export function applySnapshot(message) {
  const incoming = message.match || message.room
  activeMatch.match = message.match || { ...activeMatch.match, ...incoming, id:incoming.id || activeMatch.match?.id }
  activeMatch.game = message.game || null
  activeMatch.snapshotVersion++
}
export async function refreshMatch(id) { const version = generation; const data = await getMatch(id); if (version === generation) activeMatch.match = data.match; return data.match }
