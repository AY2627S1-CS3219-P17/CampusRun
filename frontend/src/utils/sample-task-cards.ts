// AI Assistance Disclosure:
// Tool: Codex (OpenAI), date: 2026-10-16
// Scope: Added placeholder task cards, including an Open request in the My Requests Active tab.
// Author review: <to be completed by author>

// DELETE WHEN ACTUAL DATA.

import type { TaskCardProps } from '../components/shared/task-card'

export const SAMPLE_TASK_CARDS: Record<string, TaskCardProps[]> = {
  pending: [
    {
      type: 'pending',
      title: 'Pick up dinner',
      pickupPoint: 'The Deck',
      dropoffPoint: 'UTown',
      dueBy: '21 Apr, 6:30 PM',
      credits: 8,
    },
  ],
  active: [
    {
      type: 'accepted',
      title: 'Collect printed notes',
      pickupPoint: 'COM3 Print Shop',
      dropoffPoint: 'Central Library',
      dueBy: '21 Apr, 5:00 PM',
      credits: 10,
    },
    {
      type: 'picked-up',
      title: 'Deliver coffee',
      pickupPoint: 'Cafe+ Robot Cafe',
      dropoffPoint: 'Engineering Block E4',
      dueBy: '21 Apr, 5:30 PM',
      credits: 6,
    },
    {
      type: 'delivered',
      title: 'Drop off stationery',
      pickupPoint: 'NUS Co-op',
      dropoffPoint: 'University Hall',
      dueBy: '21 Apr, 4:45 PM',
      credits: 7,
    },
  ],
  completed: [
    {
      type: 'completed',
      title: 'Pick up lunch',
      pickupPoint: 'Frontier',
      dropoffPoint: 'Science Library',
      dueBy: '20 Apr, 1:00 PM',
      credits: 9,
    },
  ],
  inactive: [
    {
      type: 'cancelled',
      title: 'Collect a parcel',
      pickupPoint: 'UTown',
      dropoffPoint: "Prince George's Park",
      dueBy: '19 Apr, 3:00 PM',
      credits: 5,
    },
    {
      type: 'expired',
      title: 'Pick up a snack',
      pickupPoint: 'The Terrace',
      dropoffPoint: 'Central Library',
      dueBy: '18 Apr, 2:00 PM',
      credits: 4,
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
      dropoffPoint: 'Central Library',
      dueBy: '21 Apr, 5:00 PM',
      credits: 10,
    },
    ...SAMPLE_TASK_CARDS.active,
  ],
}
