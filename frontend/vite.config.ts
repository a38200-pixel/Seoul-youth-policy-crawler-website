import react from '@vitejs/plugin-react'
import { defineConfig } from 'vitest/config'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    // 개발 중 CORS 에 의존하지 않도록 /api 를 백엔드(uvicorn)로 프록시한다.
    // 기본은 http://127.0.0.1:8000 이고, 다른 포트의 백엔드를 쓸 때만 환경변수 API_PROXY_TARGET 으로 바꾼다.
    proxy: {
      '/api': { target: process.env.API_PROXY_TARGET ?? 'http://127.0.0.1:8000', changeOrigin: true },
    },
  },
  test: {
    environment: 'jsdom',
    include: ['src/**/*.test.{ts,tsx}'],
  },
})
