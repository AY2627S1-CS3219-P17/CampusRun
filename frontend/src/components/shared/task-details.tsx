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
// Tool: Claude Code (model: Claude Opus 5.5), date: 2026-10-19
// Scope: AI-added showing only the dropoff pin when there's no pickup position.
// Tool: Claude Code (model: Claude Opus 5.5), date: 2026-10-19
// Scope: AI-added showing only the dropoff pin when there's no pickup position; AI-wired the header action with
//        busy and error states, the edit button, badges and notes, and the errands-changed event.
// Author review: <to be completed by author>

import { useRef, useState } from 'react'
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
import { ApiError } from '../../api/client'
import { notifyErrandsChanged } from '../../utils/errand-events'
import type { TaskCardProps } from './task-card'
import InteractiveMap from './interactive-map'
import './task-details.css'

type Props = Omit<TaskCardProps, 'editErrand'> & {
  statusLabel: string
  onEdit?: () => void
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
  badges = [],
  notes = [],
  action,
  statusLabel,
  onEdit,
  onClose,
}: Props) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  // Set after a refused action, so the lists reload when the dialog closes
  const refused = useRef(false)

  function close() {
    if (refused.current) notifyErrandsChanged()
    onClose()
  }

  async function handleAction() {
    if (!action || busy) return
    setBusy(true)
    setError('')
    try {
      await action.run()
      // The lists reload, which updates this dialog, or closes it if the errand leaves the list
      notifyErrandsChanged()
    } catch (reason) {
      setError(
        reason instanceof ApiError
          ? reason.message
          : 'Something went wrong. Please try again.',
      )
      // The errand probably changed under the user (409), but reloading now could remove the card, and this
      // dialog with it, before they've read why
      refused.current = true
    } finally {
      setBusy(false)
    }
  }

  return (
    <Dialog.Root open onOpenChange={(open) => !open && close()}>
      <Dialog.Portal>
        <Dialog.Overlay className="task-details-overlay" />
        <Dialog.Content className="task-details" aria-busy={busy}>
          <div className="task-details-heading">
            <Dialog.Title>{title}</Dialog.Title>
            {onEdit && (
              <button
                className="task-details-icon-button"
                type="button"
                aria-label="Edit request"
                onClick={onEdit}
              >
                <Pencil size={16} aria-hidden="true" />
              </button>
            )}
            <div className="task-details-header-actions">
              {action && (
                <button
                  className="task-details-cta"
                  type="button"
                  disabled={busy}
                  onClick={() => {
                    void handleAction()
                  }}
                >
                  {busy ? action.busyLabel : action.label}
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

          {error && (
            <p className="task-details-error" role="alert">
              {error}
            </p>
          )}

          <div className="task-details-summary">
            <span
              className={`task-card-status task-card-status-${type}${negative && type === 'open' ? ' task-details-request-open' : ''}`}
            >
              {statusLabel}
            </span>
            {badges.map((badge) => (
              <span
                key={badge.label}
                className={`task-card-badge task-card-badge-${badge.tone}`}
              >
                {badge.label}
              </span>
            ))}
            <span className="task-details-reward">
              {negative ? '-' : '+'}
              {credits}
              <CircleDollarSign size={20} aria-hidden="true" />
            </span>
          </div>

          {notes.length > 0 && (
            <ul className="task-details-notes">
              {notes.map((note) => (
                <li
                  key={note.text}
                  className={`task-details-note task-details-note-${note.tone}`}
                >
                  {note.text}
                </li>
              ))}
            </ul>
          )}

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

          {pins.pickup ? (
            <InteractiveMap
              className="task-details-map"
              pins={{ pickup: pins.pickup, dropoff: pins.dropoff }}
              readOnly
              ariaLabel={`Pickup at ${pickupPoint} and dropoff at ${dropoffPoint}`}
            />
          ) : (
            <InteractiveMap
              className="task-details-map"
              value={pins.dropoff}
              readOnly
              ariaLabel={`Dropoff at ${dropoffPoint}`}
            />
          )}
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  )
}
