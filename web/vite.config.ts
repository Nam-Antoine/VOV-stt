import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// PLAN §6: static build, no SSR. Caddy serves web/dist and proxies /api to api:8000.
// In dev, Vite proxies /api itself so the browser sees one origin and the session
// cookie behaves exactly as it will in production.
export default defineConfig({
  plugins: [react()],
  server: {
    host: true,
    port: 5173,
    proxy: {
      '/api': {
        target: process.env.VITE_API_TARGET ?? 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: 'dist',
    sourcemap: true,
  },
})
