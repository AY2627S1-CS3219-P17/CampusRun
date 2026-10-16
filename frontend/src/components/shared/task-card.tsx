// AI Assistance Disclosure:
// Tool: Codex (OpenAI), date: 2026-10-16
// Scope: Extracted a reusable task card with content props and added status labels and an optional negative credit sign.
// Author review: <to be completed by author>

import { CalendarDays, CircleDollarSign, MapPin } from 'lucide-react'
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
  dropoffPoint: string
  dueBy: string
  credits: number
  negative?: boolean
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

export default function TaskCard({
  type,
  title,
  pickupPoint,
  dropoffPoint,
  dueBy,
  credits,
  negative = false,
}: TaskCardProps) {
  return (
    <article className="task-card">
      <h2>{title}</h2>
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
  )
}
