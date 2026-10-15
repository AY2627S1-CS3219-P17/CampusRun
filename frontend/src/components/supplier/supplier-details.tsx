// AI Assistance Disclosure:
// Tool: Claude (claude.ai chat, model: Claude Opus 5.5), date: 2026-09-26
// Scope: AI-assisted review and debugging for supplier details dialog: loads one supplier and shows hours, location, map and photo.
// Author review: Validated loading, missing-data, and error states.
// Tool: Codex (OpenAI), date: 2026-10-16
// Scope: Reused the shared NUS-bounded map in read-only mode for supplier details.
// Author review: <to be completed by author>

import { useEffect, useState } from 'react'
import { Dialog } from 'radix-ui'
import { Clock, ExternalLink, MapPin, Navigation, X } from 'lucide-react'
import { ApiError } from '../../api/client'
import { getSupplier } from '../../api/supplier'
import type { Supplier } from '../../types/supplier'
import InteractiveMap from '../shared/interactive-map'
import './update-supplier.css'
import './supplier-details.css'

type Props = {
  supplier: Supplier
  onClose: () => void
}

export default function SupplierDetailsDialog({
  supplier: fromList,
  onClose,
}: Props) {
  const [loaded, setLoaded] = useState<{
    supplier: Supplier | null
    error: string | null
  } | null>(null)

  useEffect(() => {
    const controller = new AbortController()
    getSupplier(fromList.id, controller.signal)
      .then((supplier) => setLoaded({ supplier, error: null }))
      .catch((error: unknown) => {
        if (error instanceof DOMException && error.name === 'AbortError') return
        setLoaded({
          supplier: null,
          error:
            error instanceof ApiError
              ? error.message
              : 'Could not load this supplier.',
        })
      })
    return () => controller.abort()
  }, [fromList.id])

  const supplier = loaded?.supplier ?? fromList
  const mapsLink = `https://www.google.com/maps/search/?api=1&query=${supplier.latitude},${supplier.longitude}`

  return (
    <Dialog.Root open onOpenChange={(open) => !open && onClose()}>
      <Dialog.Portal>
        <Dialog.Overlay className="supplier-dialog-overlay" />
        <Dialog.Content className="supplier-dialog supplier-details">
          <div className="supplier-dialog-heading">
            <Dialog.Title>{supplier.name}</Dialog.Title>
            <Dialog.Close className="supplier-dialog-close" aria-label="Close">
              <X size={20} />
            </Dialog.Close>
          </div>

          <div className="supplier-details-badges">
            <span
              className={`supplier-type supplier-type-${supplier.type.toLowerCase()}`}
            >
              {supplier.type}
            </span>
            {supplier.active ? (
              <span
                className={`supplier-open${supplier.isOpenNow ? ' is-open' : ''}`}
              >
                {supplier.isOpenNow ? 'Open now' : 'Closed now'}
              </span>
            ) : (
              <span className="supplier-details-inactive">Deactivated</span>
            )}
          </div>

          <Dialog.Description className="supplier-details-location">
            <MapPin size={16} aria-hidden="true" />
            <span>
              <strong>{supplier.location}</strong>
              <br />
              {supplier.locationDescription}
            </span>
          </Dialog.Description>

          <p className="supplier-details-hours">
            <Clock size={16} aria-hidden="true" />
            <span>
              Opens {supplier.startTime}, closes {supplier.endTime}
              {supplier.endTime < supplier.startTime && ' (after midnight)'}
            </span>
          </p>
          {loaded?.error && (
            <p className="supplier-dialog-error" role="alert">
              {loaded.error}
            </p>
          )}

          <InteractiveMap
            className="supplier-details-map"
            value={{
              latitude: supplier.latitude,
              longitude: supplier.longitude,
            }}
            ariaLabel={`${supplier.name} location`}
            readOnly
          />

          <a
            className="supplier-details-maps-link"
            href={mapsLink}
            target="_blank"
            rel="noreferrer"
          >
            <Navigation size={15} aria-hidden="true" />
            Open in Google Maps
            <ExternalLink size={13} aria-hidden="true" />
          </a>

          {supplier.imageUrl && (
            <>
              <h3>Image</h3>
              <img
                className="supplier-details-photo"
                src={supplier.imageUrl}
                alt={`Photo of ${supplier.name}`}
                loading="lazy"
              />
            </>
          )}
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  )
}
