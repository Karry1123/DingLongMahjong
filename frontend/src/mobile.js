import { Capacitor, registerPlugin } from '@capacitor/core'
import { App } from '@capacitor/app'
import { Preferences } from '@capacitor/preferences'
import { ScreenOrientation } from '@capacitor/screen-orientation'
import { KeepAwake } from '@capacitor/keep-awake'
import { Haptics } from '@capacitor/haptics'
import { StatusBar } from '@capacitor/status-bar'
import { LiveUpdate } from '@capawesome/capacitor-live-update'
import { initializeNative } from './platform/index.js'

async function boot() {
  if (Capacitor.isNativePlatform()) await initializeNative({ App, Preferences, ScreenOrientation, KeepAwake, Haptics, StatusBar, ApkUpdater: registerPlugin('ApkUpdater') })
  // Import the auth store and hash router after Preferences has loaded.
  const { appReady } = await import('./main.js')
  await appReady
  if (Capacitor.isNativePlatform()) {
    const { startAppUpdates } = await import('./services/appUpdates.js')
    await startAppUpdates(LiveUpdate)
  }
}
void boot().catch(() => {
  document.getElementById('app').textContent = '应用初始化失败，请关闭后重新打开。'
})
