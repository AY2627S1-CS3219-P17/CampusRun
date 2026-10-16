// AI Assistance Disclosure:
// Tool: Codex (OpenAI), date: 2026-10-17
// Scope: Generated a mock task details dialog with status, credits, route, due time, user, actions menu, and two-pin map.
// Tool: Codex (OpenAI), date: 2026-10-17
// Scope: Placed credits beside status and limited settings to Open requests.
// Tool: Codex (OpenAI), date: 2026-10-17
// Scope: Added a supplier row above the pickup-to-dropoff route.
// Tool: Codex (OpenAI), date: 2026-10-17
// Scope: Replaced the Cancel menu trash icon with a Ban icon, preserving its size and color.
// Tool: Codex (OpenAI), date: 2026-10-17
// Scope: Added a conditional header CTA and replaced the Open request settings menu with a direct edit icon.
// Author review: <to be completed by author>

import { Dialog } from 'radix-ui'
import {
  CalendarDays,
  CircleDollarSign,
  MapPin,
  Pencil,
  Store,
  UserRound,
  X,
} from 'lucide-react'
import type { TaskCardProps } from './task-card'
import InteractiveMap from './interactive-map'
import './task-details.css'

type Props = TaskCardProps & {
  statusLabel: string
  onClose: () => void
}

export default function TaskDetailsDialog({
  type,
  title,
  pickupPoint,
  supplierName,
  dropoffPoint,
  dueBy,
  credits,
  userName,
  pins,
  negative = false,
  showEdit = false,
  actionLabel,
  statusLabel,
  onClose,
}: Props) {
  return (
    <Dialog.Root open onOpenChange={(open) => !open && onClose()}>
      <Dialog.Portal>
        <Dialog.Overlay className="task-details-overlay" />
        <Dialog.Content className="task-details">
          <div className="task-details-heading">
            <Dialog.Title>{title}</Dialog.Title>
            {showEdit && (
              <button
                className="task-details-icon-button"
                type="button"
                aria-label="Edit request"
              >
                <Pencil size={16} aria-hidden="true" />
              </button>
            )}
            <div className="task-details-header-actions">
              {actionLabel && (
                <button className="task-details-cta" type="button">
                  {actionLabel}
                </button>
              )}
              <Dialog.Close
                className="task-details-icon-button"
                aria-label="Close"
              >
                <X size={20} aria-hidden="true" />
              </Dialog.Close>
            </div>
          </div>

          <div className="task-details-summary">
            <span
              className={`task-card-status task-card-status-${type}${negative && type === 'open' ? ' task-details-request-open' : ''}`}
            >
              {statusLabel}
            </span>
            <span className="task-details-reward">
              {negative ? '-' : '+'}
              {credits}
              <CircleDollarSign size={20} aria-hidden="true" />
            </span>
          </div>

          <p className="task-details-row">
            <Store size={16} aria-hidden="true" />
            <span>{supplierName}</span>
          </p>
          <Dialog.Description className="task-details-row">
            <MapPin size={16} aria-hidden="true" />
            <span>
              {pickupPoint}&nbsp;&nbsp;&rarr;&nbsp;&nbsp;{dropoffPoint}
            </span>
          </Dialog.Description>
          <p className="task-details-row">
            <CalendarDays size={16} aria-hidden="true" />
            <span>Due {dueBy}</span>
          </p>
          <p className="task-details-row">
            <UserRound size={16} aria-hidden="true" />
            <span>{userName}</span>
          </p>

          <InteractiveMap
            className="task-details-map"
            pins={pins}
            readOnly
            ariaLabel={`Pickup at ${pickupPoint} and dropoff at ${dropoffPoint}`}
          />
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  )
}
