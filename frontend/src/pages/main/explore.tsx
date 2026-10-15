// AI Assistance Disclosure:
// Tool: Codex (OpenAI), date: 2026-10-15
// Scope: Composed the Explore page from the reusable credit banner and shared toolbar components.
// Author review: <to be completed by author>

import { useState } from 'react'
import CreditBanner from '../../components/shared/credit-banner'
import Toolbar from '../../components/shared/toolbar'
import Header from '../../components/shared/header'
import { ERRAND_SORTS } from '../../utils/toolbar'
import './explore.css'

export default function ExplorePage() {
  const [query, setQuery] = useState('')
  const [sort, setSort] = useState(ERRAND_SORTS[0].value)

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
      </main>
    </div>
  )
}
