// AI Assistance Disclosure:
// Tool: Codex (OpenAI), date: 2026-10-16
// Scope: Added placeholder task cards, including an Open request in the My Requests Active tab.
// Tool: Codex (OpenAI), date: 2026-10-17
// Scope: Added mock user names and approximate NUS pickup/dropoff map positions for task details.
// Tool: Codex (OpenAI), date: 2026-10-17
// Scope: Added mock supplier names for task details.
// Tool: Codex (OpenAI), date: 2026-10-17
// Scope: Replaced building-like mock suppliers with names from the seeded supplier list.
// Author review: <to be completed by author>

// DELETE WHEN ACTUAL DATA.
// Actual data will certainly not look like this, its just a reference for what is minimally necessary

import type { TaskCardProps } from '../components/shared/task-card'
import type { MapPosition } from './map'

export const SAMPLE_TASK_LOCATIONS: Record<string, MapPosition> = {
  'COM3 Print Shop': { latitude: 1.2946, longitude: 103.7756 },
  'Central Library': { latitude: 1.2966, longitude: 103.7733 },
  'The Deck': { latitude: 1.2949, longitude: 103.7717 },
  UTown: { latitude: 1.3039, longitude: 103.7734 },
  'Cafe+ Robot Cafe': { latitude: 1.2973, longitude: 103.7725 },
  'Engineering Block E4': { latitude: 1.3001, longitude: 103.7722 },
  'NUS Co-op': { latitude: 1.2957, longitude: 103.7707 },
  'University Hall': { latitude: 1.2977, longitude: 103.7782 },
  Frontier: { latitude: 1.2967, longitude: 103.7804 },
  'Science Library': { latitude: 1.296, longitude: 103.7796 },
  "Prince George's Park": { latitude: 1.2907, longitude: 103.7808 },
  'The Terrace': { latitude: 1.3043, longitude: 103.7767 },
}

export const SAMPLE_TASK_CARDS: Record<string, TaskCardProps[]> = {
  pending: [
    {
      type: 'pending',
      title: 'Pick up dinner',
      pickupPoint: 'The Deck', // Supplier building name
      supplierName: 'Pasta Express',
      dropoffPoint: 'UTown', // Delivery building name
      dueBy: '21 Apr, 6:30 PM',
      credits: 8,
      userName: 'Maya Lim',
      pins: {
        pickup: SAMPLE_TASK_LOCATIONS['The Deck'],
        dropoff: SAMPLE_TASK_LOCATIONS.UTown,
      },
    },
  ],
  active: [
    {
      type: 'accepted',
      title: 'Collect printed notes',
      pickupPoint: 'COM3 Print Shop',
      supplierName: 'Printer @ Com 2',
      dropoffPoint: 'Central Library',
      dueBy: '21 Apr, 5:00 PM',
      credits: 10,
      userName: 'Alex Tan',
      pins: {
        pickup: SAMPLE_TASK_LOCATIONS['COM3 Print Shop'],
        dropoff: SAMPLE_TASK_LOCATIONS['Central Library'],
      },
    },
    {
      type: 'picked-up',
      title: 'Deliver coffee',
      pickupPoint: 'Cafe+ Robot Cafe',
      supplierName: 'TOMORO COFFEE',
      dropoffPoint: 'Engineering Block E4',
      dueBy: '21 Apr, 5:30 PM',
      credits: 6,
      userName: 'Jamie Lee',
      pins: {
        pickup: SAMPLE_TASK_LOCATIONS['Cafe+ Robot Cafe'],
        dropoff: SAMPLE_TASK_LOCATIONS['Engineering Block E4'],
      },
    },
    {
      type: 'delivered',
      title: 'Drop off stationery',
      pickupPoint: 'NUS Co-op',
      supplierName: 'Octobox',
      dropoffPoint: 'University Hall',
      dueBy: '21 Apr, 4:45 PM',
      credits: 7,
      userName: 'Sofia Wong',
      pins: {
        pickup: SAMPLE_TASK_LOCATIONS['NUS Co-op'],
        dropoff: SAMPLE_TASK_LOCATIONS['University Hall'],
      },
    },
  ],
  completed: [
    {
      type: 'completed',
      title: 'Pick up lunch',
      pickupPoint: 'Frontier',
      supplierName: 'Jollibee',
      dropoffPoint: 'Science Library',
      dueBy: '20 Apr, 1:00 PM',
      credits: 9,
      userName: 'Ryan Koh',
      pins: {
        pickup: SAMPLE_TASK_LOCATIONS.Frontier,
        dropoff: SAMPLE_TASK_LOCATIONS['Science Library'],
      },
    },
  ],
  inactive: [
    {
      type: 'cancelled',
      title: 'Collect a parcel',
      pickupPoint: 'UTown',
      supplierName: 'FairPrice Xpress @ UTown',
      dropoffPoint: "Prince George's Park",
      dueBy: '19 Apr, 3:00 PM',
      credits: 5,
      userName: 'Nadia Chen',
      pins: {
        pickup: SAMPLE_TASK_LOCATIONS.UTown,
        dropoff: SAMPLE_TASK_LOCATIONS["Prince George's Park"],
      },
    },
    {
      type: 'expired',
      title: 'Pick up a snack',
      pickupPoint: 'The Terrace',
      supplierName: 'Supersnacks',
      dropoffPoint: 'Central Library',
      dueBy: '18 Apr, 2:00 PM',
      credits: 4,
      userName: 'Ethan Goh',
      pins: {
        pickup: SAMPLE_TASK_LOCATIONS['The Terrace'],
        dropoff: SAMPLE_TASK_LOCATIONS['Central Library'],
      },
    },
  ],
}

export const SAMPLE_REQUEST_CARDS: Record<string, TaskCardProps[]> = {
  ...SAMPLE_TASK_CARDS,
  active: [
    {
      type: 'open',
      title: 'Pick up printed notes',
      pickupPoint: 'COM3 Print Shop',
      supplierName: 'Printer @ Com 2',
      dropoffPoint: 'Central Library',
      dueBy: '21 Apr, 5:00 PM',
      credits: 10,
      userName: 'Alex Tan',
      pins: {
        pickup: SAMPLE_TASK_LOCATIONS['COM3 Print Shop'],
        dropoff: SAMPLE_TASK_LOCATIONS['Central Library'],
      },
    },
    ...SAMPLE_TASK_CARDS.active,
  ],
}
