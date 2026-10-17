import { test } from 'node:test'
import assert from 'node:assert/strict'
import { compareVersions, describeRelease, parseVersion, updateAvailable } from '../src/utils/appUpdate.js'

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
