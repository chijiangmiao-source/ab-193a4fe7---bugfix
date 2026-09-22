import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// During local `npm run dev`, forward API/health calls to the backend.
// In the production image the frontend is served by nginx, which proxies
// /api and /health to the backend container (see nginx.conf).
export default defineConfig({
  plugins: [react()],
  server: {
    host: true,
    port: 5173,
    proxy: {
      '/api': { target: 'http://localhost:8000', changeOrigin: true },
      '/health': { target: 'http://localhost:8000', changeOrigin: true }
    }
  }
})
