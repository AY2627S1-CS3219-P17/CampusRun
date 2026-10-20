// AI Assistance Disclosure:
// Tool: Codex (OpenAI), dates: 2026-10-15 and 2026-10-16
// Scope: Composed the Explore page from the reusable credit banner and shared toolbar components, then added the shared Pagination control for available-task samples.
// Tool: Codex (OpenAI), date: 2026-10-17
// Scope: Supplied a mock user and pickup/dropoff positions for the task details preview.
// Tool: Codex (OpenAI), date: 2026-10-17
// Scope: Added the sample supplier name for task details.
// Tool: Codex (OpenAI), date: 2026-10-17
// Scope: Changed the mock supplier to a name from the seeded supplier list.
// Tool: Codex (OpenAI), date: 2026-10-17
// Scope: Showed Accept in Open Explore task details.
// Tool: Claude Code (model: Claude Opus 5.5), date: 2026-10-19
// Scope: AI-replaced the sample tasks with Explore from the Order Service, loaded as the list scrolls.
// Tool: Claude Code (model: Claude Opus 5.5), date: 2026-10-19
// Scope: AI-moved the card actions into the shared errand mapper.
// Tool: OpenAI Codex (GPT-6), date: 2026-10-20
// Scope: Moved the shared header into the persistent main-route layout.
// Author review: <to be completed by author>

import { useState } from 'react'
import CreditBanner from '../../components/shared/credit-banner'
import ErrandList from '../../components/shared/errand-list'
import Toolbar from '../../components/shared/toolbar'
import { ERRAND_SORTS, toErrandSort } from '../../utils/toolbar'
import { useErrandList } from '../../utils/use-errand-list'
import type { ErrandSort } from '../../types/order'
import './explore.css'

export default function ExplorePage() {
  const [query, setQuery] = useState('')
  const [sort, setSort] = useState<ErrandSort>(ERRAND_SORTS[0].value)
  const list = useErrandList('explore', 'active', query, sort)

  return (
    <main className="explore-content">
      <CreditBanner pending={list.pending} />
      <Toolbar
        subheader="Available Tasks"
        search={{
          value: query,
          onChange: setQuery,
          placeholder: 'Search errands',
          label: 'Search errands',
          maxLength: 100,
        }}
        sort={{
          options: ERRAND_SORTS,
          value: sort,
          onChange: (value) => setSort(toErrandSort(value) ?? sort),
          label: 'Sort available tasks',
        }}
      />
      <ErrandList
        list={list}
        viewer="explore"
        label="Available tasks"
        emptyText="No errands are waiting for a courier."
        onClearSearch={() => setQuery('')}
      />
    </main>
  )
}
