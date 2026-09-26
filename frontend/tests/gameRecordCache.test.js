import assert from 'node:assert/strict'
import { test } from 'node:test'
import { LOCAL_MAX_RECORDS, LOCAL_RECORDS_KEY, cacheLocalRecords, readLocalRecords } from '../src/utils/gameRecordCache.js'
import { getGameRecord, listGameRecords, postGameRecord } from '../src/services/api.js'

function memoryStorage() {
  const values = new Map()
  return { getItem: key => values.get(key) ?? null, setItem: (key, value) => values.set(key, value) }
}
function summary(i) {
  return { game_id: `GM-${String(i).padStart(6, '0')}`, timestamp: new Date(2026, 0, i + 1).toISOString() }
}

test('local FIFO keeps ten newest games and duplicate writes do not evict another game', () => {
  const store = memoryStorage()
  for (let i = 0; i < 11; i++) cacheLocalRecords([{ summary: summary(i), record: { steps: [i] } }], store)
  const rows = readLocalRecords(store)
  assert.equal(LOCAL_MAX_RECORDS, 10)
  assert.equal(rows.length, 10)
  assert.equal(rows[0].summary.game_id, summary(10).game_id)
  assert.equal(rows.at(-1).summary.game_id, summary(1).game_id)
  cacheLocalRecords([{ summary: summary(10), record: { steps: [] } }], store)
  assert.equal(readLocalRecords(store).length, 10)
  assert.deepEqual(readLocalRecords(store)[0].record.steps, [10])
})

test('storage quota falls back to summaries and corrupt storage does not throw', () => {
  const store = memoryStorage()
  const write = store.setItem
  store.setItem = (key, value) => {
    if (value.includes('"record"')) throw new Error('QuotaExceededError')
    write(key, value)
  }
  cacheLocalRecords([{ summary: summary(1), record: { steps: ['large replay'] } }], store)
  assert.equal(readLocalRecords(store).length, 1)
  assert.equal(readLocalRecords(store)[0].record, undefined)
  write(LOCAL_RECORDS_KEY, 'broken')
  assert.deepEqual(readLocalRecords(store), [])
})

test('the eleventh cloud upload evicts only local history; old ID still loads from cloud', async t => {
  const original = Object.getOwnPropertyDescriptor(globalThis, 'localStorage')
  Object.defineProperty(globalThis, 'localStorage', { configurable: true, value: memoryStorage() })
  t.after(() => {
    if (original) Object.defineProperty(globalThis, 'localStorage', original)
    else delete globalThis.localStorage
  })
  const cloud = new Map()
  t.mock.method(globalThis, 'fetch', async (url, options) => {
    if (options.method === 'POST') {
      const payload = JSON.parse(options.body)
      const item = summary(cloud.size)
      cloud.set(item.game_id, { ...payload, ...item })
      return Response.json({ ...item, summary: item })
    }
    return Response.json(cloud.get(url.split('/').at(-1)))
  })
  for (let i = 0; i < 11; i++) await postGameRecord({ round_id: `round-${i}`, steps: [i] })
  const listed = await listGameRecords()
  assert.equal(listed.records.length, 10)
  assert.ok(!listed.records.some(row => row.game_id === summary(0).game_id))
  assert.equal(cloud.size, 11)
  assert.deepEqual((await getGameRecord(summary(0).game_id)).steps, [0])
})
