/** Version comparison and release parsing for the in-app update check (pure, testable). */
export const RELEASES_API = 'https://api.github.com/repos/Karry1123/DingLongMahjong/releases?per_page=10'
const LATEST_API = `${(import.meta.env?.VITE_API_BASE_URL || '').replace(/\/$/, '')}/api/app/latest`

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
  const left = x[3].split('.'), right = y[3].split('.')
  for (let i = 0; i < Math.max(left.length, right.length); i++) {
    if (left[i] === right[i]) continue
    if (left[i] === undefined) return -1
    if (right[i] === undefined) return 1
    const aNumeric = /^\d+$/.test(left[i]), bNumeric = /^\d+$/.test(right[i])
    if (aNumeric && bNumeric) return Number(left[i]) - Number(right[i])
    if (aNumeric !== bNumeric) return aNumeric ? -1 : 1
    return left[i] < right[i] ? -1 : 1
  }
  return 0
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

export function latestRelease(releases) {
  if (!Array.isArray(releases)) throw new Error('版本列表格式错误')
  return releases.map(describeRelease).filter(info => info && parseVersion(info.version) && info.url)
    .sort((a, b) => compareVersions(b.version, a.version))[0] || null
}

async function requestJson(url, fetcher, timeoutMs) {
  const controller = new AbortController()
  let timer
  try {
    return await Promise.race([
      (async () => {
        const response = await fetcher(url, { signal: controller.signal, headers: { Accept: 'application/json' } })
        if (!response.ok) throw new Error(`HTTP ${response.status}`)
        return response.json()
      })(),
      new Promise((_, reject) => {
        timer = setTimeout(() => { controller.abort(); reject(new Error('请求超时')) }, timeoutMs)
      }),
    ])
  } finally { clearTimeout(timer) }
}

/** Shared by the automatic banner and the manual settings check. */
export async function checkForUpdate(current, { fetcher = globalThis.fetch, timeoutMs = 8000, backendUrl = LATEST_API } = {}) {
  let info, backendError
  try {
    info = await requestJson(backendUrl, fetcher, timeoutMs)
    if (!info || !parseVersion(info.version) || !info.url) throw new Error('版本信息格式错误')
  } catch (error) {
    backendError = error
    try {
      info = latestRelease(await requestJson(RELEASES_API, fetcher, timeoutMs))
      if (!info) throw new Error('未找到带 APK 的版本')
    } catch (fallbackError) {
      throw new Error(`后端：${backendError.message}；GitHub：${fallbackError.message}`)
    }
  }
  return compareVersions(info.version, current) > 0 ? info : null
}

export function updateAction(current, nativeBuild, info) {
  if (!info || compareVersions(info.version, current) <= 0) return 'none'
  if (!Number.isInteger(info.nativeBuild)) return 'apk'
  if (info.nativeBuild > nativeBuild) return 'apk'
  if (info.nativeBuild === nativeBuild) return info.bundleUrl ? 'ota' : 'apk'
  return 'none'
}

// A whitelist keeps unknown routes and all table modes from reloading.
export function canReloadUpdate({ path, inGame = false }) {
  return !inGame && path === '/home'
}

export async function stageWebUpdate(liveUpdate, info, context) {
  const { bundleIds: blocked } = await liveUpdate.getBlockedBundles()
  if (blocked.includes(info.version)) throw new Error('该更新启动失败，已自动回退，请等待后续版本')
  const { bundleIds } = await liveUpdate.getBundles()
  if (!bundleIds.includes(info.version)) {
    await liveUpdate.downloadBundle({ bundleId: info.version, url: info.bundleUrl,
      ...(info.bundleSha256 ? { checksum: info.bundleSha256 } : {}) })
  }
  await liveUpdate.setNextBundle({ bundleId: info.version })
  // Evaluate after every async step, immediately before the reload call.
  if (canReloadUpdate(context())) { await liveUpdate.reload(); return true }
  return false
}

export async function pruneWebBundles(liveUpdate, previousBundleId) {
  const { bundleId: current } = await liveUpdate.getCurrentBundle()
  const { bundleId: next } = await liveUpdate.getNextBundle()
  const { bundleIds } = await liveUpdate.getBundles()
  const previous = previousBundleId || bundleIds.filter(id => id !== current && id !== next)
    .sort((a, b) => compareVersions(b, a))[0]
  for (const bundleId of bundleIds) {
    if (![current, previous, next].includes(bundleId)) await liveUpdate.deleteBundle({ bundleId })
  }
}
