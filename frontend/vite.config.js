import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// Tailwind v4 is a Vite plugin — there is no tailwind.config.js and no
// postcss.config.js. If your team installs Tailwind v3 instead, remove
// the tailwindcss() plugin here and follow the v3 PostCSS setup; the
// README explains the difference.

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 5173,

    // Deliberately left commented out. With the proxy OFF, the browser
    // calls Flask on a different port and a real CORS request happens —
    // which is what we actually want to prove. Uncomment only if the
    // team decides to avoid CORS entirely in development.
    //
    // proxy: {
    //   '/api': { target: 'http://localhost:5001', changeOrigin: true },
    // },
  },

   test: {  environment: 'jsdom',
            globals: true,
            setupFiles: './src/setupTests.js',
            css: false,
            coverage: { provider: 'v8',
                        reporter: ['text', 'html', 'lcov'],
                        reportsDirectory: './coverage',
                        include: ['src/**/*.{js,jsx}'],
                        exclude: ['src/main.jsx',
                                  'src/setupTests.js',
                                  'src/test/**',
                                  'src/**/*.test.{js,jsx}',],
                        },
           },
})
