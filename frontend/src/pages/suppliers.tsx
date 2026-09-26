// AI Assistance Disclosure:
// Tool: Claude (claude.ai chat, model: Claude Opus 5.5), date: 2026-09-26
// Scope: AI-modified: loads suppliers from the Supplier Service (search, type filter, sort and
//        pagination done by the service); adds details, delete, admin-only controls and sign-in handling.
// Author review: <to be completed by author>

import { useEffect, useMemo, useRef, useState } from 'react'
import { Link } from 'react-router'
import { DropdownMenu } from 'radix-ui'
import {
  ArrowLeft,
  ArrowUpDown,
  Check,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  Clock,
  Filter,
  MapPin,
  Pencil,
  Plus,
  Power,
  Search,
  Settings,
  Trash2,
} from 'lucide-react'
import './suppliers.css'
import CreateSupplierDialog from '../components/update-supplier'
import SupplierDetailsDialog from '../components/supplier-details'
import DeleteSupplierDialog from '../components/delete-supplier'
import DevTokenDialog from '../components/dev-token-dialog'
import { ApiError } from '../api/client'
import { listSuppliers, toggleSupplier } from '../api/supplier'
import { clearSession, useSession } from '../utils/session'
import {
  SUPPLIER_CATEGORIES,
  type Page,
  type Supplier,
  type SupplierCategory,
  type SupplierQuery,
  type SupplierSort,
} from '../types/supplier'

const PAGE_SIZE = 10

const SORTS: { value: SupplierSort; label: string }[] = [
  { value: 'name', label: 'Name (A-Z)' },
  { value: '-name', label: 'Name (Z-A)' },
  { value: 'type', label: 'Type' },
  { value: '-createdAt', label: 'Newest' },
  { value: '-updatedAt', label: 'Recently updated' },
]

// 1 … 4 5 6 … 12
function pageNumbers(page: number, total: number): (number | 'gap')[] {
  const wanted = [...new Set([1, page - 1, page, page + 1, total])]
    .filter((p) => p >= 1 && p <= total)
    .sort((a, b) => a - b)
  return wanted.flatMap((p, i) =>
    i > 0 && p - wanted[i - 1] > 1 ? ['gap' as const, p] : [p],
  )
}

function messageOf(error: unknown) {
  return error instanceof ApiError
    ? error.message
    : 'Something went wrong. Please try again.'
}

export default function SuppliersPage() {
  const session = useSession()
  const isAdmin = session?.role === 'admin'

  const [editor, setEditor] = useState<{ supplier?: Supplier } | null>(null)
  const editorTrigger = useRef<HTMLElement | null>(null)
  const createButton = useRef<HTMLButtonElement>(null)
  const [details, setDetails] = useState<Supplier | null>(null)
  const [deleting, setDeleting] = useState<Supplier | null>(null)
  const [signingIn, setSigningIn] = useState(false)

  const [status, setStatus] = useState<'active' | 'deactivated'>('active')
  const [query, setQuery] = useState('')
  const [debouncedQuery, setDebouncedQuery] = useState('')
  const [selectedType, setSelectedType] = useState<
    SupplierCategory | 'All Types'
  >('All Types')
  const [sort, setSort] = useState<SupplierSort>('name')
  const [page, setPage] = useState(1)
  const [reloadKey, setReloadKey] = useState(0)
  const [result, setResult] = useState<{
    key: string
    data: Page<Supplier> | null
    error: string | null
  } | null>(null)
  const [notice, setNotice] = useState<{
    text: string
    tone: 'ok' | 'error'
  } | null>(null)
  const noticeTimer = useRef<number | undefined>(undefined)

  useEffect(() => {
    const timeout = setTimeout(() => {
      setDebouncedQuery(query)
      setPage(1)
    }, 300)
    return () => clearTimeout(timeout)
  }, [query])

  // Students only ever see active suppliers; the service refuses anything else
  const active = !isAdmin || status === 'active'
  const suppliersQuery = useMemo<SupplierQuery>(
    () => ({
      q: debouncedQuery,
      type: selectedType === 'All Types' ? null : selectedType,
      active,
      sort,
      page,
      pageSize: PAGE_SIZE,
    }),
    [debouncedQuery, selectedType, active, sort, page],
  )
  const requestKey = session
    ? `${JSON.stringify(suppliersQuery)}#${reloadKey}#${session.token}`
    : null

  useEffect(() => {
    if (!requestKey) return
    const controller = new AbortController()
    listSuppliers(suppliersQuery, controller.signal)
      .then((data) => {
        // e.g. the last supplier on the last page was deleted
        if (data.totalPages > 0 && suppliersQuery.page > data.totalPages) {
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
  }, [requestKey, suppliersQuery])

  const loading = requestKey !== null && result?.key !== requestKey
  const data = result?.data ?? null
  const loadError = !loading ? (result?.error ?? null) : null
  const hasFilters =
    debouncedQuery.trim() !== '' || selectedType !== 'All Types'

  function reload() {
    setReloadKey((key) => key + 1)
  }

  function showNotice(text: string, tone: 'ok' | 'error' = 'ok') {
    setNotice({ text, tone })
    window.clearTimeout(noticeTimer.current)
    noticeTimer.current = window.setTimeout(() => setNotice(null), 5000)
  }

  async function handleToggle(supplier: Supplier) {
    try {
      const saved = await toggleSupplier(supplier.id, !supplier.active)
      showNotice(
        saved.active
          ? `Activated ${saved.name}. Students can see it again.`
          : `Deactivated ${saved.name}. Students can no longer see it.`,
      )
      if (details?.id === saved.id) setDetails(saved)
      reload()
    } catch (error) {
      showNotice(messageOf(error), 'error')
    }
  }

  function changeFilter(change: () => void) {
    change()
    setPage(1)
  }

  return (
    <div className="suppliers-page">
      <main>
        <section className="suppliers-banner">
          <div>
            <Link
              className="suppliers-back"
              to="/explore"
              aria-label="Back to Explore"
            >
              <ArrowLeft size={20} aria-hidden="true" />
            </Link>
            <h1>Suppliers</h1>
            <p>Our supported suppliers.</p>
            {session && (
              <p className="suppliers-session">
                Signed in as {isAdmin ? 'an admin' : 'a student'}.{' '}
                <button type="button" onClick={clearSession}>
                  Sign out
                </button>
              </p>
            )}
          </div>
        </section>

        <section className="supplier-directory" aria-label="Supplier directory">
          {!session ? (
            <div className="supplier-signin">
              <h2>Sign in to see suppliers</h2>
              <p>The supplier list is only available to signed-in users.</p>
              <div>
                <Link to="/login">Go to login</Link>
                {import.meta.env.DEV && (
                  <button type="button" onClick={() => setSigningIn(true)}>
                    Use a development token
                  </button>
                )}
              </div>
            </div>
          ) : (
            <>
              <div className="directory-toolbar">
                {isAdmin ? (
                  <div
                    className="supplier-tabs"
                    role="tablist"
                    aria-label="Supplier status"
                  >
                    <button
                      className={status === 'active' ? 'is-active' : ''}
                      onClick={() => changeFilter(() => setStatus('active'))}
                      role="tab"
                      aria-selected={status === 'active'}
                    >
                      Active
                    </button>
                    <button
                      className={status === 'deactivated' ? 'is-active' : ''}
                      onClick={() =>
                        changeFilter(() => setStatus('deactivated'))
                      }
                      role="tab"
                      aria-selected={status === 'deactivated'}
                    >
                      Deactivated
                    </button>
                  </div>
                ) : (
                  <div />
                )}

                <div className="directory-controls">
                  <label className="supplier-search">
                    <Search size={18} aria-hidden="true" />
                    <input
                      value={query}
                      onChange={(event) => setQuery(event.target.value)}
                      placeholder="Search by name or location"
                      aria-label="Search suppliers by name or location"
                      maxLength={100}
                    />
                  </label>

                  <DropdownMenu.Root modal={false}>
                    <DropdownMenu.Trigger asChild>
                      <button
                        className="supplier-filter"
                        type="button"
                        aria-label={`Filter suppliers by type: ${selectedType}`}
                      >
                        <Filter size={16} aria-hidden="true" />
                        <span>{selectedType}</span>
                        <ChevronDown size={15} aria-hidden="true" />
                      </button>
                    </DropdownMenu.Trigger>
                    <DropdownMenu.Portal>
                      <DropdownMenu.Content
                        className="supplier-filter-menu"
                        align="end"
                        sideOffset={6}
                        collisionPadding={12}
                      >
                        <DropdownMenu.RadioGroup
                          value={selectedType}
                          onValueChange={(value) => {
                            if (
                              value === 'All Types' ||
                              SUPPLIER_CATEGORIES.includes(
                                value as SupplierCategory,
                              )
                            )
                              changeFilter(() =>
                                setSelectedType(
                                  value as SupplierCategory | 'All Types',
                                ),
                              )
                          }}
                          aria-label="Supplier type"
                        >
                          <DropdownMenu.RadioItem
                            className="supplier-filter-option"
                            value="All Types"
                          >
                            All Types
                            <DropdownMenu.ItemIndicator>
                              <Check size={16} aria-hidden="true" />
                            </DropdownMenu.ItemIndicator>
                          </DropdownMenu.RadioItem>
                          <DropdownMenu.Separator className="supplier-filter-separator" />
                          {SUPPLIER_CATEGORIES.map((type) => (
                            <DropdownMenu.RadioItem
                              className="supplier-filter-option"
                              key={type}
                              value={type}
                            >
                              {type}
                              <DropdownMenu.ItemIndicator>
                                <Check size={16} aria-hidden="true" />
                              </DropdownMenu.ItemIndicator>
                            </DropdownMenu.RadioItem>
                          ))}
                        </DropdownMenu.RadioGroup>
                      </DropdownMenu.Content>
                    </DropdownMenu.Portal>
                  </DropdownMenu.Root>

                  <DropdownMenu.Root modal={false}>
                    <DropdownMenu.Trigger asChild>
                      <button
                        className="supplier-filter supplier-sort"
                        type="button"
                        aria-label={`Sort suppliers: ${SORTS.find((s) => s.value === sort)?.label}`}
                      >
                        <ArrowUpDown size={16} aria-hidden="true" />
                        <span>
                          {SORTS.find((s) => s.value === sort)?.label}
                        </span>
                        <ChevronDown size={15} aria-hidden="true" />
                      </button>
                    </DropdownMenu.Trigger>
                    <DropdownMenu.Portal>
                      <DropdownMenu.Content
                        className="supplier-filter-menu"
                        align="end"
                        sideOffset={6}
                        collisionPadding={12}
                      >
                        <DropdownMenu.RadioGroup
                          value={sort}
                          onValueChange={(value) => {
                            const option = SORTS.find((s) => s.value === value)
                            if (option)
                              changeFilter(() => setSort(option.value))
                          }}
                          aria-label="Sort order"
                        >
                          {SORTS.map((option) => (
                            <DropdownMenu.RadioItem
                              className="supplier-filter-option"
                              key={option.value}
                              value={option.value}
                            >
                              {option.label}
                              <DropdownMenu.ItemIndicator>
                                <Check size={16} aria-hidden="true" />
                              </DropdownMenu.ItemIndicator>
                            </DropdownMenu.RadioItem>
                          ))}
                        </DropdownMenu.RadioGroup>
                      </DropdownMenu.Content>
                    </DropdownMenu.Portal>
                  </DropdownMenu.Root>

                  {isAdmin && (
                    <button
                      className="create-supplier"
                      type="button"
                      aria-label="Create supplier"
                      ref={createButton}
                      onClick={(event) => {
                        editorTrigger.current = event.currentTarget
                        setEditor({})
                      }}
                    >
                      <Plus size={18} aria-hidden="true" />
                    </button>
                  )}
                </div>
              </div>

              <div className="supplier-status-line" aria-live="polite">
                <span>
                  {data
                    ? `${data.total} ${data.total === 1 ? 'supplier' : 'suppliers'}`
                    : loading
                      ? 'Loading suppliers...'
                      : ''}
                </span>
                {notice && (
                  <span
                    className={`supplier-notice supplier-notice-${notice.tone}`}
                  >
                    {notice.text}
                  </span>
                )}
              </div>

              {loadError ? (
                <div className="supplier-empty" role="alert">
                  <p>{loadError}</p>
                  <button type="button" onClick={reload}>
                    Try again
                  </button>
                </div>
              ) : (
                <div
                  className={`supplier-list${loading && data ? ' is-loading' : ''}`}
                >
                  {data?.items.map((supplier) => (
                    <article className="supplier-card" key={supplier.id}>
                      <div>
                        <h2>
                          <button
                            type="button"
                            className="supplier-card-open"
                            onClick={() => setDetails(supplier)}
                          >
                            {supplier.name}
                          </button>
                        </h2>
                        <p className="supplier-location">
                          <MapPin size={16} aria-hidden="true" />
                          <span>{supplier.location}</span>
                        </p>
                        <p className="supplier-hours">
                          <Clock size={16} aria-hidden="true" />
                          <span>
                            {supplier.startTime} - {supplier.endTime}
                          </span>
                          {supplier.active && (
                            <span
                              className={`supplier-open${supplier.isOpenNow ? ' is-open' : ''}`}
                            >
                              {supplier.isOpenNow ? 'Open now' : 'Closed'}
                            </span>
                          )}
                        </p>
                      </div>
                      <aside className="supplier-card-actions">
                        <span
                          className={`supplier-type supplier-type-${supplier.type.toLowerCase()}`}
                        >
                          {supplier.type}
                        </span>
                        {isAdmin && (
                          <DropdownMenu.Root modal={false}>
                            <DropdownMenu.Trigger asChild>
                              <button
                                className="supplier-settings"
                                type="button"
                                aria-label={`Settings for ${supplier.name}`}
                                onFocus={(event) => {
                                  editorTrigger.current = event.currentTarget
                                }}
                              >
                                <Settings size={18} aria-hidden="true" />
                              </button>
                            </DropdownMenu.Trigger>
                            <DropdownMenu.Portal>
                              <DropdownMenu.Content
                                className="supplier-filter-menu supplier-settings-menu"
                                onCloseAutoFocus={(event) => {
                                  if (editor || deleting) event.preventDefault()
                                }}
                                align="end"
                                sideOffset={6}
                                collisionPadding={12}
                              >
                                <DropdownMenu.Item
                                  className="supplier-filter-option supplier-settings-option"
                                  onSelect={() => setEditor({ supplier })}
                                >
                                  <Pencil size={16} aria-hidden="true" />
                                  Edit
                                </DropdownMenu.Item>
                                <DropdownMenu.Item
                                  className="supplier-filter-option supplier-settings-option"
                                  onSelect={() => {
                                    void handleToggle(supplier)
                                  }}
                                >
                                  <Power size={16} aria-hidden="true" />
                                  {supplier.active ? 'Deactivate' : 'Activate'}
                                </DropdownMenu.Item>
                                <DropdownMenu.Item
                                  className="supplier-filter-option supplier-settings-option supplier-settings-danger"
                                  onSelect={() => setDeleting(supplier)}
                                >
                                  <Trash2 size={16} aria-hidden="true" />
                                  Delete
                                </DropdownMenu.Item>
                              </DropdownMenu.Content>
                            </DropdownMenu.Portal>
                          </DropdownMenu.Root>
                        )}
                      </aside>
                    </article>
                  ))}

                  {data?.items.length === 0 && (
                    <div className="supplier-empty">
                      <p>No suppliers found.</p>
                      {hasFilters && (
                        <button
                          type="button"
                          onClick={() => {
                            setQuery('')
                            setDebouncedQuery('')
                            changeFilter(() => setSelectedType('All Types'))
                          }}
                        >
                          Clear search and filter
                        </button>
                      )}
                    </div>
                  )}
                </div>
              )}

              {data && data.totalPages > 1 && (
                <nav className="supplier-pagination" aria-label="Pages">
                  <button
                    type="button"
                    aria-label="Previous page"
                    disabled={page <= 1}
                    onClick={() => setPage(page - 1)}
                  >
                    <ChevronLeft size={18} aria-hidden="true" />
                  </button>
                  {pageNumbers(page, data.totalPages).map((p, i) =>
                    p === 'gap' ? (
                      <span key={`gap-${i}`} aria-hidden="true">
                        …
                      </span>
                    ) : (
                      <button
                        type="button"
                        key={p}
                        aria-label={`Page ${p}`}
                        aria-current={p === page ? 'page' : undefined}
                        onClick={() => setPage(p)}
                      >
                        {p}
                      </button>
                    ),
                  )}
                  <button
                    type="button"
                    aria-label="Next page"
                    disabled={page >= data.totalPages}
                    onClick={() => setPage(page + 1)}
                  >
                    <ChevronRight size={18} aria-hidden="true" />
                  </button>
                </nav>
              )}
            </>
          )}
        </section>
      </main>

      {details && (
        <SupplierDetailsDialog
          key={details.id}
          supplier={details}
          isAdmin={isAdmin}
          onClose={() => setDetails(null)}
          onEdit={(supplier) => {
            setDetails(null)
            setEditor({ supplier })
          }}
          onToggle={(supplier) => {
            void handleToggle(supplier)
          }}
          onDelete={(supplier) => {
            setDetails(null)
            setDeleting(supplier)
          }}
        />
      )}
      {editor && (
        <CreateSupplierDialog
          supplier={editor.supplier}
          onClose={() => setEditor(null)}
          onRestoreFocus={() => {
            const trigger = editorTrigger.current
            if (trigger?.isConnected) trigger.focus()
            else createButton.current?.focus()
          }}
          onSave={(saved) => {
            showNotice(
              editor.supplier
                ? `Saved changes to ${saved.name}.`
                : `Created ${saved.name}.`,
            )
            if (!editor.supplier) {
              setStatus('active')
              setQuery('')
              setDebouncedQuery('')
              setSelectedType('All Types')
              setPage(1)
            }
            reload()
          }}
        />
      )}
      {deleting && (
        <DeleteSupplierDialog
          supplier={deleting}
          onClose={() => setDeleting(null)}
          onDeleted={(supplier) => {
            showNotice(`Deleted ${supplier.name}.`)
            reload()
          }}
        />
      )}
      {signingIn && <DevTokenDialog onClose={() => setSigningIn(false)} />}
    </div>
  )
}
