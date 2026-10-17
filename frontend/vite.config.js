import vue from '@vitejs/plugin-vue'
import { defineConfig, loadEnv } from 'vite'
import { assertMobileApiBase } from './src/services/apiBase.js'
import { createRequire } from 'node:module'

const { version: appVersion } = createRequire(import.meta.url)('./package.json')

function voiceDataHeaders(server) {
  server.middlewares.use((req, res, next) => {
    if (/\/audio\/data\/[^/?]+\.dat(?:\?|$)/.test(req.url || '')) {
      res.setHeader('Content-Type', 'application/octet-stream')
      res.setHeader('X-Content-Type-Options', 'nosniff')
    }
    next()
  })
}

export default defineConfig(({ command, mode }) => {
  const env = loadEnv(mode, process.cwd(), 'VITE_')
  if (command === 'build' && mode === 'production' && !env.VITE_API_BASE_URL?.trim()) {
    throw new Error('生产构建需要 VITE_API_BASE_URL，例如 https://你的服务.onrender.com')
  }
  const mobile = mode === 'mobile'
  if (command === 'build' && mobile) assertMobileApiBase(env.VITE_API_BASE_URL)
  return {
    define: { __APP_VERSION__: JSON.stringify(appVersion) },
    build: { outDir: mobile ? 'dist-mobile' : 'dist' },
    plugins: [vue(), { name: 'mobile-entry', transformIndexHtml: { order: 'pre', handler: html => mobile ? html.replace('/src/main.js', '/src/mobile.js') : html } }, { name: 'voice-data-headers', configureServer: voiceDataHeaders, configurePreviewServer: voiceDataHeaders }],
    base: mobile ? './' : process.env.NODE_ENV === 'production' ? '/DingLongMahjong/' : '/',
    server: {
      host: '0.0.0.0',
      port: 5173,
      proxy: {
        '/api': { target: 'http://127.0.0.1:8000', changeOrigin: true, ws: true },
        '/health': { target: 'http://127.0.0.1:8000', changeOrigin: true },
      },
    },
    preview: { host:'0.0.0.0' },
  }
})
