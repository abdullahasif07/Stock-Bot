import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// In dev, /api is proxied to the FastAPI server so the app is same-origin
// (exactly like production, where FastAPI serves the built SPA).
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': { target: process.env.VITE_DEV_API ?? 'http://localhost:8001', changeOrigin: true },
    },
  },
})
