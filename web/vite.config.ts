import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig({
  plugins: [tailwindcss(), react()],
  server: {
    allowedHosts: true,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        // Preserve the browser host so Django's same-origin CSRF check sees the
        // same localhost origin on both sides of the development proxy.
        changeOrigin: false,
      },
    },
  },
})
