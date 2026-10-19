// AI Assistance Disclosure:
// Tool: OpenAI Codex (GPT-6), date: 2026-10-17
// Scope: Moved the order autofill response type into the shared types module.
// Tool: Claude Code (model: Claude Opus 5.5), date: 2026-10-19
// Scope: AI-added the errand, list page and list query types, matching the Order Service API, and the create,
//        edit and action request types.
// Author review: <to be completed by author>

export type AutofillSuggestion = {
  title: string | null
  supplier: { id: number; name: string } | null
  building: string | null
  floor: string | null
  description: string | null
  deliveryBy: string | null
  credits: number | null
}

export type ErrandState =
  | 'OPEN'
  | 'ACCEPTED'
  | 'PICKED_UP'
  | 'DELIVERED'
  | 'COMPLETED'
  | 'CANCELLED'
  | 'EXPIRED'

// PENDING: a credit command is on its way and its reply hasn't been applied yet
export type CreditStatus =
  'PENDING' | 'HELD' | 'REJECTED' | 'TRANSFERRED' | 'RELEASED'

export type CancelReason = 'REQUESTER' | 'INSUFFICIENT_CREDITS' | 'NO_WALLET'

// Copied from the Supplier Service when the errand is read; null while it can't be reached
export type ErrandSupplier = {
  id: number
  name: string
  building: string
  floor: string | null
  latitude: number
  longitude: number
  active: boolean
}

export type ErrandLocation = {
  id: number
  name: string
  floor: string | null
  description: string | null
  latitude: number
  longitude: number
  predefined: boolean
}

// As returned by the Order Service. Timestamps are ISO strings.
export type Errand = {
  id: number
  title: string
  state: ErrandState
  creditStatus: CreditStatus
  creditRejection: string | null
  credits: number
  requesterId: number
  requesterName: string | null
  courierId: number | null
  courierName: string | null
  supplierId: number
  supplier: ErrandSupplier | null
  deliveryLocation: ErrandLocation
  deliverBy: string
  // Once delivered, the deadline for the requester to confirm
  expiresAt: string
  cancelReason: CancelReason | null
  createdAt: string
  updatedAt: string
  acceptedAt: string | null
  pickedUpAt: string | null
  deliveredAt: string | null
  completedAt: string | null
  cancelledAt: string | null
  expiredAt: string | null
}

export type ErrandPage = {
  items: Errand[]
  total: number
  page: number
  pageSize: number
  totalPages: number
  // False when the Supplier Service couldn't be reached, so supplier names weren't searched
  supplierSearch: boolean
}

export type ErrandTab = 'active' | 'completed' | 'inactive'

export type ErrandSort =
  'most-recent' | 'least-recent' | 'most-credits' | 'least-credits'

export type ErrandQuery = {
  q: string
  sort: ErrandSort
  page: number
  pageSize: number
}

// A new delivery point of the requester's own; the form doesn't offer the saved locations yet
type NewDeliveryPoint = {
  building: string
  floor?: string | null
  description?: string
  latitude: number
  longitude: number
}

// Leave optional fields out rather than sending empty strings, which fail validation
export type CreateErrandPayload = NewDeliveryPoint & {
  title: string
  supplierId: number
  deliverBy: string
  credits: number
}

// Only the fields sent are changed; a new delivery point sends all of its fields together
export type EditErrandPayload = Partial<CreateErrandPayload>

export type ErrandAction =
  'accept' | 'pickup' | 'deliver' | 'complete' | 'cancel'
