import { Capacitor } from '@capacitor/core'
import { App } from '@capacitor/app'
import { Preferences } from '@capacitor/preferences'
import { ScreenOrientation } from '@capacitor/screen-orientation'
import { KeepAwake } from '@capacitor/keep-awake'
import { Haptics } from '@capacitor/haptics'
import { StatusBar } from '@capacitor/status-bar'
import { initializeNative } from './platform/index.js'

async function boot() {
  if (Capacitor.isNativePlatform()) await initializeNative({ App, Preferences, ScreenOrientation, KeepAwake, Haptics, StatusBar })
  // Import the auth store and hash router after Preferences has loaded.
  await import('./main.js')
}
void boot().catch(() => {
  document.getElementById('app').textContent = '应用初始化失败，请关闭后重新打开。'
})
