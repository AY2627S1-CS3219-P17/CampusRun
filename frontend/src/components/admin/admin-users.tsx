// AI Assistance Disclosure:
// Tool: Claude Code (model: Claude Opus 5.5), date: 2026-11-09
// Scope: AI-generated the admin page's Users tab: search and role filter, pages, promoting a student after a
//        confirmation, and stepping down from your own admin role while another admin is left; AI-moved Step down
//        into the toolbar row, greyed out while you're the only admin (2026-11-10); AI-added the Errands menu that
//        opens a user's errands as requester or courier (2026-11-10).
// Author review: <to be completed by author>

import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router'
import { AlertDialog, DropdownMenu } from 'radix-ui'
import { ChevronDown, ListChecks, ShieldCheck, ShieldMinus } from 'lucide-react'
import Pagination from '../shared/pagination'
import Toolbar from '../shared/toolbar'
import { ApiError } from '../../api/client'
import { listUsers, promoteUser, stepDown } from '../../api/user'
import { refreshSession, useSession } from '../../utils/session'
import type {
  AdminUser,
  AdminUserPage,
  AdminUserQuery,
  Role,
} from '../../types/user'
import type { ToolbarOption } from '../../types/toolbar'

const PAGE_SIZE = 10

const ROLE_TABS: ToolbarOption[] = [
  { value: 'all', label: 'All' },
  { value: 'student', label: 'Students' },
  { value: 'admin', label: 'Admins' },
]

// What the confirmation dialog is asking about
type Pending = { kind: 'promote'; user: AdminUser } | { kind: 'step-down' }

function messageOf(error: unknown) {
  return error instanceof ApiError
    ? error.message
    : 'Something went wrong. Please try again.'
}

export default function AdminUsers({
  onError,
  onViewErrands,
}: {
  onError: (message: string) => void
  onViewErrands: (user: AdminUser, as: 'requester' | 'courier') => void
}) {
  const session = useSession()
  const navigate = useNavigate()
  const myId = Number(session?.userId)

  const [role, setRole] = useState<Role | null>(null)
  const [query, setQuery] = useState('')
  const [debouncedQuery, setDebouncedQuery] = useState('')
  const [page, setPage] = useState(1)
  const [reloadKey, setReloadKey] = useState(0)
  const [notice, setNotice] = useState('')
  const [pending, setPending] = useState<Pending | null>(null)
  const [busy, setBusy] = useState(false)

  const [result, setResult] = useState<{
    key: string
    data: AdminUserPage | null
    error: string | null
  } | null>(null)
  // Only used to grey out "Step down" for the last admin; the server makes the real check
  const [adminCount, setAdminCount] = useState<number | null>(null)

  useEffect(() => {
    const timeout = setTimeout(() => setDebouncedQuery(query), 300)
    return () => clearTimeout(timeout)
  }, [query])

  const usersQuery = useMemo<AdminUserQuery>(
    () => ({ q: debouncedQuery, role, page, pageSize: PAGE_SIZE }),
    [debouncedQuery, role, page],
  )
  const requestKey = `${JSON.stringify(usersQuery)}#${reloadKey}`

  useEffect(() => {
    const controller = new AbortController()
    listUsers(usersQuery, controller.signal)
      .then((data) => {
        // The page emptied, e.g. after a promotion moved its last user out of a role filter
        if (data.total_pages > 0 && usersQuery.page > data.total_pages) {
          setPage(data.total_pages)
          return
        }
        setResult({ key: requestKey, data, error: null })
      })
      .catch((error: unknown) => {
        if (error instanceof DOMException && error.name === 'AbortError') return
        setResult({ key: requestKey, data: null, error: messageOf(error) })
      })
    return () => controller.abort()
  }, [requestKey, usersQuery])

  useEffect(() => {
    const controller = new AbortController()
    listUsers({ q: '', role: 'admin', page: 1, pageSize: 1 }, controller.signal)
      .then((data) => setAdminCount(data.total))
      .catch(() => setAdminCount(null))
    return () => controller.abort()
  }, [reloadKey])

  const loading = result?.key !== requestKey
  const data = result?.data ?? null
  const loadError = !loading ? (result?.error ?? null) : null
  const hasFilters = debouncedQuery.trim() !== '' || role !== null
  // Unknown (still loading, or the count failed) counts as "can't", so the button never offers what may be refused
  const canStepDown = adminCount !== null && adminCount > 1

  function updateRole(value: string) {
    setRole(value === 'student' || value === 'admin' ? value : null)
    setPage(1)
  }

  function updateQuery(value: string) {
    setQuery(value)
    setPage(1)
  }

  async function confirm() {
    if (!pending) return
    setBusy(true)
    try {
      if (pending.kind === 'promote') {
        const saved = await promoteUser(pending.user.id)
        setNotice(
          `${saved.username} is now an admin. They'll have admin access within 5 minutes.`,
        )
        setPending(null)
        setReloadKey((key) => key + 1)
      } else {
        await stepDown()
        // Get a token with the new role now, rather than staying an admin here for up to 5 minutes
        await refreshSession().catch(() => undefined)
        void navigate('/explore', { replace: true })
      }
    } catch (error) {
      setPending(null)
      onError(messageOf(error))
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="supplier-directory" aria-label="Users">
      <Toolbar
        tabs={{
          options: ROLE_TABS,
          value: role ?? 'all',
          onChange: updateRole,
          label: 'Filter users by role',
        }}
        search={{
          value: query,
          onChange: updateQuery,
          placeholder: 'Search by username or email',
          label: 'Search users by username or email',
          maxLength: 100,
        }}
        actions={
          <button
            type="button"
            className="admin-action admin-action-danger admin-step-down"
            // aria-disabled rather than disabled, so it stays focusable and its tooltip says why
            aria-disabled={!canStepDown}
            title={
              canStepDown
                ? 'Give up your admin role'
                : "You're the only admin. Make someone else an admin before stepping down."
            }
            onClick={() => {
              if (canStepDown) setPending({ kind: 'step-down' })
            }}
          >
            <ShieldMinus size={16} aria-hidden="true" />
            <span className="admin-step-down-label">Step down</span>
          </button>
        }
      />

      <div className="supplier-status-line" aria-live="polite">
        <span>
          {data
            ? `${data.total} ${data.total === 1 ? 'user' : 'users'}`
            : loading
              ? 'Loading users...'
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
          {data?.items.map((user) => {
            const isMe = user.id === myId
            return (
              <article className="admin-card" key={user.id}>
                <div>
                  <h2>
                    {user.username}
                    {isMe && <span className="admin-you"> (you)</span>}
                  </h2>
                  <p>{user.email}</p>
                </div>
                <aside className="admin-card-actions">
                  <span className={`admin-role admin-role-${user.role}`}>
                    {user.role === 'admin' ? 'Admin' : 'Student'}
                  </span>
                  <DropdownMenu.Root modal={false}>
                    <DropdownMenu.Trigger asChild>
                      <button
                        type="button"
                        className="admin-action"
                        aria-label={`${user.username}'s errands`}
                      >
                        <ListChecks size={16} aria-hidden="true" />
                        Errands
                        <ChevronDown size={14} aria-hidden="true" />
                      </button>
                    </DropdownMenu.Trigger>
                    <DropdownMenu.Portal>
                      <DropdownMenu.Content
                        className="toolbar-menu"
                        align="end"
                        sideOffset={6}
                        collisionPadding={12}
                      >
                        <DropdownMenu.Item
                          className="toolbar-option"
                          onSelect={() => onViewErrands(user, 'requester')}
                        >
                          Requested by {user.username}
                        </DropdownMenu.Item>
                        <DropdownMenu.Item
                          className="toolbar-option"
                          onSelect={() => onViewErrands(user, 'courier')}
                        >
                          Delivered by {user.username}
                        </DropdownMenu.Item>
                      </DropdownMenu.Content>
                    </DropdownMenu.Portal>
                  </DropdownMenu.Root>
                  {user.role === 'student' && (
                    <button
                      type="button"
                      className="admin-action"
                      onClick={() => setPending({ kind: 'promote', user })}
                    >
                      <ShieldCheck size={16} aria-hidden="true" />
                      Make admin
                    </button>
                  )}
                </aside>
              </article>
            )
          })}

          {data?.items.length === 0 && (
            <div className="supplier-empty">
              <p>No users found.</p>
              {hasFilters && (
                <button
                  type="button"
                  onClick={() => {
                    setQuery('')
                    setDebouncedQuery('')
                    updateRole('all')
                  }}
                >
                  Clear search and filter
                </button>
              )}
            </div>
          )}
        </div>
      )}

      {data && data.total_pages > 1 && (
        <Pagination
          page={page}
          totalPages={data.total_pages}
          onPageChange={setPage}
        />
      )}

      <AlertDialog.Root
        open={pending !== null}
        onOpenChange={(open) => !open && !busy && setPending(null)}
      >
        <AlertDialog.Portal>
          <AlertDialog.Overlay className="admin-dialog-overlay" />
          <AlertDialog.Content className="admin-dialog">
            <AlertDialog.Title>
              {pending?.kind === 'promote'
                ? `Make ${pending.user.username} an admin?`
                : 'Step down as admin?'}
            </AlertDialog.Title>
            <AlertDialog.Description>
              {pending?.kind === 'promote'
                ? 'They will be able to manage suppliers, delivery locations and users, including making other admins. Only they can give the role up again.'
                : "You'll lose admin access and go back to being a student. Only another admin can make you an admin again."}
            </AlertDialog.Description>
            <div className="admin-dialog-actions">
              <AlertDialog.Cancel disabled={busy}>Cancel</AlertDialog.Cancel>
              <button
                type="button"
                className={
                  pending?.kind === 'step-down' ? 'admin-action-danger' : ''
                }
                disabled={busy}
                onClick={() => void confirm()}
              >
                {busy
                  ? 'Saving...'
                  : pending?.kind === 'promote'
                    ? 'Make admin'
                    : 'Step down'}
              </button>
            </div>
          </AlertDialog.Content>
        </AlertDialog.Portal>
      </AlertDialog.Root>
    </section>
  )
}
