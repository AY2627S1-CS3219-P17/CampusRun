// AI Assistance Disclosure:
// Tool: Codex (OpenAI), dates: 2026-10-15 and 2026-10-16
// Scope: Composed the My Tasks page from shared components and added sample cards and per-tab pagination.
// Tool: Codex (OpenAI), date: 2026-10-17
// Scope: Showed Picked up and Delivered header actions for active courier tasks.
// Tool: Codex (OpenAI), date: 2026-10-17
// Scope: Simplified action label typing and per-tab pagination initialization.
// Author review: <to be completed by author>

import { useState } from 'react'
import CreditBanner from '../../components/shared/credit-banner'
import TaskCard, { type TaskCardType } from '../../components/shared/task-card'
import Pagination from '../../components/shared/pagination'
import Toolbar from '../../components/shared/toolbar'
import Header from '../../components/shared/header'
import { ERRAND_SORTS, ERRAND_TABS } from '../../utils/toolbar'
import { SAMPLE_TASK_CARDS } from '../../utils/sample-task-cards'
import './explore.css'

const PAGE_SIZE = 2
const ACTIVE_ACTIONS: Partial<Record<TaskCardType, string>> = {
  accepted: 'Picked up',
  'picked-up': 'Delivered',
}

export default function MyTasksPage() {
  const [tab, setTab] = useState(ERRAND_TABS[0].value)
  const [query, setQuery] = useState('')
  const [sort, setSort] = useState(ERRAND_SORTS[0].value)
  const [pages, setPages] = useState<Record<string, number>>({})
  const page = pages[tab] ?? 1
  const cards = SAMPLE_TASK_CARDS[tab] ?? []
  const totalPages = Math.max(1, Math.ceil(cards.length / PAGE_SIZE))

  return (
    <div className="explore-page">
      <Header initialSection="My Tasks" />
      <main className="explore-content">
        <CreditBanner />
        <Toolbar
          tabs={{
            options: ERRAND_TABS,
            value: tab,
            onChange: setTab,
            label: 'Errand status',
          }}
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
            label: 'Sort errands',
          }}
        />
        <section className="task-card-list" aria-label={`${tab} tasks`}>
          {cards.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE).map((card) => (
            <TaskCard
              key={card.type}
              {...card}
              actionLabel={
                tab === 'active' ? ACTIVE_ACTIONS[card.type] : undefined
              }
            />
          ))}
        </section>
        <Pagination
          page={page}
          totalPages={totalPages}
          onPageChange={(nextPage) =>
            setPages((current) => ({ ...current, [tab]: nextPage }))
          }
        />
      </main>
    </div>
  )
}
