// AI Assistance Disclosure:
// Tool: Claude Code (model: Claude Opus 5.5), date: 2026-11-10
// Scope: AI-generated the admin page's Delivery locations tab: the predefined locations, active or deactivated, with
//        search and pages, and opening the form to add or edit one.
// Author review: I verified the UI: the Delivery locations tab lists active and inactive locations and opens the form.

import { useEffect, useMemo, useState } from 'react'
import { MapPin, Pencil } from 'lucide-react'
import LocationForm from './location-form'
import Pagination from '../shared/pagination'
import Toolbar from '../shared/toolbar'
import { ApiError } from '../../api/client'
import { listLocations } from '../../api/order'
import type { Page } from '../../types/supplier'
import type { DeliveryLocation, LocationQuery } from '../../types/order'
import type { ToolbarOption } from '../../types/toolbar'

const PAGE_SIZE = 10

const STATUS_TABS: ToolbarOption[] = [
  { value: 'active', label: 'Active' },
  { value: 'deactivated', label: 'Deactivated' },
]

// The form: { location } edits one, {} adds a new one
type Editor = { location?: DeliveryLocation }

function messageOf(error: unknown) {
  return error instanceof ApiError
    ? error.message
    : 'Something went wrong. Please try again.'
}

export default function AdminLocations() {
  const [active, setActive] = useState(true)
  const [query, setQuery] = useState('')
  const [debouncedQuery, setDebouncedQuery] = useState('')
  const [page, setPage] = useState(1)
  const [reloadKey, setReloadKey] = useState(0)
  const [editor, setEditor] = useState<Editor | null>(null)
  const [notice, setNotice] = useState('')
  const [result, setResult] = useState<{
    key: string
    data: Page<DeliveryLocation> | null
    error: string | null
  } | null>(null)

  useEffect(() => {
    const timeout = setTimeout(() => setDebouncedQuery(query), 300)
    return () => clearTimeout(timeout)
  }, [query])

  const locationsQuery = useMemo<LocationQuery>(
    () => ({ q: debouncedQuery, active, page, pageSize: PAGE_SIZE }),
    [debouncedQuery, active, page],
  )
  const requestKey = `${JSON.stringify(locationsQuery)}#${reloadKey}`

  useEffect(() => {
    const controller = new AbortController()
    listLocations(locationsQuery, controller.signal)
      .then((data) => {
        // The page emptied, e.g. after deactivating its last location
        if (data.totalPages > 0 && locationsQuery.page > data.totalPages) {
          setPage(data.totalPages)
          return
        }
        setResult({ key: requestKey, data, error: null })
      })
      .catch((error: unknown) => {
        if (error instanceof DOMException && error.name === 'AbortError') return
        setResult({ key: requestKey, data: null, error: messageOf(error) })
      })
    return () => controller.abort()
  }, [requestKey, locationsQuery])

  const loading = result?.key !== requestKey
  const data = result?.data ?? null
  const loadError = !loading ? (result?.error ?? null) : null

  function updateStatus(value: string) {
    setActive(value !== 'deactivated')
    setPage(1)
    setNotice('')
  }

  function handleSave(saved: DeliveryLocation) {
    const before = editor?.location
    if (!before) {
      setNotice(`Added ${saved.name}.`)
      // Show it where it now is
      setActive(true)
      setQuery('')
      setDebouncedQuery('')
      setPage(1)
    } else if (before.active !== saved.active) {
      setNotice(
        `${saved.name} is ${saved.active ? 'active again' : 'deactivated'}.`,
      )
    } else {
      setNotice(`Saved ${saved.name}.`)
    }
    setReloadKey((key) => key + 1)
  }

  return (
    <section className="supplier-directory" aria-label="Delivery locations">
      <Toolbar
        tabs={{
          options: STATUS_TABS,
          value: active ? 'active' : 'deactivated',
          onChange: updateStatus,
          label: 'Delivery location status',
        }}
        search={{
          value: query,
          onChange: (value) => {
            setQuery(value)
            setPage(1)
          },
          placeholder: 'Search by name or description',
          label: 'Search delivery locations by name or description',
          maxLength: 100,
        }}
        createAction={{
          label: 'Add delivery location',
          onClick: () => setEditor({}),
        }}
      />

      <div className="supplier-status-line" aria-live="polite">
        <span>
          {data
            ? `${data.total} ${data.total === 1 ? 'location' : 'locations'}`
            : loading
              ? 'Loading delivery locations...'
              : ''}
        </span>
        {notice && <span className="admin-notice">{notice}</span>}
      </div>

      {loadError ? (
        <div className="supplier-empty" role="alert">
          <p>{loadError}</p>
          <button type="button" onClick={() => setReloadKey((k) => k + 1)}>
            Try again
          </button>
        </div>
      ) : (
        <div className="supplier-list">
          {data?.items.map((location) => (
            <article className="admin-card" key={location.id}>
              <div>
                <h2>
                  {location.name}
                  {location.floor && (
                    <span className="admin-you"> · Floor {location.floor}</span>
                  )}
                </h2>
                <p className="admin-location-line">
                  <MapPin size={15} aria-hidden="true" />
                  <span>
                    {location.description ??
                      `${location.latitude.toFixed(5)}, ${location.longitude.toFixed(5)}`}
                  </span>
                </p>
              </div>
              <aside className="admin-card-actions">
                <button
                  type="button"
                  className="admin-action"
                  aria-label={`Edit ${location.name}`}
                  onClick={() => setEditor({ location })}
                >
                  <Pencil size={16} aria-hidden="true" />
                  Edit
                </button>
              </aside>
            </article>
          ))}

          {data?.items.length === 0 && (
            <div className="supplier-empty">
              <p>
                {active
                  ? 'No delivery locations found.'
                  : 'No deactivated delivery locations.'}
              </p>
              {debouncedQuery.trim() !== '' && (
                <button
                  type="button"
                  onClick={() => {
                    setQuery('')
                    setDebouncedQuery('')
                    setPage(1)
                  }}
                >
                  Clear search
                </button>
              )}
            </div>
          )}
        </div>
      )}

      {data && data.totalPages > 1 && (
        <Pagination
          page={page}
          totalPages={data.totalPages}
          onPageChange={setPage}
        />
      )}

      {editor && (
        <LocationForm
          location={editor.location}
          onSave={handleSave}
          onClose={() => setEditor(null)}
        />
      )}
    </section>
  )
}
