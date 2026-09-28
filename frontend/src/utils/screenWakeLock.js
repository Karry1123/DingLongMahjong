/** One sentinel per page, including visibility/focus recovery and in-flight disposal. */
export function createScreenWakeLock(browser = globalThis.window, onStatus = () => {}) {
  let sentinel, pending, disposed = false, started = false
  async function request() {
    if (disposed || browser?.document?.visibilityState === 'hidden') return false
    if (!browser?.navigator?.wakeLock?.request) { onStatus('unsupported'); return false }
    if (sentinel && !sentinel.released) return true
    if (pending) return pending
    pending = (async () => {
      try {
        const lock = await browser.navigator.wakeLock.request('screen')
        if (disposed || browser.document.visibilityState === 'hidden') { await lock.release(); return false }
        sentinel = lock
        lock.addEventListener('release', () => { if (sentinel === lock) { sentinel = null; onStatus('released') } })
        onStatus('active')
        return true
      } catch { onStatus('unavailable'); return false }
    })()
    try { return await pending } finally { pending = null }
  }
  const recover = () => { void request() }
  function start() {
    if (started || disposed) return
    started = true
    browser?.document?.addEventListener('visibilitychange', recover)
    browser?.addEventListener('focus', recover)
    browser?.document?.addEventListener('pointerdown', recover, { passive:true })
    recover()
  }
  async function stop() {
    disposed = true
    browser?.document?.removeEventListener('visibilitychange', recover)
    browser?.removeEventListener('focus', recover)
    browser?.document?.removeEventListener('pointerdown', recover)
    const lock = sentinel; sentinel = null
    try { await lock?.release() } catch { /* Page teardown must not throw. */ }
  }
  return { request, start, stop }
}
