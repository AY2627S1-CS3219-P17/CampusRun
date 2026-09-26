// AI Assistance Disclosure:
// Tool: Claude Code (model: Claude Opus 5.5), date: 2026-09-27
// Scope: AI-added the dev-server proxy that forwards /api to VITE_API_PROXY_TARGET.
// Author review: <to be completed by author>

import react from '@vitejs/plugin-react'
import { defineConfig, loadEnv } from 'vite'

export default defineConfig(({ command, mode }) => {
  // The app calls relative /api/... URLs. Behind the gateway they're same-origin;
  // under `npm run dev` / `npm run preview` this proxy forwards them instead.
  const { VITE_API_PROXY_TARGET: apiProxyTarget } = loadEnv(mode, process.cwd())
  if (command === 'serve' && !apiProxyTarget) {
    throw new Error(
      'Set VITE_API_PROXY_TARGET in frontend/.env (see .env.example), e.g. http://localhost:8080 for the Compose gateway.',
    )
  }

  return {
    plugins: [react()],
    server: {
      // Also used by `vite preview`
      proxy: { '/api': { target: apiProxyTarget, changeOrigin: true } },
    },
  }
})
