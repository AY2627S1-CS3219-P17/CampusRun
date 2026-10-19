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
// Tool: Claude Code (model: Claude Opus 5.5), date: 2026-10-19
// Scope: AI-removed the pending type (credits processing is a badge, not a state) and allowed a missing pickup pin.
// Tool: Claude Code (model: Claude Opus 5.5), date: 2026-10-19
// Scope: AI-replaced the action label and edit flag with a runnable action and the errand to edit; AI-added
//        badges (e.g. credits processing), details notes, and opening the edit dialog from the details.
// Author review: <to be completed by author>

import { useRef, useState } from 'react'
import { CalendarDays, CircleDollarSign, MapPin } from 'lucide-react'
import type { MapPosition } from '../../utils/map'
import type { Errand } from '../../types/order'
import TaskDetailsDialog from './task-details'
import UpdateRequestDialog from './update-request'
import './task-card.css'

export type TaskCardType =
  | 'open'
  | 'accepted'
  | 'picked-up'
  | 'delivered'
  | 'completed'
  | 'cancelled'
  | 'expired'

export type TaskCardBadge = { label: string; tone: 'pending' | 'warning' }
export type TaskCardNote = { text: string; tone: 'info' | 'warning' }
export type TaskCardAction = {
  label: string
  busyLabel: string
  run: () => Promise<unknown>
}

export type TaskCardProps = {
  type: TaskCardType
  title: string
  pickupPoint: string
  supplierName: string
  dropoffPoint: string
  dueBy: string
  credits: number
  userName: string
  // pickup is null while the supplier's details can't be loaded
  pins: { pickup: MapPosition | null; dropoff: MapPosition }
  negative?: boolean
  badges?: TaskCardBadge[]
  // Shown in the details only
  notes?: TaskCardNote[]
  // The details dialog's header button
  action?: TaskCardAction
  // Set when the viewer may edit the errand: shows the edit button and pre-fills the form
  editErrand?: Errand
}

const STATUS_LABELS: Record<TaskCardType, string> = {
  open: 'Open',
  accepted: 'Accepted',
  'picked-up': 'Picked up',
  delivered: 'Delivered',
  completed: 'Completed',
  cancelled: 'Cancelled',
  expired: 'Expired',
}

export default function TaskCard(props: TaskCardProps) {
  const {
    type,
    title,
    pickupPoint,
    dropoffPoint,
    dueBy,
    credits,
    negative,
    badges = [],
    editErrand,
  } = props
  const [detailsOpen, setDetailsOpen] = useState(false)
  // A copy, so a refresh while the form is open doesn't change what it was filled from
  const [editing, setEditing] = useState<Errand | null>(null)
  const openButton = useRef<HTMLButtonElement>(null)

  return (
    <>
      <article className="task-card">
        <h2>
          <button
            className="task-card-open"
            type="button"
            ref={openButton}
            onClick={() => setDetailsOpen(true)}
          >
            {title}
          </button>
        </h2>
        <span className="task-card-badges">
          {badges.map((badge) => (
            <span
              key={badge.label}
              className={`task-card-badge task-card-badge-${badge.tone}`}
            >
              {badge.label}
            </span>
          ))}
          <span className={`task-card-status task-card-status-${type}`}>
            {STATUS_LABELS[type]}
          </span>
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
          onEdit={
            editErrand
              ? () => {
                  setDetailsOpen(false)
                  setEditing(editErrand)
                }
              : undefined
          }
          onClose={() => setDetailsOpen(false)}
        />
      )}
      {editing && (
        <UpdateRequestDialog
          errand={editing}
          onClose={() => setEditing(null)}
          onRestoreFocus={() => openButton.current?.focus()}
        />
      )}
    </>
  )
}
