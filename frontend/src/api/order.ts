// AI Assistance Disclosure:
// Tool: OpenAI Codex (GPT-6), date: 2026-10-17
// Scope: Added the authenticated order-service AI autofill API contract and optional request cancellation.
// Author review: <to be completed by author>

import { request } from './client'
import type { AutofillSuggestion } from '../types/order'

export function autofillRequest(description: string, signal?: AbortSignal) {
  return request<AutofillSuggestion>('/api/orders/autofill', {
    method: 'POST',
    body: JSON.stringify({ description }),
    signal,
  })
}
