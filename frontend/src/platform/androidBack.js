const dismissers = []
export function registerBackDismiss(handler) {
  dismissers.push(handler)
  return () => { const index = dismissers.lastIndexOf(handler); if (index >= 0) dismissers.splice(index, 1) }
}
export function dismissTopLayer() {
  for (const handler of [...dismissers].reverse()) if (handler()) return true
  return false
}
export async function handleAndroidBack({ router, route, exit, confirm = message => globalThis.confirm(message), inGame = false }) {
  if (dismissTopLayer()) return
  // Friend tables already confirm and call /leave in their route guard.
  if (inGame && !route.path.startsWith('/matches/') && !confirm('离开会结束本桌对战，确定离开？')) return
  if (['/home', '/friends', '/records', '/settings', '/login'].includes(route.path)) { await exit(); return }
  if (router.options.history.state.back) router.back()
  else await router.replace('/home')
}
