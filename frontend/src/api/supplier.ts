import type {
  CreateSupplierPayload,
  EditSupplierPayload,
  Supplier,
} from '../types/supplier'

// All APIs requests to Supplier Service are mocked for now
export async function createSupplier(
  createSupplierPayload: CreateSupplierPayload,
) {
  console.log(createSupplierPayload)
  await new Promise<void>((resolve) => setTimeout(resolve, 500))
  return
}

export async function editSupplier(editSupplierPayload: EditSupplierPayload) {
  console.log(editSupplierPayload)
  await new Promise<void>((resolve) => setTimeout(resolve, 500))
  return
}

// Toggle Activate/Deactivate (soft-delete)
export async function toggleSupplier(isActive: boolean) {
  console.log(isActive)
  await new Promise<void>((resolve) => setTimeout(resolve, 500))
  return
}

// Mock data from supplier-seed-data.csv
export const initialSuppliers: Supplier[] = [
  {
    name: 'Anna x Soup Union',
    location: 'Central Library, Floor 1',
    startTime: '09:00',
    endTime: '18:00',
    type: 'Food',
    active: true,
  },
  {
    name: 'NUS Co-op',
    location: 'Central Library, Floor 1',
    startTime: '09:00',
    endTime: '16:00',
    type: 'Shopping',
    active: true,
  },
  {
    name: 'Printer @ Com 2',
    location: 'Com 2, Floor 1',
    startTime: '00:00',
    endTime: '23:59',
    type: 'Printing',
    active: true,
  },
  {
    name: 'Cool Spot',
    location: 'Com2, Floor 1',
    startTime: '09:00',
    endTime: '21:30',
    type: 'Food',
    active: true,
  },
  {
    name: 'InstaChef',
    location: 'Terrace, Floor 1',
    startTime: '00:00',
    endTime: '23:59',
    type: 'Food',
    active: true,
  },
  {
    name: 'Cafe+ Robot Cafe',
    location: 'Central Library, Floor 1',
    startTime: '00:00',
    endTime: '23:59',
    type: 'Drinks',
    active: true,
  },
  {
    name: 'A Hot Hideout',
    location: 'Prince George Park, Floor 2',
    startTime: '11:00',
    endTime: '21:30',
    type: 'Food',
    active: true,
  },
  {
    name: 'Arise and Shine',
    location: 'Engineering Block E4, Floor 4',
    startTime: '08:00',
    endTime: '18:00',
    type: 'Food',
    active: true,
  },
  {
    name: 'Bakehaus / Aurea',
    location: 'The Ridge, Floor 1',
    startTime: '08:00',
    endTime: '21:00',
    type: 'Food',
    active: true,
  },
  {
    name: 'Central Square @ YIH',
    location: 'Yusof Ishak House, Floor 1',
    startTime: '08:00',
    endTime: '20:00',
    type: 'Food',
    active: true,
  },
  {
    name: 'Pasta Express',
    location: 'Frontier, Floor 1',
    startTime: '09:30',
    endTime: '19:30',
    type: 'Food',
    active: true,
  },
  {
    name: 'TOMORO COFFEE',
    location: 'Hon Sui Sen Memorial Library, Floor 2',
    startTime: '08:15',
    endTime: '18:00',
    type: 'Drinks',
    active: true,
  },
  {
    name: 'Octobox',
    location: 'Prince George Park, Floor 2',
    startTime: '00:00',
    endTime: '23:59',
    type: 'Shopping',
    active: true,
  },
  {
    name: 'Smooy',
    location: 'COM3, Floor 1',
    startTime: '11:00',
    endTime: '21:00',
    type: 'Food',
    active: true,
  },
  {
    name: 'Goh Bros E-Print Pte Ltd',
    location: 'Yusof Ishak House, Floor 5',
    startTime: '09:00',
    endTime: '18:00',
    type: 'Printing',
    active: true,
  },
  {
    name: 'Cheers Unmanned Convenience Store',
    location: 'Engineering Block E3, Floor 4',
    startTime: '00:00',
    endTime: '23:59',
    type: 'Shopping',
    active: true,
  },
  {
    name: 'Nami',
    location: 'innovation4.0, Floor 1',
    startTime: '08:00',
    endTime: '17:30',
    type: 'Food',
    active: true,
  },
  {
    name: 'Supersnacks',
    location: 'Prince George Park, Floor 1',
    startTime: '11:00',
    endTime: '02:00',
    type: 'Food',
    active: true,
  },
  {
    name: 'Good Day Cafe',
    location: 'Medicine+Science Library, Floor 1',
    startTime: '07:30',
    endTime: '18:30',
    type: 'Drinks',
    active: true,
  },
  {
    name: 'The Coffee Roaster',
    location: 'Blk AS8, Floor 1',
    startTime: '08:00',
    endTime: '17:30',
    type: 'Drinks',
    active: true,
  },
  {
    name: 'he by He Brews',
    location: 'Engineering Block EA, Floor 1',
    startTime: '08:00',
    endTime: '17:00',
    type: 'Drinks',
    active: true,
  },
]
