import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

const DEV_PORT = parseInt(process.env.LORE_DEV_PORT) || 3000
const API_PORT = parseInt(process.env.LORE_PORT) || 8000

export default defineConfig({
  plugins: [vue()],
  server: {
    port: DEV_PORT,
    watch: {
      usePolling: true,
      interval: 1000,
    },
    proxy: {
      '/api': {
        target: `http://localhost:${API_PORT}`,
        changeOrigin: true,
      },
    },
  },
})
