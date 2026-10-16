// AI Assistance Disclosure:
// Tool: Codex (OpenAI), dates: 2026-10-15 and 2026-10-16
// Scope: Composed the Explore page from the reusable credit banner and shared toolbar components, then added the shared Pagination control for available-task samples.
// Author review: <to be completed by author>

import { useState } from 'react'
import CreditBanner from '../../components/shared/credit-banner'
import TaskCard, { type TaskCardProps } from '../../components/shared/task-card'
import Pagination from '../../components/shared/pagination'
import Toolbar from '../../components/shared/toolbar'
import Header from '../../components/shared/header'
import { ERRAND_SORTS } from '../../utils/toolbar'
import './explore.css'

const PAGE_SIZE = 2
const AVAILABLE_TASKS: TaskCardProps[] = [
  {
    type: 'open',
    title: 'Pick up printed notes',
    pickupPoint: 'COM3 Print Shop',
    dropoffPoint: 'Central Library',
    dueBy: '21 Apr, 5:00 PM',
    credits: 10,
  },
]

export default function ExplorePage() {
  const [query, setQuery] = useState('')
  const [sort, setSort] = useState(ERRAND_SORTS[0].value)
  const [page, setPage] = useState(1)
  const totalPages = Math.max(1, Math.ceil(AVAILABLE_TASKS.length / PAGE_SIZE))

  return (
    <div className="explore-page">
      <Header initialSection="Explore" />
      <main className="explore-content">
        <CreditBanner />
        <Toolbar
          subheader="Available Tasks"
          search={{
            value: query,
            onChange: setQuery,
            placeholder: 'Search errands',
            label: 'Search errands',
          }}
          sort={{
            options: ERRAND_SORTS,
            value: sort,
            onChange: setSort,
            label: 'Sort available tasks',
          }}
        />
        <section className="task-card-list" aria-label="Available tasks">
          {AVAILABLE_TASKS.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE).map(
            (card) => (
              <TaskCard key={card.title} {...card} />
            ),
          )}
        </section>
        <Pagination
          page={page}
          totalPages={totalPages}
          onPageChange={setPage}
        />
      </main>
    </div>
  )
}
