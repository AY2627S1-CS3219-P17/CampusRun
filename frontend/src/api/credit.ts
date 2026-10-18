// AI Assistance Disclosure:
// Tool: Claude (claude.ai, model: Claude Opus 5.5), date: 2026-10-17
// Scope: Added the call to the Credit Service's wallet endpoint.
// Author review: <to be completed by author>

import { request } from './client'
import type { Wallet } from '../types/credit'

// Relative, so it's same-origin behind the gateway; the Vite dev server proxies it (see vite.config.ts)
const CREDIT_API_URL = '/api/credits'

// Read-only: balances only change through the credit service's own messages, never from the browser
export function getWallet(signal?: AbortSignal) {
  return request<Wallet>(`${CREDIT_API_URL}/wallets/me`, { signal })
}
