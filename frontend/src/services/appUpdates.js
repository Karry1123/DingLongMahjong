import { reactive } from 'vue'
import { router } from '../router/index.js'
import { activeMatch } from '../stores/activeMatch.js'
import { isNative, lifecycle, apkUpdater } from '../platform/index.js'
import { checkForUpdate, updateAction, canReloadUpdate, stageWebUpdate, pruneWebBundles } from '../utils/appUpdate.js'

export const webVersion = typeof __APP_VERSION__ === 'string' ? __APP_VERSION__ : '0.0.0'
export const nativeBuild = typeof __NATIVE_BUILD__ === 'number' ? __NATIVE_BUILD__ : 0
export const appUpdate = reactive({ info: null, action: 'none', checking: false, pending: false,
  message: '', error: '', downloading: false, progress: null, path: '' })
let liveUpdate, checking, localGameGuard = () => true
export function setUpdateGameGuard(guard) { localGameGuard = guard }
const context = () => ({ path: router.currentRoute.value.path,
  inGame: localGameGuard() || !!activeMatch.game || activeMatch.match?.status === 'playing' })

export async function restartUpdate() {
  if (appUpdate.pending && canReloadUpdate(context())) await liveUpdate.reload()
}

export function runUpdateCheck() {
  if (!isNative()) return Promise.resolve()
  if (checking) return checking
  if (appUpdate.downloading) return Promise.resolve()
  checking = (async () => {
    appUpdate.checking = true
    appUpdate.error = ''
    try {
      const info = await checkForUpdate(webVersion)
      if (appUpdate.info?.version !== info?.version && !appUpdate.downloading) appUpdate.path = ''
      appUpdate.info = info
      appUpdate.action = updateAction(webVersion, nativeBuild, info)
      if (appUpdate.action === 'ota') {
        if (!liveUpdate) throw new Error('热更新尚未初始化，请稍后重试')
        await stageWebUpdate(liveUpdate, info, context)
        appUpdate.pending = true
        appUpdate.message = '已下载新版本，重启后生效'
      } else if (appUpdate.action === 'apk') {
        appUpdate.message = '需要安装新版本'
      } else appUpdate.message = appUpdate.pending ? '已下载新版本，重启后生效' : '已是最新'
    } catch (error) { appUpdate.error = `检查失败（${error.message}）`; throw error }
    finally { appUpdate.checking = false; checking = null }
  })()
  return checking
}

export async function installAppUpdate() {
  if (!isNative() || !appUpdate.info || appUpdate.downloading) return
  appUpdate.downloading = true
  appUpdate.error = ''
  let listener
  try {
    listener = await apkUpdater.addListener('downloadProgress', event => { appUpdate.progress = event.progress })
    if (!appUpdate.path) {
      appUpdate.progress = 0
      const result = await apkUpdater.download({ url: appUpdate.info.url })
      appUpdate.path = result.path
    }
    const result = await apkUpdater.install({ path: appUpdate.path })
    appUpdate.message = result?.permissionRequired ? '请允许安装未知应用，返回后将自动打开安装确认' : '请在系统界面确认安装'
  } catch (error) { appUpdate.error = `更新失败（${error.message}）` }
  finally { await listener?.remove(); appUpdate.downloading = false }
}

export async function startAppUpdates(plugin) {
  liveUpdate = plugin
  // Only acknowledge after the Vue application and its initial route mounted.
  const ready = await liveUpdate.ready()
  try { await pruneWebBundles(liveUpdate, ready.previousBundleId) } catch { /* retry next boot */ }
  await apkUpdater.addListener('installError', event => { appUpdate.error = `更新失败（${event.message}）` })
  lifecycle.onResume(() => { void runUpdateCheck().catch(() => {}) })
  router.afterEach(() => { void restartUpdate().catch(() => {}) })
  void runUpdateCheck().catch(() => {})
}
