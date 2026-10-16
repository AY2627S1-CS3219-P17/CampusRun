// AI Assistance Disclosure:
// Tool: Codex (OpenAI), date: 2026-10-16
// Scope: Extracted the supplier page-number navigation into a reusable pagination component.
// Author review: <to be completed by author>

import { ChevronLeft, ChevronRight } from 'lucide-react'
import './pagination.css'

type PaginationProps = {
  page: number
  totalPages: number
  onPageChange: (page: number) => void
}

function pageNumbers(page: number, total: number): (number | 'gap')[] {
  const wanted = [...new Set([1, page - 1, page, page + 1, total])]
    .filter((number) => number >= 1 && number <= total)
    .sort((a, b) => a - b)
  return wanted.flatMap((number, index) =>
    index > 0 && number - wanted[index - 1] > 1
      ? ['gap' as const, number]
      : [number],
  )
}

export default function Pagination({
  page,
  totalPages,
  onPageChange,
}: PaginationProps) {
  if (totalPages < 1) return null

  return (
    <nav className="shared-pagination" aria-label="Pages">
      <button
        type="button"
        aria-label="Previous page"
        disabled={page <= 1}
        onClick={() => onPageChange(page - 1)}
      >
        <ChevronLeft size={18} aria-hidden="true" />
      </button>
      {pageNumbers(page, totalPages).map((number, index) =>
        number === 'gap' ? (
          <span key={`gap-${index}`} aria-hidden="true">
            &hellip;
          </span>
        ) : (
          <button
            type="button"
            key={number}
            aria-label={`Page ${number}`}
            aria-current={number === page ? 'page' : undefined}
            onClick={() => onPageChange(number)}
          >
            {number}
          </button>
        ),
      )}
      <button
        type="button"
        aria-label="Next page"
        disabled={page >= totalPages}
        onClick={() => onPageChange(page + 1)}
      >
        <ChevronRight size={18} aria-hidden="true" />
      </button>
    </nav>
  )
}
