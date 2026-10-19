// AI Assistance Disclosure:
// Tool: Claude Code (model: Claude Opus 5.5), date: 2026-10-19
// Scope: AI-generated hook that loads an errand list from the Order Service with a debounced search, infinite
//        scrolling and polling while any loaded errand's credits are PENDING; AI-added reloading in place when an
//        errand changes.
// Author review: <to be completed by author>

import { useCallback, useEffect, useState } from 'react'
import { ApiError } from '../api/client'
import { listExplore, listMyRequests, listMyTasks } from '../api/order'
import type {
  Errand,
  ErrandPage,
  ErrandQuery,
  ErrandSort,
  ErrandTab,
} from '../types/order'
import { onErrandsChanged } from './errand-events'
import { useSession } from './session'

export type ErrandScope = 'explore' | 'requests' | 'tasks'

const PAGE_SIZE = 10
const SEARCH_DELAY_MS = 300
// How often to check again while credits are being processed
const PENDING_POLL_MS = 2000

// Everything here belongs to one requestKey, so changing the filters starts again from nothing
type Loaded = {
  key: string
  pages: ErrandPage[]
  error: string | null
  // The pages asked for so far, and how many times the user pressed Try again
  count: number
  attempt: number
  // Set when an errand changed, so the pages shown are reloaded straight away
  stale?: boolean
}

function fetchPage(
  scope: ErrandScope,
  tab: ErrandTab,
  query: ErrandQuery,
  signal: AbortSignal,
) {
  if (scope === 'explore') return listExplore(query, signal)
  if (scope === 'requests') return listMyRequests(tab, query, signal)
  return listMyTasks(tab, query, signal)
}

function messageOf(error: unknown) {
  return error instanceof ApiError
    ? error.message
    : 'Something went wrong. Please try again.'
}

function isAbort(error: unknown) {
  return error instanceof DOMException && error.name === 'AbortError'
}

// tab is ignored for Explore
export function useErrandList(
  scope: ErrandScope,
  tab: ErrandTab,
  search: string,
  sort: ErrandSort,
) {
  const session = useSession()
  const [debouncedSearch, setDebouncedSearch] = useState(search)
  const [loaded, setLoaded] = useState<Loaded | null>(null)

  useEffect(() => {
    const timeout = setTimeout(
      () => setDebouncedSearch(search),
      SEARCH_DELAY_MS,
    )
    return () => clearTimeout(timeout)
  }, [search])

  const q = debouncedSearch.trim()
  // A change here starts the list again from the first page, and aborts the request in flight
  const requestKey = session
    ? JSON.stringify([scope, scope === 'explore' ? null : tab, q, sort]) +
      `#${session.token}`
    : null
  const current = loaded?.key === requestKey ? loaded : null
  const count = current?.count ?? 1
  const attempt = current?.attempt ?? 0

  // Load page `count`: the first page after a change, then the next one each time the list scrolls to its end
  useEffect(() => {
    if (!requestKey) return

    const controller = new AbortController()
    const query = { q, sort, page: count, pageSize: PAGE_SIZE }
    fetchPage(scope, tab, query, controller.signal)
      .then((page) =>
        setLoaded((prev) =>
          prev?.key === requestKey
            ? {
                ...prev,
                pages: [...prev.pages.slice(0, count - 1), page],
                error: null,
              }
            : { key: requestKey, pages: [page], error: null, count, attempt },
        ),
      )
      .catch((error: unknown) => {
        if (isAbort(error)) return
        setLoaded((prev) =>
          prev?.key === requestKey
            ? { ...prev, error: messageOf(error) }
            : {
                key: requestKey,
                pages: [],
                error: messageOf(error),
                count,
                attempt,
              },
        )
      })
    return () => controller.abort()
  }, [requestKey, count, attempt, scope, tab, q, sort])

  const pending =
    current?.pages.some((page) =>
      page.items.some((errand) => errand.creditStatus === 'PENDING'),
    ) ?? false

  useEffect(
    () =>
      onErrandsChanged(() =>
        setLoaded((prev) =>
          prev?.key === requestKey ? { ...prev, stale: true } : prev,
        ),
      ),
    [requestKey],
  )

  // After a change, and while credits are processing, reload the pages already shown in place, without the
  // loading state
  useEffect(() => {
    if (!current || !(pending || current.stale)) return

    const { key, pages } = current
    const controller = new AbortController()
    const timer = setTimeout(
      () => {
        Promise.all(
          pages.map((_, index) =>
            fetchPage(
              scope,
              tab,
              { q, sort, page: index + 1, pageSize: PAGE_SIZE },
              controller.signal,
            ),
          ),
        )
          .then((fresh) =>
            setLoaded((prev) =>
              prev?.key === key
                ? {
                    ...prev,
                    pages: [...fresh, ...prev.pages.slice(fresh.length)],
                    stale: false,
                  }
                : prev,
            ),
          )
          .catch((error: unknown) => {
            if (isAbort(error)) return
            // Keep what's shown; a new object runs this effect again, so the next poll still happens
            setLoaded((prev) =>
              prev?.key === key ? { ...prev, stale: false } : prev,
            )
          })
      },
      current.stale ? 0 : PENDING_POLL_MS,
    )

    return () => {
      clearTimeout(timer)
      controller.abort()
    }
  }, [current, pending, scope, tab, q, sort])

  // A refresh can move an errand onto a page that's already loaded, so show each one once
  const seen = new Set<number>()
  const items: Errand[] = []
  for (const page of current?.pages ?? []) {
    for (const errand of page.items) {
      if (seen.has(errand.id)) continue
      seen.add(errand.id)
      items.push(errand)
    }
  }

  const pageCount = current?.pages.length ?? 0
  const lastPage = current?.pages.at(-1)
  const error = current?.error ?? null
  const loading = requestKey !== null && pageCount === 0 && !error
  const loadingMore = pageCount > 0 && count > pageCount && !error
  const hasMore = !!lastPage && lastPage.page < lastPage.totalPages

  const loadMore = useCallback(() => {
    if (!hasMore || loadingMore || error) return
    setLoaded((prev) =>
      prev?.key === requestKey
        ? { ...prev, count: prev.pages.length + 1 }
        : prev,
    )
  }, [requestKey, hasMore, loadingMore, error])

  // Asks again for the page that failed
  const retry = useCallback(() => {
    setLoaded((prev) =>
      prev?.key === requestKey
        ? { ...prev, error: null, attempt: prev.attempt + 1 }
        : prev,
    )
  }, [requestKey])

  return {
    items,
    total: lastPage?.total ?? 0,
    // False if any page couldn't search supplier names because the Supplier Service was down
    supplierSearch: current?.pages.every((page) => page.supplierSearch) ?? true,
    searching: q !== '',
    loading,
    loadingMore,
    hasMore,
    error,
    pending,
    loadMore,
    retry,
  }
}

export type ErrandList = ReturnType<typeof useErrandList>
