// AI Assistance Disclosure:
// Tool: Claude Code (model: Claude Opus 5.5), date: 2026-10-19
// Scope: AI-generated mapper from an Order Service errand to the task card's props, and the due date format;
//        AI-added who can do what (the action, edit, badges and notes on each card).
// Author review: <to be completed by author>

import { runErrandAction } from '../api/order'
import type {
  TaskCardBadge,
  TaskCardNote,
  TaskCardProps,
  TaskCardType,
} from '../components/shared/task-card'
import type {
  CancelReason,
  Errand,
  ErrandAction,
  ErrandState,
} from '../types/order'

// Whose list the card is in: Explore and My Tasks name the requester, My Requests names the courier
export type ErrandViewer = 'explore' | 'requester' | 'courier'

const CARD_TYPES: Record<ErrandState, TaskCardType> = {
  OPEN: 'open',
  ACCEPTED: 'accepted',
  PICKED_UP: 'picked-up',
  DELIVERED: 'delivered',
  COMPLETED: 'completed',
  CANCELLED: 'cancelled',
  EXPIRED: 'expired',
}

export const SUPPLIER_UNAVAILABLE = 'Supplier details unavailable'
const UNKNOWN_USER = 'Unknown user'

const DUE_FORMAT = new Intl.DateTimeFormat('en-GB', {
  day: 'numeric',
  month: 'short',
  hour: 'numeric',
  minute: '2-digit',
  // Always 12:30 AM, never 0:30 AM
  hourCycle: 'h12',
})

// "21 Apr, 5:00 PM"
export function formatDue(iso: string) {
  const parts = Object.fromEntries(
    DUE_FORMAT.formatToParts(new Date(iso)).map(({ type, value }) => [
      type,
      value,
    ]),
  )
  return `${parts.day} ${parts.month}, ${parts.hour}:${parts.minute} ${parts.dayPeriod.toUpperCase()}`
}

function otherParty(errand: Errand, viewer: ErrandViewer) {
  if (viewer !== 'requester') return errand.requesterName ?? UNKNOWN_USER
  if (errand.courierId === null) return 'Waiting for a courier'
  return errand.courierName ?? UNKNOWN_USER
}

const ENDED: ErrandState[] = ['COMPLETED', 'CANCELLED', 'EXPIRED']

const CANCEL_REASONS: Record<CancelReason, string> = {
  REQUESTER: 'Cancelled by the requester.',
  INSUFFICIENT_CREDITS:
    "Cancelled: there weren't enough credits to reserve the reward.",
  NO_WALLET: "Cancelled: the requester's credits weren't set up yet.",
}

// Only the Credit Service refusals a user can act on; the rest are retries the services sort out themselves
const CREDIT_REJECTIONS: Record<string, string> = {
  INSUFFICIENT_CREDITS:
    "There weren't enough credits for the new reward, so it wasn't changed.",
  NO_COURIER_WALLET:
    "The courier's credits aren't set up yet, so the payment will be retried.",
}

const ACTIONS: Record<ErrandAction, { label: string; busyLabel: string }> = {
  accept: { label: 'Accept', busyLabel: 'Accepting...' },
  pickup: { label: 'Picked up', busyLabel: 'Saving...' },
  deliver: { label: 'Delivered', busyLabel: 'Saving...' },
  complete: { label: 'Completed', busyLabel: 'Completing...' },
  cancel: { label: 'Cancel', busyLabel: 'Cancelling...' },
}

// The same rules the Order Service enforces; it still has the final say (409)
function allowedAction(
  errand: Errand,
  viewer: ErrandViewer,
  userId: string | null,
  now: number,
): ErrandAction | null {
  const beforeDeadline = new Date(errand.deliverBy).getTime() > now

  if (viewer === 'explore') {
    // A deactivated supplier can't be accepted (D13); an unknown one (null) still can
    const acceptable =
      errand.state === 'OPEN' &&
      errand.creditStatus === 'HELD' &&
      errand.supplier?.active !== false &&
      String(errand.requesterId) !== userId
    return acceptable && beforeDeadline ? 'accept' : null
  }

  if (viewer === 'courier') {
    if (String(errand.courierId) !== userId || !beforeDeadline) return null
    if (errand.state === 'ACCEPTED') return 'pickup'
    if (errand.state === 'PICKED_UP') return 'deliver'
    return null
  }

  if (String(errand.requesterId) !== userId) return null
  // Any credit status (D1); the reserve's reply is handled either way
  if (errand.state === 'OPEN') return 'cancel'
  // expiresAt is deliverBy plus the grace period once delivered (D2)
  if (
    errand.state === 'DELIVERED' &&
    new Date(errand.expiresAt).getTime() > now
  )
    return 'complete'
  return null
}

function badgesFor(errand: Errand): TaskCardBadge[] {
  const badges: TaskCardBadge[] = []
  if (errand.creditStatus === 'PENDING')
    badges.push({ label: 'Credits processing', tone: 'pending' })
  if (errand.supplier?.active === false && !ENDED.includes(errand.state))
    badges.push({ label: 'Supplier unavailable', tone: 'warning' })
  return badges
}

function notesFor(errand: Errand, viewer: ErrandViewer): TaskCardNote[] {
  const notes: TaskCardNote[] = []

  if (errand.cancelReason)
    notes.push({ text: CANCEL_REASONS[errand.cancelReason], tone: 'warning' })

  if (viewer === 'requester') {
    if (errand.state === 'OPEN' && errand.supplier?.active === false)
      notes.push({
        text: 'This supplier is no longer available, so no courier can accept this request. Cancel it to get your credits back.',
        tone: 'warning',
      })
    if (errand.state === 'DELIVERED')
      notes.push({
        text: `Confirm you've received it by ${formatDue(errand.expiresAt)}.`,
        tone: 'info',
      })
  }

  const rejection = errand.creditRejection
  if (
    viewer !== 'explore' &&
    errand.state !== 'CANCELLED' &&
    rejection &&
    rejection in CREDIT_REJECTIONS
  )
    notes.push({ text: CREDIT_REJECTIONS[rejection], tone: 'warning' })

  return notes
}

export function toTaskCard(
  errand: Errand,
  viewer: ErrandViewer,
  userId: string | null,
  now = Date.now(),
): TaskCardProps {
  const { supplier, deliveryLocation } = errand
  const action = allowedAction(errand, viewer, userId, now)
  const editable =
    viewer === 'requester' &&
    String(errand.requesterId) === userId &&
    errand.state === 'OPEN' &&
    errand.creditStatus === 'HELD' &&
    new Date(errand.deliverBy).getTime() > now

  return {
    type: CARD_TYPES[errand.state],
    title: errand.title,
    // supplier is null while the Supplier Service can't be reached
    pickupPoint: supplier?.building ?? SUPPLIER_UNAVAILABLE,
    supplierName: supplier?.name ?? SUPPLIER_UNAVAILABLE,
    dropoffPoint: deliveryLocation.name,
    dueBy: formatDue(errand.deliverBy),
    credits: errand.credits,
    userName: otherParty(errand, viewer),
    pins: {
      pickup: supplier
        ? { latitude: supplier.latitude, longitude: supplier.longitude }
        : null,
      dropoff: {
        latitude: deliveryLocation.latitude,
        longitude: deliveryLocation.longitude,
      },
    },
    // The requester pays the reward
    negative: viewer === 'requester',
    badges: badgesFor(errand),
    notes: notesFor(errand, viewer),
    action: action
      ? {
          ...ACTIONS[action],
          run: () => runErrandAction(errand.id, action),
        }
      : undefined,
    // OPEN with its credits HELD (D10)
    editErrand: editable ? errand : undefined,
  }
}
