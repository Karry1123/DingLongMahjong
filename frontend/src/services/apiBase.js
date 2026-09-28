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
