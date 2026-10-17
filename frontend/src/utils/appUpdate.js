/** Version comparison and release parsing for the in-app update check (pure, testable). */
export const RELEASES_API = 'https://api.github.com/repos/Karry1123/DingLongMahjong/releases/latest'

/** Parse "v0.4.0-beta" / "0.4.1" into [0,4,0,'beta']; null when not a version. */
export function parseVersion(text) {
  const match = /^v?(\d+)\.(\d+)\.(\d+)(?:-([0-9A-Za-z.-]+))?/.exec(String(text || '').trim())
  if (!match) return null
  return [Number(match[1]), Number(match[2]), Number(match[3]), match[4] || '']
}

/** >0 when a is newer than b. A release without a pre-release suffix outranks one with it. */
export function compareVersions(a, b) {
  const x = parseVersion(a), y = parseVersion(b)
  if (!x || !y) return 0
  for (let i = 0; i < 3; i++) if (x[i] !== y[i]) return x[i] - y[i]
  if (x[3] === y[3]) return 0
  if (!x[3]) return 1
  if (!y[3]) return -1
  return x[3] < y[3] ? -1 : 1
}

/** Pick the APK asset and version out of a GitHub release payload; null when nothing installable. */
export function describeRelease(release) {
  if (!release || release.draft) return null
  const asset = (release.assets || []).find(item => /\.apk$/i.test(item.name || ''))
  if (!asset) return null
  return { version: release.tag_name || release.name || '', url: asset.browser_download_url, size: asset.size || 0, notes: release.body || '', page: release.html_url || '' }
}

export function updateAvailable(current, release) {
  const info = describeRelease(release)
  return info && compareVersions(info.version, current) > 0 ? info : null
}
