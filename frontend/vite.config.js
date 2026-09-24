import vue from '@vitejs/plugin-vue'
import { defineConfig, loadEnv } from 'vite'

export default defineConfig(({ command, mode }) => {
  const env = loadEnv(mode, process.cwd(), 'VITE_')
  if (command === 'build' && mode === 'production' && !env.VITE_API_BASE_URL?.trim()) {
    throw new Error('生产构建需要 VITE_API_BASE_URL，例如 https://你的服务.onrender.com')
  }
  return {
    plugins: [vue()],
    server: {
      proxy: {
        '/api': { target: 'http://127.0.0.1:8000', changeOrigin: true },
        '/health': { target: 'http://127.0.0.1:8000', changeOrigin: true },
      },
    },
  }
})
