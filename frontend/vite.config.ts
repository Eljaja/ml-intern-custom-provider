import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  server: {
    // 5173 often collides on Windows (another process on [::1]:5173 — e.g. IDE), so localhost:5173 404s while 127.0.0.1 works.
    port: 5174,
    strictPort: false,
    proxy: {
      '/api': {
        target: 'http://localhost:7860',
        changeOrigin: true,
        ws: true, // Proxy WebSocket connections (/api/ws/...)
      },
      '/auth': {
        target: 'http://localhost:7860',
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: 'dist',
    sourcemap: false,
  },
})
