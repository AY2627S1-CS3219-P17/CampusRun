// AI Assistance Disclosure:
// Tool: Claude Code (model: Claude Opus 5.5), date: 2026-11-09
// Scope: AI-generated the admin page: a banner like the Suppliers page and one tab per admin area, kept in the URL
//        (?tab=). Starts with the Users tab (docs/admin-dashboard-plan.md, Task 2).
// Author review: <to be completed by author>

import { Link, useSearchParams } from 'react-router'
import { Toast } from 'radix-ui'
import { useState } from 'react'
import { ArrowLeft } from 'lucide-react'
import AdminUsers from '../../components/admin/admin-users'
import './suppliers.css'
import './admin.css'

const TABS = [{ value: 'users', label: 'Users' }] as const
type AdminTab = (typeof TABS)[number]['value']

function isTab(value: string | null): value is AdminTab {
  return TABS.some((tab) => tab.value === value)
}

export default function AdminPage() {
  const [params, setParams] = useSearchParams()
  const requested = params.get('tab')
  const tab: AdminTab = isTab(requested) ? requested : 'users'
  // Errors from any tab, shown the same way as on the Suppliers page
  const [toast, setToast] = useState('')

  return (
    <Toast.Provider duration={5000} swipeDirection="right">
      <div className="suppliers-page">
        <main>
          <section className="suppliers-banner">
            <div>
              <Link
                className="suppliers-back"
                to="/explore"
                aria-label="Back to Explore"
              >
                <ArrowLeft size={20} aria-hidden="true" />
              </Link>
              <h1>Admin</h1>
              <p>Manage CampusRun's users, errands and delivery locations.</p>
            </div>
          </section>

          <div className="admin-body">
            <nav className="admin-tabs" aria-label="Admin sections">
              {TABS.map((item) => (
                <button
                  key={item.value}
                  type="button"
                  className={item.value === tab ? 'is-active' : ''}
                  aria-current={item.value === tab ? 'page' : undefined}
                  onClick={() => setParams({ tab: item.value })}
                >
                  {item.label}
                </button>
              ))}
            </nav>

            {tab === 'users' && <AdminUsers onError={setToast} />}
          </div>
        </main>
      </div>

      <Toast.Root
        className="supplier-toast"
        open={Boolean(toast)}
        onOpenChange={(open) => !open && setToast('')}
      >
        <Toast.Description>{toast}</Toast.Description>
      </Toast.Root>
      <Toast.Viewport className="supplier-toast-viewport" />
    </Toast.Provider>
  )
}
