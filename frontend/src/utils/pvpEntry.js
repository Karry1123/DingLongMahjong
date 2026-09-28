export function nicknameError(value) {
  const name = value.trim()
  const compact = name.normalize('NFKC').replace(/[\s\p{P}\p{S}_]/gu, '')
  if (!compact || /\p{C}/u.test(name)) return '请输入有效昵称'
  if ([...name].length > 6) return '昵称最多 6 个字'
  if (/ai[1-4一二三四](?![0-9])/i.test(compact)) return 'AI 1号至 AI 4号为系统保留昵称，请换一个名字'
  return ''
}

export function roomIdError(value) {
  return /^[0-9]{6}$/.test(value.trim()) ? '' : '请输入 6 位数字房间号'
}

export function pvpRoute(hash) {
  const match = /^#\/pvp(?:\/room\/([0-9]{6}))?$/.exec(hash)
  return match ? { roomId: match[1] || '' } : null
}

// randomUUID needs HTTPS; getRandomValues also works for LAN development previews.
export function createVisitorId(cryptoProvider = globalThis.crypto) {
  if (cryptoProvider.randomUUID) return cryptoProvider.randomUUID()
  const bytes = cryptoProvider.getRandomValues(new Uint8Array(16))
  bytes[6] = (bytes[6] & 15) | 64
  bytes[8] = (bytes[8] & 63) | 128
  const hex = [...bytes].map(b => b.toString(16).padStart(2, '0')).join('')
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`
}
