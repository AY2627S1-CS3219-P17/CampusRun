// AI Assistance Disclosure:
// Tool: Codex (OpenAI), date: 2026-10-15
// Scope: Extracted the reusable active and reserved credit banner component.
// Author review: <to be completed by author>

import { CircleDollarSign } from 'lucide-react'
import sharedBanner from '../../assets/shared_banner.png'
import './credit-banner.css'

export default function CreditBanner() {
  return (
    <section
      className="credit-banner"
      style={{ backgroundImage: `url(${sharedBanner})` }}
      aria-label="Your credits: 120 active, 30 reserved"
    >
      <div className="credit-banner-summary">
        <p>Total Credits</p>
        <div className="credit-banner-balance">
          <span className="credit-banner-active">
            <CircleDollarSign size={30} strokeWidth={2} aria-hidden="true" />
            <span className="credit-banner-value">70</span>
            <small>Active</small>
          </span>
          <span className="credit-banner-reserved">
            <CircleDollarSign size={30} strokeWidth={2} aria-hidden="true" />
            <span className="credit-banner-value">30</span>
            <small>Reserved</small>
          </span>
        </div>
      </div>
    </section>
  )
}
