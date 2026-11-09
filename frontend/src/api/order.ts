// AI Assistance Disclosure:
// Tool: OpenAI Codex (GPT-6), date: 2026-10-17
// Scope: Added the authenticated order-service AI autofill API contract and optional request cancellation.
// Tool: Claude Code (model: Claude Opus 5.5), date: 2026-10-19
// Scope: AI-added the Explore, My Requests and My Tasks list calls, and create, edit and the errand actions.
// Tool: Claude Code (model: Claude Opus 5.5), date: 2026-10-20
// Scope: AI-added the predefined delivery location search.
// Tool: Claude Code (model: Claude Opus 5.5), date: 2026-11-10
// Scope: AI-added the admin list of all errands, and listing, adding and editing predefined delivery locations.
// Author review: <to be completed by author>

import { request } from './client'
import type { Page } from '../types/supplier'
import type {
  AdminErrandQuery,
  AutofillSuggestion,
  CreateErrandPayload,
  DeliveryLocation,
  EditErrandPayload,
  Errand,
  ErrandAction,
  ErrandPage,
  ErrandQuery,
  ErrandTab,
  LocationPayload,
  LocationQuery,
} from '../types/order'

// Relative, so it's same-origin behind the gateway; the Vite dev server proxies it (see vite.config.ts)
const ORDER_API_URL = '/api/orders'

export function autofillRequest(description: string, signal?: AbortSignal) {
  return request<AutofillSuggestion>(`${ORDER_API_URL}/autofill`, {
    method: 'POST',
    body: JSON.stringify({ description }),
    signal,
  })
}

// The shared campus list, by name
export function listPredefinedLocations(q: string, signal?: AbortSignal) {
  const params = new URLSearchParams({ predefined: 'true', pageSize: '100' })
  if (q.trim()) params.set('q', q.trim())
  return request<Page<DeliveryLocation>>(
    `${ORDER_API_URL}/delivery-locations?${params}`,
    { signal },
  )
}

// Admin: the predefined list only, active or deactivated
export function listLocations(query: LocationQuery, signal?: AbortSignal) {
  const params = new URLSearchParams({
    predefined: 'true',
    active: String(query.active),
    page: String(query.page),
    pageSize: String(query.pageSize),
  })
  if (query.q.trim()) params.set('q', query.q.trim())
  return request<Page<DeliveryLocation>>(
    `${ORDER_API_URL}/delivery-locations?${params}`,
    { signal },
  )
}

// Admin: adds to the shared campus list
export function createLocation(payload: LocationPayload) {
  return request<DeliveryLocation>(`${ORDER_API_URL}/delivery-locations`, {
    method: 'POST',
    body: JSON.stringify({ ...payload, predefined: true }),
  })
}

// Only the fields sent change; { active } deactivates or reactivates
export function updateLocation(
  id: number,
  changes: Partial<LocationPayload> & { active?: boolean },
) {
  return request<DeliveryLocation>(
    `${ORDER_API_URL}/delivery-locations/${id}`,
    { method: 'PATCH', body: JSON.stringify(changes) },
  )
}

function listParams(query: ErrandQuery, tab?: ErrandTab) {
  const params = new URLSearchParams({
    sort: query.sort,
    page: String(query.page),
    pageSize: String(query.pageSize),
  })

  if (tab) params.set('tab', tab)
  if (query.q.trim()) params.set('q', query.q.trim())
  return params
}

// Explore: OPEN errands from other students that a courier can accept
export function listExplore(query: ErrandQuery, signal?: AbortSignal) {
  return request<ErrandPage>(`${ORDER_API_URL}/?${listParams(query)}`, {
    signal,
  })
}

export function listMyRequests(
  tab: ErrandTab,
  query: ErrandQuery,
  signal?: AbortSignal,
) {
  return request<ErrandPage>(
    `${ORDER_API_URL}/me/requests?${listParams(query, tab)}`,
    { signal },
  )
}

export function listMyTasks(
  tab: ErrandTab,
  query: ErrandQuery,
  signal?: AbortSignal,
) {
  return request<ErrandPage>(
    `${ORDER_API_URL}/me/tasks?${listParams(query, tab)}`,
    { signal },
  )
}

// Admin only: every errand, optionally one requester's or courier's, or in one state
export function listAllErrands(query: AdminErrandQuery, signal?: AbortSignal) {
  const params = listParams(query)
  if (query.state) params.set('state', query.state)
  if (query.requesterId) params.set('requesterId', String(query.requesterId))
  if (query.courierId) params.set('courierId', String(query.courierId))
  return request<ErrandPage>(`${ORDER_API_URL}/admin/errands?${params}`, {
    signal,
  })
}

export function createErrand(payload: CreateErrandPayload) {
  return request<Errand>(`${ORDER_API_URL}/`, {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export function editErrand(id: number, payload: EditErrandPayload) {
  return request<Errand>(`${ORDER_API_URL}/${id}`, {
    method: 'PATCH',
    body: JSON.stringify(payload),
  })
}

// Each returns the errand as it is afterwards
export function runErrandAction(id: number, action: ErrandAction) {
  return request<Errand>(`${ORDER_API_URL}/${id}/${action}`, {
    method: 'POST',
  })
}
