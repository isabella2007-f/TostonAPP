import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

const LOCAL_API  = 'http://localhost:8000'
const REMOTE_API = 'https://api-tostonapp.onrender.com'

// Prioridad en dev: backend local si responde; si no, la API en Render.
// Override manual: VITE_API_TARGET=http://localhost:8000 npm run dev
async function pickApiTarget() {
  if (process.env.VITE_API_TARGET) return process.env.VITE_API_TARGET
  try {
    await fetch(`${LOCAL_API}/docs`, { signal: AbortSignal.timeout(800) })
    console.log('[vite] API → backend local (localhost:8000)')
    return LOCAL_API
  } catch {
    console.log('[vite] API → Render (backend local no detectado)')
    return REMOTE_API
  }
}

export default defineConfig(async () => ({
  plugins: [react()],
  base: '/',
  server: {
    proxy: {
      '/api': {
        target: await pickApiTarget(),
        changeOrigin: true,
        secure: true,
      },
    },
  },
  build: {
    chunkSizeWarningLimit: 2000,
    minify: 'esbuild',
    rollupOptions: {
      output: {
        manualChunks: {
          vendor: ['react', 'react-dom', 'react-router-dom'],
          charts: ['recharts'],
          icons: ['lucide-react'],
          map: ['leaflet', 'react-leaflet'],
          pdf: ['jspdf', 'jspdf-autotable'],
          excel: ['xlsx'],
        }
      }
    }
  }
}))
