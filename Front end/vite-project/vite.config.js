// Configuracao do Vite para build/dev server do frontend.
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  build: {
    rollupOptions: {
      output: {
        // Bibliotecas em chunks proprios: mudanca no codigo do app nao
        // invalida o cache delas no navegador (antes: 1 arquivo de 628 KB).
        manualChunks(id) {
          if (!id.includes('node_modules')) return undefined
          if (id.includes('@supabase')) return 'vendor-supabase'
          if (/[\\/](react-bootstrap|bootstrap|@restart|@popperjs|react-bootstrap-icons)[\\/]/.test(id)) return 'vendor-bootstrap'
          if (/[\\/](react|react-dom|scheduler)[\\/]/.test(id)) return 'vendor-react'
          return 'vendor'
        },
      },
    },
  },
  server: {
    // Bind em 0.0.0.0 pra ser acessivel de fora do container.
    host: true,
    // Aceita Host header de qualquer dominio (necessario para tuneis tipo
    // cloudflared/ngrok exporem o frontend pra extensoes externas).
    allowedHosts: true,
    // Em Docker no Windows o inotify do bind mount nao propaga; usa polling
    // pra o hot-reload funcionar. Ligado so quando VITE_DOCKER=1 (compose).
    watch: process.env.VITE_DOCKER
      ? { usePolling: true, interval: 300 }
      : undefined,
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
