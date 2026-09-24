import assert from 'node:assert/strict'
import { afterEach, test } from 'node:test'
import { cloudWakeMessage, fetchWithWakeNotice } from '../src/services/api.js'

const originalFetch = globalThis.fetch
afterEach(() => { globalThis.fetch = originalFetch })

test('a slow API request shows the wake notice and clears it when the response arrives', async () => {
  let finish
  globalThis.fetch = () => new Promise((resolve) => { finish = resolve })
  const pending = fetchWithWakeNotice('/api/game/auto-deal', {}, {
    wakeDelayMs: 5, timeoutMs: 200,
  })
  await new Promise((resolve) => setTimeout(resolve, 15))
  assert.match(cloudWakeMessage.value, /云端计算引擎唤醒中/)
  finish({ ok: true })
  await pending
  assert.equal(cloudWakeMessage.value, '')
})

test('an unresponsive API request times out and releases the wake notice', async () => {
  globalThis.fetch = (_, { signal }) => new Promise((_, reject) => {
    signal.addEventListener('abort', () => reject(Object.assign(
      new Error('aborted'), { name: 'AbortError' },
    )), { once: true })
  })
  await assert.rejects(
    fetchWithWakeNotice('/api/recommend', {}, { wakeDelayMs: 5, timeoutMs: 20 }),
    /响应超时，请稍后重试/,
  )
  assert.equal(cloudWakeMessage.value, '')
})
