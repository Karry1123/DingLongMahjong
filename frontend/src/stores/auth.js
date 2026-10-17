import { reactive } from 'vue'
import * as session from '../platform/secureSession.js'
import * as api from '../services/authApi.js'
export const auth = reactive({ token: session.get(), user: null, restored: false })
let restoring
export function clearAuth() {
  const clearing = Promise.resolve(session.clear())
  void clearing.catch(() => {})
  auth.token = ''; auth.user = null; auth.restored = false
  return clearing
}
export function saveAuth(result) {
  const persist = session.set(result.token)
  const apply = () => { auth.token = result.token; auth.user = result.user; auth.restored = true; return result.user }
  return persist?.then ? persist.then(apply) : apply()
}
export async function restoreAuth() {
  if (!auth.token) return false
  if (auth.restored) return true
  if (!restoring) restoring = api.getMe().then(user => { auth.user = user; auth.restored = true; return true }).finally(() => { restoring = null })
  return restoring
}
export async function signOut() { try { await api.logout() } finally { await clearAuth() } }
