/// <reference types="vitest" />
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import path from 'path';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  server: {
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        secure: false,
      },
      '/ws': {
        target: 'ws://localhost:8000',
        changeOrigin: true,
        secure: false,
        ws: true,
      },
      '/messages': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        secure: false,
      },
      '/labels': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        secure: false,
      },
      '/models': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        secure: false,
      },
      '/filter': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        secure: false,
      },
      '/stats': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        secure: false,
      },
    },
  },
  test: {
    globals: true,
    environment: 'jsdom',
    setupFiles: './src/test/setup.ts',
  },
});
