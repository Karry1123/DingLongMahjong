export const LOCAL_MAX_RECORDS = 10
export const LOCAL_RECORDS_KEY = 'dinglong_game_records_local'

function storage() {
  try { return globalThis.localStorage } catch { return null }
}

export function readLocalRecords(store = storage()) {
  try {
    const rows = JSON.parse(store?.getItem(LOCAL_RECORDS_KEY) || '[]')
    return Array.isArray(rows) ? rows.filter(row => row?.summary?.game_id).slice(0, LOCAL_MAX_RECORDS) : []
  } catch { return [] }
}

export function cacheLocalRecords(incoming, store = storage()) {
  const byId = new Map(readLocalRecords(store).map(row => [row.summary.game_id, row]))
  for (const row of incoming) {
    if (!row?.summary?.game_id) continue
    const previous = byId.get(row.summary.game_id)
    byId.set(row.summary.game_id, { ...previous, ...row, record: previous?.record || row.record })
  }
  const rows = [...byId.values()].sort((a, b) =>
    String(b.summary.timestamp || '').localeCompare(String(a.summary.timestamp || ''))
  ).slice(0, LOCAL_MAX_RECORDS)
  try { store?.setItem(LOCAL_RECORDS_KEY, JSON.stringify(rows)) } catch {
    // Full replay snapshots may exceed the browser quota. Keep the ten summaries;
    // their complete records remain retrievable from the cloud by game_id.
    try { store?.setItem(LOCAL_RECORDS_KEY, JSON.stringify(rows.map(({ summary }) => ({ summary })))) } catch { /* Storage unavailable. */ }
  }
  return rows
}
