/// <reference types="vitest" />
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import path from 'path';

const apiTarget = (process.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000').replace(
  '//localhost:',
  '//127.0.0.1:'
);

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: apiTarget,
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ''),
      },
      '^/(context|strategy|portfolio|agent-runs|risk|execution|orders|monitoring|workflow|workflow-state|cycle|run-cycle|health|pnl|decision-trail|debug|analyze)': {
        target: apiTarget,
        changeOrigin: true,
      },
    },
  },
  test: {
    globals: true,
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.ts'],
  },
});
