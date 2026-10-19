// AI Assistance Disclosure:
// Tool: Codex (OpenAI), date: 2026-10-16
// Scope: Moved reusable errand toolbar configuration out of the type layer.
// Tool: Claude Code (model: Claude Opus 5.5), date: 2026-10-19
// Scope: AI-removed the pending tab (D4) and typed the options for the Order Service.
// Author review: <to be completed by author>

import type { ErrandSort, ErrandTab } from '../types/order'
import type { ToolbarOption } from '../types/toolbar'

// Errands whose credits are still processing stay in these tabs with a badge; there's no pending tab (D4)
export const ERRAND_TABS: (ToolbarOption & { value: ErrandTab })[] = [
  { value: 'active', label: 'Active' },
  { value: 'completed', label: 'Completed' },
  { value: 'inactive', label: 'Inactive' },
]

export const ERRAND_SORTS: (ToolbarOption & { value: ErrandSort })[] = [
  { value: 'most-recent', label: 'Most recent' },
  { value: 'least-recent', label: 'Least recent' },
  { value: 'most-credits', label: 'Most credits' },
  { value: 'least-credits', label: 'Least credits' },
]

export function toErrandTab(value: string) {
  return ERRAND_TABS.find((option) => option.value === value)?.value
}

export function toErrandSort(value: string) {
  return ERRAND_SORTS.find((option) => option.value === value)?.value
}
