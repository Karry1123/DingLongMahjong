import { createScreenWakeLock } from '../utils/screenWakeLock.js'

export const TOKEN_KEY = 'dl.auth.token'
export function createWebPlatform(browser = globalThis.window) {
  const storage = () => browser?.localStorage || globalThis.localStorage
  let wakeLock, owners = 0
  const visibility = (active, callback) => {
    const handler = () => { if ((browser.document.visibilityState !== 'hidden') === active) callback() }
    browser?.document?.addEventListener('visibilitychange', handler)
    return () => browser?.document?.removeEventListener('visibilitychange', handler)
  }
  return {
    apkUpdater: { async download() { return null }, async install() {}, async addListener() { return { remove() {} } } },
    secureSession: {
      async ready() {},
      get() { try { return storage()?.getItem(TOKEN_KEY) || '' } catch { return '' } },
      set(token) { storage()?.setItem(TOKEN_KEY, token) },
      clear() { try { storage()?.removeItem(TOKEN_KEY) } catch { /* Storage unavailable. */ } },
    },
    // TableShell's viewport transform remains the fallback on the web.
    orientation: { async enterTable() { return false }, async leaveTable() {} },
    lifecycle: { onResume: callback => visibility(true, callback), onPause: callback => visibility(false, callback) },
    backButton: { subscribe: () => () => {}, async exit() {} },
    haptics: { async selection() {}, async impact() {} },
    keepAwake: {
      async acquire() { if (++owners === 1) { wakeLock = createScreenWakeLock(browser); wakeLock.start() } },
      async release() { if (owners && --owners === 0) { const previous = wakeLock; wakeLock = null; await previous?.stop() } },
    },
    statusBar: { async dark() {}, async enterTable() {}, async leaveTable() {} },
  }
}
