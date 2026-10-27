import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// Spring Boot owns /api; Vite preserves one origin for sessions and CSRF.
const API = process.env.MONEYFEST_API_URL ?? 'http://127.0.0.1:8080'
const proxied = [
  '/api',
]

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 5173,
    proxy: Object.fromEntries(
      proxied.map((p) => [p, { target: API, changeOrigin: true }]),
    ),
  },
  preview: {
    host: '127.0.0.1',
    port: 4173,
    strictPort: true,
    allowedHosts: ['.trycloudflare.com'],
  },
  build: { outDir: 'dist' },
})
