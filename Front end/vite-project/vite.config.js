// Configuracao do Vite para build/dev server do frontend.
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    // Aceita Host header de qualquer dominio (necessario para tuneis tipo
    // cloudflared/ngrok exporem o frontend pra extensoes externas).
    allowedHosts: true,
  },
  test: {
    globals: true,
    environment: 'happy-dom',
    coverage: {
      provider: 'v8',
      reporter: ['text', 'html', 'lcov'],
      reportsDirectory: './coverage',
      include: [
        'src/utils/**',
        'src/components/AuthModal.jsx',
        'src/lib/supabaseClient.js',
      ],
      thresholds: {
        statements: 90,
        branches: 85,
        functions: 90,
        lines: 90,
      },
    },
  },
})
