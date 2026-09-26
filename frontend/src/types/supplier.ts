// AI Assistance Disclosure:
// Tool: Claude (claude.ai chat, model: Claude Opus 5.5), date: 2026-09-26
// Scope: AI-modified: types now match the Supplier Service API responses and requests.
// Author review: <to be completed by author>

export type SupplierCategory = 'Food' | 'Drinks' | 'Shopping' | 'Printing'

export const SUPPLIER_CATEGORIES: SupplierCategory[] = [
  'Food',
  'Drinks',
  'Shopping',
  'Printing',
]

// As returned by the Supplier Service
export type Supplier = {
  id: number
  name: string
  type: SupplierCategory
  // "Central Library, Floor 1", made by the service from building and floor
  location: string
  building: string
  floor: string | null
  locationDescription: string
  latitude: number
  longitude: number
  // "09:00"
  startTime: string
  endTime: string
  imageUrl: string | null
  active: boolean
  isOpenNow: boolean
  distanceM: number | null
  createdAt: string
  updatedAt: string
  createdBy: string | null
  updatedBy: string | null
}

export type CreateSupplierPayload = {
  name: string
  type: SupplierCategory
  building: string
  floor: string | null
  locationDescription: string
  latitude: number
  longitude: number
  startTime: string
  endTime: string
  imageUrl: string | null
}

// Only the fields sent are changed
export type EditSupplierPayload = Partial<
  CreateSupplierPayload & { active: boolean }
>

export type SupplierSort =
  'name' | '-name' | 'type' | '-createdAt' | '-updatedAt'

export type SupplierQuery = {
  q: string
  type: SupplierCategory | null
  active: boolean
  sort: SupplierSort
  page: number
  pageSize: number
}

export type Page<T> = {
  items: T[]
  total: number
  page: number
  pageSize: number
  totalPages: number
}
