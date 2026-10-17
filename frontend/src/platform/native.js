import { TOKEN_KEY } from './web.js'

// Inject plugins so tests require neither a device nor SDK packages.
export function createNativePlatform({ Preferences, ScreenOrientation, App, Haptics, KeepAwake, StatusBar }) {
  let token = '', initialized, writes = Promise.resolve(), owners = 0, orientationOwners = 0
  let wakeOperations = Promise.resolve(), orientationOperations = Promise.resolve()
  const optional = async operation => { try { await operation(); return true } catch { return false } }
  const listen = (event, callback) => {
    let disposed = false
    const handle = Promise.resolve().then(() => App.addListener(event, (...args) => { if (!disposed) callback(...args) }))
    void handle.catch(() => {})
    return () => { if (disposed) return; disposed = true; return handle.then(listener => listener.remove()).catch(() => {}) }
  }
  return {
    secureSession: {
      ready() { return initialized ||= Preferences.get({ key: TOKEN_KEY }).then(result => { token = result.value || '' }) },
      get: () => token,
      set(value) { token = value; writes = writes.catch(() => {}).then(() => Preferences.set({ key: TOKEN_KEY, value })); return writes },
      clear() { token = ''; writes = writes.catch(() => {}).then(() => Preferences.remove({ key: TOKEN_KEY })); return writes },
    },
    orientation: {
      enterTable() {
        if (++orientationOwners > 1) return orientationOperations
        orientationOperations = orientationOperations.then(() => optional(() => ScreenOrientation.lock({ orientation: 'landscape' })))
        return orientationOperations
      },
      leaveTable() {
        if (!orientationOwners || --orientationOwners) return orientationOperations
        orientationOperations = orientationOperations.then(() => optional(() => ScreenOrientation.unlock()))
        return orientationOperations
      },
    },
    lifecycle: { onResume: callback => listen('resume', callback), onPause: callback => listen('pause', callback) },
    backButton: { subscribe: callback => listen('backButton', callback), exit: () => App.exitApp() },
    haptics: { selection: () => optional(async () => {
      await Haptics.selectionStart()
      try { await Haptics.selectionChanged() } finally { await Haptics.selectionEnd() }
    }), impact: () => optional(() => Haptics.impact({ style: 'LIGHT' })) },
    keepAwake: {
      acquire() { if (++owners === 1) wakeOperations = wakeOperations.then(() => optional(() => KeepAwake.keepAwake())); return wakeOperations },
      release() { if (owners && --owners === 0) wakeOperations = wakeOperations.then(() => optional(() => KeepAwake.allowSleep())); return wakeOperations },
    },
    statusBar: { async dark() {
      await optional(() => StatusBar.setStyle({ style: 'DARK' }))
      await optional(() => StatusBar.setBackgroundColor({ color: '#06221D' }))
    } },
  }
}
