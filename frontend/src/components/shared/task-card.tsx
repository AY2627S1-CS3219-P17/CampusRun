// AI Assistance Disclosure:
// Tool: Codex (OpenAI), date: 2026-10-16
// Scope: Extracted a reusable task card with content props and added status labels and an optional negative credit sign.
// Tool: Codex (OpenAI), date: 2026-10-17
// Scope: Added a clickable task details preview carrying card fields, user, and mock map pins into a dialog.
// Tool: Codex (OpenAI), date: 2026-10-17
// Scope: Kept the mock user in details only and exposed settings only when the parent marks an Open request editable.
// Tool: Codex (OpenAI), date: 2026-10-17
// Scope: Passed a distinct supplier name into the details view.
// Tool: Codex (OpenAI), date: 2026-10-17
// Scope: Passed optional page-specific task action labels and edit availability into the details dialog.
// Tool: Codex (OpenAI), date: 2026-10-17
// Scope: Simplified task prop forwarding and removed an unnecessary action-label union.
// Author review: <to be completed by author>

import { useState } from 'react'
import { CalendarDays, CircleDollarSign, MapPin } from 'lucide-react'
import type { MapPosition } from '../../utils/map'
import TaskDetailsDialog from './task-details'
import './task-card.css'

export type TaskCardType =
  | 'open'
  | 'pending'
  | 'accepted'
  | 'picked-up'
  | 'delivered'
  | 'completed'
  | 'cancelled'
  | 'expired'

export type TaskCardProps = {
  type: TaskCardType
  title: string
  pickupPoint: string
  supplierName: string
  dropoffPoint: string
  dueBy: string
  credits: number
  userName: string
  pins: { pickup: MapPosition; dropoff: MapPosition }
  negative?: boolean
  showEdit?: boolean
  actionLabel?: string
}

const STATUS_LABELS: Record<TaskCardType, string> = {
  open: 'Open',
  pending: 'Pending',
  accepted: 'Accepted',
  'picked-up': 'Picked up',
  delivered: 'Delivered',
  completed: 'Completed',
  cancelled: 'Cancelled',
  expired: 'Expired',
}

export default function TaskCard(props: TaskCardProps) {
  const { type, title, pickupPoint, dropoffPoint, dueBy, credits, negative } =
    props
  const [detailsOpen, setDetailsOpen] = useState(false)

  return (
    <>
      <article className="task-card">
        <h2>
          <button
            className="task-card-open"
            type="button"
            onClick={() => setDetailsOpen(true)}
          >
            {title}
          </button>
        </h2>
        <span className={`task-card-status task-card-status-${type}`}>
          {STATUS_LABELS[type]}
        </span>
        <p className="task-card-location">
          <MapPin size={16} aria-hidden="true" />
          <span>
            {pickupPoint}&nbsp;&nbsp;&rarr;&nbsp;&nbsp;{dropoffPoint}
          </span>
        </p>
        <p className="task-card-due">
          <CalendarDays size={16} aria-hidden="true" />
          <span>Due {dueBy}</span>
        </p>
        <span className="task-card-reward">
          <span>
            {negative ? '-' : '+'}
            {credits}
          </span>
          <CircleDollarSign size={20} aria-hidden="true" />
        </span>
      </article>
      {detailsOpen && (
        <TaskDetailsDialog
          {...props}
          statusLabel={STATUS_LABELS[type]}
          onClose={() => setDetailsOpen(false)}
        />
      )}
    </>
  )
}
