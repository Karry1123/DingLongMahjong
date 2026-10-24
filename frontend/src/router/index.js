import { createRouter, createWebHashHistory } from 'vue-router'
import { auth, restoreAuth, clearAuth } from '../stores/auth.js'
import { clearFriends } from '../stores/friends.js'
import { clearInvitations } from '../stores/invitations.js'
import { clearActiveMatch } from '../stores/activeMatch.js'
import { setUnauthorizedHandler } from '../services/authenticatedFetch.js'
import { isLegacyPath, loginRedirect } from './guards.js'
const view = name => () => import(`../views/${name}.vue`)
const routes = [
 { path: '/', redirect: '/home' },
 { path: '/rules', component: view('RulesGuideView'), meta: { public: true } },
 ...['Login','Register'].map(name => ({ path: `/${name.toLowerCase()}`, component: view(`${name}View`), meta: { public: true } })),
 ...[['/home','Home'],['/friends','Friends'],['/friends/requests','FriendRequests'],['/invite','InviteMatch'],['/records','Records'],['/settings','Settings']].map(([path,name]) => ({ path, component: view(`${name}View`) })),
 { path: '/matches/:id/:phase(waiting|play)', component: () => import('../components/PvpLobby.vue') },
 { path: '/pve', component: { render: () => null } }, { path: '/sandbox', component: { render: () => null } },
 { path: '/:pathMatch(.*)*', redirect: to => isLegacyPath(to.path) ? { path: '/home', query: { upgraded: '1' } } : '/home' },
]
export const router = createRouter({ history: createWebHashHistory(), routes, scrollBehavior: () => ({ top: 0 }) })
setUnauthorizedHandler(() => { clearAuth(); if (!['/login','/register'].includes(router.currentRoute.value.path)) void router.replace({ path:'/login', query: { redirect: router.currentRoute.value.fullPath } }) })
router.beforeEach(async to => {
 if (auth.token && !to.meta.public) {
  try { await restoreAuth() } catch (error) { if (error.status === 401) clearAuth(); else return { path:'/login', query: { redirect:to.fullPath, error:error.message } } }
 }
 return loginRedirect(to, !!auth.token)
})
// Clear account-scoped data immediately when the session changes.
import { watch } from 'vue'
watch(() => auth.token, token => { clearFriends(); clearInvitations(); clearActiveMatch(); if (!token && !router.currentRoute.value.meta.public) void router.replace('/login') }, { flush: 'sync' })
