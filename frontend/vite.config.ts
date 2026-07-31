import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// The FastAPI app owns the data; Vite only serves the UI in dev and proxies
// everything the API exposes, so the browser sees one origin and the existing
// cookie auth keeps working without CORS.
const API = 'http://127.0.0.1:8000'
// Every backend route prefix the UI touches must be listed here or it 502s in dev.
const proxied = [
  '/portfolio', '/stocks', '/health', '/watchlist', '/universe', '/market',
  '/metrics', '/alerts', '/runs', '/users', '/exposure', '/run_eod',
]

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 5173,
    proxy: Object.fromEntries(
      proxied.map((p) => [p, { target: API, changeOrigin: true }]),
    ),
  },
  build: { outDir: 'dist' },
})
