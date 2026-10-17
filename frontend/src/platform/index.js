import { createWebPlatform } from './web.js'
import { createNativePlatform } from './native.js'

export const isNative = () => !!globalThis.Capacitor?.isNativePlatform?.()
export let { secureSession, orientation, lifecycle, backButton, haptics, keepAwake, statusBar } = createWebPlatform()
export async function initializeNative(plugins) {
  if (!isNative()) return
  const platform = createNativePlatform(plugins)
  await platform.secureSession.ready()
  ;({ secureSession, orientation, lifecycle, backButton, haptics, keepAwake, statusBar } = platform)
  await statusBar.dark()
}
