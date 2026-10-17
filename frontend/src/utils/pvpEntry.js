export function nicknameError(value) {
  const name = value.trim()
  const compact = name.normalize('NFKC').replace(/[\s\p{P}\p{S}_]/gu, '')
  if (!compact || /\p{C}/u.test(name)) return '请输入有效昵称'
  if ([...name].length > 6) return '昵称最多 6 个字'
  if (/ai[1-4一二三四](?![0-9])/i.test(compact)) return 'AI 1号至 AI 4号为系统保留昵称，请换一个名字'
  return ''
}

