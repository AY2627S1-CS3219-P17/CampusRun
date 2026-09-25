export type SupplierCategory = 'Food' | 'Drinks' | 'Shopping' | 'Printing'

export type Supplier = {
  name: string
  location: string
  startTime: string
  endTime: string
  type: SupplierCategory
  active: boolean
}

export type CreateSupplierPayload = Omit<Supplier, 'active'>
export type EditSupplierPayload = Omit<Supplier, 'active'>
