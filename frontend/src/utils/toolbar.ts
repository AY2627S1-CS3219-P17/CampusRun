// AI Assistance Disclosure:
// Tool: Codex (OpenAI), date: 2026-10-16
// Scope: Moved reusable errand toolbar configuration out of the type layer.
// Author review: <to be completed by author>

import type { ToolbarOption } from '../types/toolbar'

export const ERRAND_TABS: ToolbarOption[] = [
  { value: 'pending', label: 'Pending' },
  { value: 'active', label: 'Active' },
  { value: 'completed', label: 'Completed' },
  { value: 'inactive', label: 'Inactive' },
]

export const ERRAND_SORTS: ToolbarOption[] = [
  { value: 'most-recent', label: 'Most recent' },
  { value: 'least-recent', label: 'Least recent' },
  { value: 'most-credits', label: 'Most credits' },
  { value: 'least-credits', label: 'Least credits' },
]
