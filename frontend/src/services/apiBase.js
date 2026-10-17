/** Default to the current origin's Vite proxy; never address the phone's loopback. */
export function resolveApiBase(configured = '', pageOrigin = globalThis.location?.origin) {
  const base = configured.trim().replace(/\/+$/, '')
  if (!base || !pageOrigin) return base
  try {
    const endpoint = new URL(base)
    const page = new URL(pageOrigin)
    const loopback = host => host === 'localhost' || host === '[::1]' || /^127\./.test(host)
    if (loopback(endpoint.hostname) && !loopback(page.hostname)) {
      endpoint.hostname = page.hostname
      endpoint.protocol = page.protocol
      return endpoint.href.replace(/\/+$/, '')
    }
  } catch { /* Relative configurations continue through the same-origin proxy. */ }
  return base
}

/** Native WebViews must never resolve API requests against their own origin. */
export function assertMobileApiBase(configured = '') {
  let endpoint
  try { endpoint = new URL(configured) } catch { throw new Error('App 构建需要 HTTPS 绝对地址 VITE_API_BASE_URL') }
  const host = endpoint.hostname.toLowerCase().replace(/\.$/, '')
  if (endpoint.protocol !== 'https:' || endpoint.username || endpoint.password || endpoint.search || endpoint.hash || host === 'localhost' || host.endsWith('.localhost') || host === '[::1]' || host === '0.0.0.0' || /^127\./.test(host) || host.startsWith('[::ffff:')) {
    throw new Error('App API 必须使用 HTTPS，且不能指向设备 loopback')
  }
  return endpoint.href.replace(/\/+$/, '')
}
