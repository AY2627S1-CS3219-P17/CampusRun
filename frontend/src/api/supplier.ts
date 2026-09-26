// AI Assistance Disclosure:
// Tool: Claude (claude.ai chat, model: Claude Opus 5.5), date: 2026-09-26
// Scope: AI-modified: the mocked calls and hard-coded supplier list are replaced with calls to the Supplier Service.
// Author review: <to be completed by author>

import { request } from './client'
import type {
  CreateSupplierPayload,
  EditSupplierPayload,
  Page,
  Supplier,
  SupplierQuery,
} from '../types/supplier'

const SUPPLIER_API_URL =
  (import.meta.env.VITE_SUPPLIER_API_URL as string | undefined) ??
  'http://localhost:8002'

export function listSuppliers(query: SupplierQuery, signal?: AbortSignal) {
  const params = new URLSearchParams({
    active: String(query.active),
    sort: query.sort,
    page: String(query.page),
    pageSize: String(query.pageSize),
  })
  if (query.q.trim()) params.set('q', query.q.trim())
  if (query.type) params.set('type', query.type)
  return request<Page<Supplier>>(`${SUPPLIER_API_URL}/suppliers?${params}`, {
    signal,
  })
}

export function getSupplier(id: number, signal?: AbortSignal) {
  return request<Supplier>(`${SUPPLIER_API_URL}/suppliers/${id}`, { signal })
}

export function createSupplier(createSupplierPayload: CreateSupplierPayload) {
  return request<Supplier>(`${SUPPLIER_API_URL}/suppliers`, {
    method: 'POST',
    body: JSON.stringify(createSupplierPayload),
  })
}

export function editSupplier(
  id: number,
  editSupplierPayload: EditSupplierPayload,
) {
  return request<Supplier>(`${SUPPLIER_API_URL}/suppliers/${id}`, {
    method: 'PATCH',
    body: JSON.stringify(editSupplierPayload),
  })
}

// Activate/Deactivate. Deactivated suppliers are hidden from students but kept.
export function toggleSupplier(id: number, isActive: boolean) {
  return editSupplier(id, { active: isActive })
}

// Removes the supplier for everyone. The service keeps the record for past errands.
export function deleteSupplier(id: number) {
  return request<void>(`${SUPPLIER_API_URL}/suppliers/${id}`, {
    method: 'DELETE',
  })
}
