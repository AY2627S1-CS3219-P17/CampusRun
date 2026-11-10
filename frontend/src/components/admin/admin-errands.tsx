// AI Assistance Disclosure:
// Tool: Claude Code (model: Claude Opus 5.5), date: 2026-11-10
// Scope: AI-generated the admin page's Errands tab: every errand, read-only, with search, a state filter, sorting,
//        pages, and a filter for one user's errands as requester or courier (opened from the Users tab).
// Author review: I verified the UI: search, the state filter and paging work on the Errands tab.

import { useEffect, useMemo, useState } from 'react'
import { X } from 'lucide-react'
import Pagination from '../shared/pagination'
import TaskCard from '../shared/task-card'
import Toolbar from '../shared/toolbar'
import { ApiError } from '../../api/client'
import { listAllErrands } from '../../api/order'
import { toTaskCard } from '../../utils/errand'
import { useSession } from '../../utils/session'
import type {
  AdminErrandQuery,
  ErrandPage,
  ErrandSort,
  ErrandState,
} from '../../types/order'
import type { ToolbarOption } from '../../types/toolbar'
import '../shared/errand-list.css'

const PAGE_SIZE = 10

const STATES: { value: ErrandState; label: string }[] = [
  { value: 'OPEN', label: 'Open' },
  { value: 'ACCEPTED', label: 'Accepted' },
  { value: 'PICKED_UP', label: 'Picked up' },
  { value: 'DELIVERED', label: 'Delivered' },
  { value: 'COMPLETED', label: 'Completed' },
  { value: 'CANCELLED', label: 'Cancelled' },
  { value: 'EXPIRED', label: 'Expired' },
]

const STATE_OPTIONS: ToolbarOption[] = [
  { value: 'all', label: 'All states' },
  ...STATES,
]

const SORTS: { value: ErrandSort; label: string }[] = [
  { value: 'most-recent', label: 'Most recent' },
  { value: 'least-recent', label: 'Least recent' },
  { value: 'most-credits', label: 'Most credits' },
  { value: 'least-credits', label: 'Least credits' },
]

// One user's errands, from the Users tab's "Errands" menu
export type ErrandUserFilter = {
  id: number
  username: string
  as: 'requester' | 'courier'
}

function messageOf(error: unknown) {
  return error instanceof ApiError
    ? error.message
    : 'Something went wrong. Please try again.'
}

export default function AdminErrands({
  userFilter,
  onClearUser,
}: {
  userFilter: ErrandUserFilter | null
  onClearUser: () => void
}) {
  const userId = useSession()?.userId ?? null
  const [state, setState] = useState<ErrandState | null>(null)
  const [sort, setSort] = useState<ErrandSort>('most-recent')
  const [query, setQuery] = useState('')
  const [debouncedQuery, setDebouncedQuery] = useState('')
  const [page, setPage] = useState(1)
  const [reloadKey, setReloadKey] = useState(0)
  const [result, setResult] = useState<{
    key: string
    data: ErrandPage | null
    error: string | null
  } | null>(null)

  useEffect(() => {
    const timeout = setTimeout(() => setDebouncedQuery(query), 300)
    return () => clearTimeout(timeout)
  }, [query])

  // A different user starts again from the first page
  const userKey = userFilter ? `${userFilter.as}:${userFilter.id}` : ''
  const [shownUserKey, setShownUserKey] = useState(userKey)
  if (shownUserKey !== userKey) {
    setShownUserKey(userKey)
    setPage(1)
  }

  // Plain values, not userFilter itself: the page builds a new filter object on every render
  const requesterId = userFilter?.as === 'requester' ? userFilter.id : null
  const courierId = userFilter?.as === 'courier' ? userFilter.id : null
  const errandsQuery = useMemo<AdminErrandQuery>(
    () => ({
      q: debouncedQuery,
      sort,
      state,
      requesterId,
      courierId,
      page,
      pageSize: PAGE_SIZE,
    }),
    [debouncedQuery, sort, state, requesterId, courierId, page],
  )
  const requestKey = `${JSON.stringify(errandsQuery)}#${reloadKey}`

  useEffect(() => {
    const controller = new AbortController()
    listAllErrands(errandsQuery, controller.signal)
      .then((data) => {
        if (data.totalPages > 0 && errandsQuery.page > data.totalPages) {
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
  }, [requestKey, errandsQuery])

  const loading = result?.key !== requestKey
  // Keep the last list on screen while the next one loads, so it doesn't flash empty
  const data = result?.data ?? null
  const loadError = !loading ? (result?.error ?? null) : null
  const hasFilters =
    debouncedQuery.trim() !== '' || state !== null || userFilter !== null

  function updateState(value: string) {
    const match = STATES.find((option) => option.value === value)
    setState(match ? match.value : null)
    setPage(1)
  }

  function updateSort(value: string) {
    const match = SORTS.find((option) => option.value === value)
    if (match) {
      setSort(match.value)
      setPage(1)
    }
  }

  return (
    <section className="supplier-directory" aria-label="Errands">
      <Toolbar
        subheader="All errands"
        search={{
          value: query,
          onChange: (value) => {
            setQuery(value)
            setPage(1)
          },
          placeholder: 'Search title, supplier or location',
          label: 'Search errands by title, supplier or delivery location',
          maxLength: 100,
        }}
        filter={{
          options: STATE_OPTIONS,
          value: state ?? 'all',
          onChange: updateState,
          label: 'Filter errands by state',
        }}
        sort={{
          options: SORTS,
          value: sort,
          onChange: updateSort,
          label: 'Sort errands',
        }}
      />

      <div className="supplier-status-line" aria-live="polite">
        <span>
          {data
            ? `${data.total} ${data.total === 1 ? 'errand' : 'errands'}`
            : loading
              ? 'Loading errands...'
              : ''}
        </span>
        {data && !data.supplierSearch && (
          <span className="errand-list-note">
            Supplier names can't be searched right now, so only titles and
            delivery locations were matched.
          </span>
        )}
      </div>

      {userFilter && (
        <p className="admin-filter-chip">
          <span>
            {userFilter.as === 'requester' ? 'Requested by' : 'Delivered by'}{' '}
            <strong>{userFilter.username}</strong>
          </span>
          <button
            type="button"
            aria-label={`Show everyone's errands, not just ${userFilter.username}'s`}
            onClick={onClearUser}
          >
            <X size={16} aria-hidden="true" />
          </button>
        </p>
      )}

      {loadError ? (
        <div className="supplier-empty" role="alert">
          <p>{loadError}</p>
          <button type="button" onClick={() => setReloadKey((k) => k + 1)}>
            Try again
          </button>
        </div>
      ) : (
        <section className="task-card-list admin-errands" aria-label="Errands">
          {data?.items.map((errand) => (
            <TaskCard
              key={errand.id}
              {...toTaskCard(errand, 'admin', userId)}
            />
          ))}

          {data?.items.length === 0 && (
            <div className="supplier-empty">
              <p>No errands found.</p>
              {hasFilters && (
                <button
                  type="button"
                  onClick={() => {
                    setQuery('')
                    setDebouncedQuery('')
                    setState(null)
                    setPage(1)
                    if (userFilter) onClearUser()
                  }}
                >
                  Clear search and filters
                </button>
              )}
            </div>
          )}
        </section>
      )}

      {data && data.totalPages > 1 && (
        <Pagination
          page={page}
          totalPages={data.totalPages}
          onPageChange={setPage}
        />
      )}
    </section>
  )
}
