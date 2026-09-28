import { createApp } from 'vue'
import './style.css'
import App from './App.vue'

if (new URLSearchParams(location.search).get('preview') === 'tiles') {
  import('./components/TileDesignPreview.vue').then(({ default: Preview }) => createApp(Preview).mount('#app'))
} else {
  createApp(App).mount('#app')
}
