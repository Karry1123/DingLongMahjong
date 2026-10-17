import { secureSession } from './index.js'
export { TOKEN_KEY } from './web.js'
export const get = () => secureSession.get()
export const set = token => secureSession.set(token)
export const clear = () => secureSession.clear()
