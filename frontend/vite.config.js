import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Fejlesztéshez: IKON_API_TARGET=https://... csak olvasásra; nem GET kérést ilyenkor a proxy elutasít.
const target = process.env.IKON_API_TARGET || 'http://localhost:8000'
const readOnly = !!process.env.IKON_API_TARGET
const proxyOpts = {
  target, changeOrigin: true,
  configure: (proxy) => {
    if (!readOnly) return
    proxy.on('proxyReq', (req, _r, res) => { if (req.method !== 'GET') { req.destroy(); res.writeHead?.(403); res.end?.('csak olvasás') } })
  },
}

export default defineConfig({
  plugins: [react()],
  server: {
    port: parseInt(process.env.PORT || '3000'),
    proxy: {
      '/api': proxyOpts,
      '/health': proxyOpts,
    },
  },
  build: {
    target: 'esnext',
    minify: 'esbuild',
    rollupOptions: {
      output: {
        manualChunks: { d3: ['d3'] },
      },
    },
  },
})
