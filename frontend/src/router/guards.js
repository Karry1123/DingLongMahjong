export const legacyNotice = '房间号对战已升级为好友邀请'
export const isLegacyPath = path => /^\/pvp(?:\/.*)?$/.test(path)
export function safeRedirect(value) { return typeof value === 'string' && value.startsWith('/') && !value.startsWith('//') && !/^\/(login|register)(?:[/?]|$)/.test(value) ? value : '/home' }
export function loginRedirect(to, loggedIn) { return !loggedIn && !to.meta.public ? { path: '/login', query: { redirect: to.fullPath } } : true }
