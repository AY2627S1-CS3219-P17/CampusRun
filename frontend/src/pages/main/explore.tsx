// AI Assistance Disclosure:
// Tool: Codex (OpenAI), dates: 2026-10-15 and 2026-10-16
// Scope: Composed the Explore page from the reusable credit banner and shared toolbar components, then added one hardcoded available-task card.
// Author review: <to be completed by author>

import { useState } from 'react'
import { CalendarDays, CircleDollarSign, MapPin } from 'lucide-react'
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
        <article className="explore-task-card">
          <h2>Pick up printed notes</h2>
          <span className="explore-task-status">Open</span>
          <p className="explore-task-location">
            <MapPin size={16} aria-hidden="true" />
            <span>
              COM3 Print Shop&nbsp;&nbsp;&rarr;&nbsp;&nbsp;Central Library
            </span>
          </p>
          <p className="explore-task-due">
            <CalendarDays size={16} aria-hidden="true" />
            <span>Due 21 Apr, 5:00 PM</span>
          </p>
          <span className="explore-task-reward">
            <span>+10</span>
            <CircleDollarSign size={20} aria-hidden="true" />
          </span>
        </article>
      </main>
    </div>
  )
}
