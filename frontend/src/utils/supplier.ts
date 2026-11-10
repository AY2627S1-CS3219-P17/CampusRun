// AI Assistance Disclosure:
// Tool: Codex (OpenAI), date: 2026-10-16
// Scope: Moved reusable supplier category values out of the type layer.
// Author review: I reviewed the code; every import of the category values was updated.

import type { SupplierCategory } from '../types/supplier'

export const SUPPLIER_CATEGORIES: SupplierCategory[] = [
  'Food',
  'Drinks',
  'Shopping',
  'Printing',
]
