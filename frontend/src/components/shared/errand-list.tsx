// AI Assistance Disclosure:
// Tool: Claude Code (model: Claude Opus 5.5), date: 2026-10-19
// Scope: AI-generated errand list shared by Explore, My Requests and My Tasks: the count line, loading, empty and
//        error states, the note when supplier names weren't searched, and loading the next page on scroll;
//        each card's actions come from the mapper, for the signed-in user.
// Author review: <to be completed by author>

import { useEffect, useRef } from 'react'
import TaskCard from './task-card'
import { toTaskCard, type ErrandViewer } from '../../utils/errand'
import { useSession } from '../../utils/session'
import type { ErrandList as ErrandListState } from '../../utils/use-errand-list'
import './errand-list.css'

type Props = {
  list: ErrandListState
  viewer: ErrandViewer
  label: string
  emptyText: string
  onClearSearch: () => void
}

export default function ErrandList({
  list,
  viewer,
  label,
  emptyText,
  onClearSearch,
}: Props) {
  const userId = useSession()?.userId ?? null
  const { items, total, loading, loadingMore, hasMore, error, loadMore } = list
  const sentinel = useRef<HTMLDivElement>(null)
  const canLoadMore = hasMore && !loadingMore && !error

  // Ask for the next page as the end of the list comes into view
  useEffect(() => {
    const node = sentinel.current
    if (!node || !canLoadMore) return

    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) loadMore()
      },
      { rootMargin: '200px' },
    )
    observer.observe(node)
    return () => observer.disconnect()
  }, [canLoadMore, loadMore])

  return (
    <>
      <div className="errand-list-status" aria-live="polite">
        <span>
          {loading
            ? 'Loading errands...'
            : !error || items.length > 0
              ? `${total} ${total === 1 ? 'errand' : 'errands'}`
              : ''}
        </span>
        {!list.supplierSearch && (
          <span className="errand-list-note">
            Supplier names can't be searched right now, so only titles and
            delivery locations were matched.
          </span>
        )}
      </div>

      {error && items.length === 0 ? (
        <div className="errand-list-empty" role="alert">
          <p>{error}</p>
          <button type="button" onClick={list.retry}>
            Try again
          </button>
        </div>
      ) : (
        <section className="task-card-list" aria-label={label}>
          {items.map((errand) => (
            <TaskCard key={errand.id} {...toTaskCard(errand, viewer, userId)} />
          ))}

          {!loading && items.length === 0 && (
            <div className="errand-list-empty">
              <p>{emptyText}</p>
              {list.searching && (
                <button type="button" onClick={onClearSearch}>
                  Clear search
                </button>
              )}
            </div>
          )}
        </section>
      )}

      {items.length > 0 && (
        <div className="errand-list-more" ref={sentinel}>
          {loadingMore && <p>Loading more errands...</p>}
          {error && (
            <div role="alert">
              <p>{error}</p>
              <button type="button" onClick={list.retry}>
                Try again
              </button>
            </div>
          )}
        </div>
      )}
    </>
  )
}
