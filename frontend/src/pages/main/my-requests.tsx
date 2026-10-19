// AI Assistance Disclosure:
// Tool: Codex (OpenAI), dates: 2026-10-15 and 2026-10-16
// Scope: Composed My Requests with negative-credit sample cards, per-tab pagination, and an Open Active request.
// Tool: Codex (OpenAI), date: 2026-10-17
// Scope: Shows task details settings only for Open request cards.
// Tool: Codex (OpenAI), date: 2026-10-17
// Scope: Labels the user as You in My Requests task details.
// Tool: Codex (OpenAI), date: 2026-10-17
// Scope: Showed Cancel and Completed header actions for active requests and limited Edit to Open.
// Tool: Codex (OpenAI), date: 2026-10-17
// Scope: Simplified action label typing and per-tab pagination initialization.
// Tool: Claude Code (model: Claude Opus 5.5), date: 2026-10-19
// Scope: AI-replaced the sample requests with My Requests from the Order Service, loaded as the list scrolls.
// Tool: Claude Code (model: Claude Opus 5.5), date: 2026-10-19
// Scope: AI-moved the card actions into the shared errand mapper.
// Author review: <to be completed by author>

import { useState } from 'react'
import CreditBanner from '../../components/shared/credit-banner'
import ErrandList from '../../components/shared/errand-list'
import Toolbar from '../../components/shared/toolbar'
import Header from '../../components/shared/header'
import {
  ERRAND_SORTS,
  ERRAND_TABS,
  toErrandSort,
  toErrandTab,
} from '../../utils/toolbar'
import { useErrandList } from '../../utils/use-errand-list'
import type { ErrandSort, ErrandTab } from '../../types/order'
import './explore.css'

export default function MyRequestsPage() {
  const [tab, setTab] = useState<ErrandTab>(ERRAND_TABS[0].value)
  const [query, setQuery] = useState('')
  const [sort, setSort] = useState<ErrandSort>(ERRAND_SORTS[0].value)
  const list = useErrandList('requests', tab, query, sort)

  return (
    <div className="explore-page my-requests-page">
      <Header initialSection="My Requests" />
      <main className="explore-content">
        <CreditBanner pending={list.pending} />
        <Toolbar
          tabs={{
            options: ERRAND_TABS,
            value: tab,
            onChange: (value) => setTab(toErrandTab(value) ?? tab),
            label: 'Errand status',
          }}
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
            label: 'Sort errands',
          }}
        />
        <ErrandList
          list={list}
          viewer="requester"
          label={`${tab} requests`}
          emptyText={`You have no ${tab} requests.`}
          onClearSearch={() => setQuery('')}
        />
      </main>
    </div>
  )
}
