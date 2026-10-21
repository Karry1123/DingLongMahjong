import { createApp } from 'vue'
import './style.css'
import App from './App.vue'
import { router } from './router/index.js'

export let appReady
if (new URLSearchParams(location.search).get('preview') === 'tiles') {
  import('./components/TileDesignPreview.vue').then(({ default: Preview }) => createApp(Preview).mount('#app'))
} else {
  const app = createApp(App).use(router)
  appReady = router.isReady().then(() => app.mount('#app'))
}
