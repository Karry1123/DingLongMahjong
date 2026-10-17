import type { CapacitorConfig } from '@capacitor/cli'

const config: CapacitorConfig = {
  appId: 'com.dinglong.mahjong',
  appName: '顶龙麻将',
  webDir: 'dist-mobile',
  backgroundColor: '#06221D',
  server: { androidScheme: 'https', cleartext: false },
  android: { allowMixedContent: false, backgroundColor: '#06221D' },
  ios: { backgroundColor: '#06221D' },
  plugins: { StatusBar: { style: 'DARK', backgroundColor: '#06221D' } },
}
export default config
