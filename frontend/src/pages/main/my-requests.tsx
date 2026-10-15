// AI Assistance Disclosure:
// Tool: Codex (OpenAI), date: 2026-10-15
// Scope: Composed the My Requests page from shared credit-banner and toolbar components.
// Author review: <to be completed by author>

import { useState } from 'react'
import CreditBanner from '../../components/shared/credit-banner'
import Toolbar from '../../components/shared/toolbar'
import Header from '../../components/shared/header'
import { ERRAND_SORTS, ERRAND_TABS } from '../../utils/toolbar'
import './explore.css'

export default function MyRequestsPage() {
  const [tab, setTab] = useState(ERRAND_TABS[0].value)
  const [query, setQuery] = useState('')
  const [sort, setSort] = useState(ERRAND_SORTS[0].value)

  return (
    <div className="explore-page">
      <Header initialSection="My Requests" />
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
      </main>
    </div>
  )
}
