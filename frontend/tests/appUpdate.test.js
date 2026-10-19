import { test } from 'node:test'
import assert from 'node:assert/strict'
import { checkForUpdate, latestRelease, RELEASES_API, compareVersions, describeRelease, parseVersion, updateAvailable } from '../src/utils/appUpdate.js'

const release = (tag, assets = [{ name: 'DingLongMahjong-v0.4.1-beta.apk', browser_download_url: 'https://example.test/app.apk', size: 5242880 }]) =>
  ({ tag_name: tag, assets, html_url: 'https://example.test/release', body: 'notes' })

test('parses tags with and without v prefix or pre-release suffix', () => {
  assert.deepEqual(parseVersion('v0.4.0-beta'), [0, 4, 0, 'beta'])
  assert.deepEqual(parseVersion('1.2.3'), [1, 2, 3, ''])
  assert.equal(parseVersion('latest'), null)
})

test('orders numeric parts first, then treats a final release as newer than its pre-release', () => {
  assert.ok(compareVersions('0.4.1-beta', '0.4.0-beta') > 0)
  assert.ok(compareVersions('0.4.0', '0.4.0-beta') > 0)
  assert.ok(compareVersions('0.4.0-beta', '0.4.0') < 0)
  assert.equal(compareVersions('v0.4.0-beta', '0.4.0-beta'), 0)
  assert.ok(compareVersions('0.10.0', '0.9.9') > 0)
})

test('offers an update only when the latest release carries an APK newer than the installed version', () => {
  assert.equal(updateAvailable('0.4.0-beta', release('v0.4.0-beta')), null)
  assert.equal(updateAvailable('0.4.0-beta', release('v0.4.1-beta', [])), null)
  const info = updateAvailable('0.4.0-beta', release('v0.4.1-beta'))
  assert.equal(info.version, 'v0.4.1-beta')
  assert.equal(info.url, 'https://example.test/app.apk')
})

test('ignores drafts and releases without an APK asset', () => {
  assert.equal(describeRelease({ ...release('v9.9.9'), draft: true }), null)
  assert.equal(describeRelease(release('v9.9.9', [{ name: 'notes.txt' }])), null)
})


test('selects semantic latest APK including prereleases, ignoring draft and missing APK', () => {
  assert.equal(latestRelease([
    { ...release('v9.0.0'), draft: true }, release('v8.0.0', []),
    release('v0.9.0'), { ...release('v0.10.0-beta.2'), prerelease: true },
    { ...release('v0.10.0-beta.10'), prerelease: true }, release('invalid'),
  ]).version, 'v0.10.0-beta.10')
  assert.equal(latestRelease([release('v1.0.0-beta'), release('v1.0.0')]).version, 'v1.0.0')
  assert.equal(latestRelease([]), null)
})

const response = data => ({ ok: true, json: async () => data })

test('prefers backend and reports up-to-date without requesting GitHub', async () => {
  let calls = 0
  const fetcher = async () => { calls++; return response(describeRelease(release('v1.0.0'))) }
  assert.equal(await checkForUpdate('1.0.0', { fetcher }), null)
  assert.equal((await checkForUpdate('0.9.0', { fetcher })).version, 'v1.0.0')
  assert.equal(calls, 2)
})

test('falls back to GitHub list for HTTP, network and invalid backend responses', async () => {
  for (const mode of ['http', 'network', 'invalid']) {
    const urls = []
    const fetcher = async url => {
      urls.push(url)
      if (url === RELEASES_API) return response([release('v1.2.0-beta')])
      if (mode === 'network') throw new Error('offline')
      return mode === 'http' ? { ok: false, status: 503 } : response({})
    }
    assert.equal((await checkForUpdate('1.0.0', { fetcher })).version, 'v1.2.0-beta')
    assert.equal(urls.length, 2)
    assert.equal(urls[1], RELEASES_API)
  }
})

test('backend timeout aborts request and falls back even if fetch ignores abort', async () => {
  let signal
  const fetcher = (url, options) => {
    if (url === RELEASES_API) return Promise.resolve(response([release('v2.0.0')]))
    signal = options.signal
    return new Promise(() => {})
  }
  assert.equal((await checkForUpdate('1.0.0', { fetcher, timeoutMs: 10 })).version, 'v2.0.0')
  assert.equal(signal.aborted, true)
})

test('times out while reading JSON and reports both source failures', async () => {
  const fetcher = async () => ({ ok: true, json: () => new Promise(() => {}) })
  await assert.rejects(checkForUpdate('1.0.0', { fetcher, timeoutMs: 10 }), /后端：请求超时；GitHub：请求超时/)
})

test('missing APK list is a check failure, not an up-to-date result', async () => {
  const fetcher = async url => url === RELEASES_API ? response([release('v2.0.0', [])]) : { ok: false, status: 503 }
  await assert.rejects(checkForUpdate('1.0.0', { fetcher }), /未找到带 APK 的版本/)
})
