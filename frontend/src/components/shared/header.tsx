// AI Assistance Disclosure:
// Tool: Claude (claude.ai chat, model: Claude Opus 5.5), date: 2026-09-26
// Scope: AI-modified: Logout also forgets the saved access token (clearSession).
// Author review: Validated logout cleanup and navigation behavior.
// Tool: Claude Code (model: Claude Opus 5.5), date: 2026-09-28
// Scope: AI-hid the errand sections and create-request button from admins; AI-showed them again, since admins
//        keep every student capability (2026-09-28).
// Author review: <to be completed by author>
// Tool: Codex (OpenAI), date: 2026-10-15
// Scope: Wired the create-request header action to the shared request editor dialog.
// Tool: Codex (OpenAI), date: 2026-10-17
// Scope: Removed duplicated navigation state and derived the active section from the page prop.
// Tool: Claude Code (model: Claude Opus 5.5), date: 2026-10-19
// Scope: AI-added opening My Requests after a request is created.
// Tool: OpenAI Codex (GPT-6), date: 2026-10-20
// Scope: Derived the active navigation link from the route in the persistent main layout.
// Author review: <to be completed by author>

import { useRef, useState } from 'react'
import { Link, useLocation, useNavigate } from 'react-router'
import { DropdownMenu } from 'radix-ui'
import { LogOut, Plus, Store, UserRound } from 'lucide-react'
import EditInfoDialog from './edit-user-info'
import UpdateRequestDialog from './update-request'
import { clearSession } from '../../utils/session'
import './header.css'

const sections = ['Explore', 'My Tasks', 'My Requests'] as const
type HeaderSection = (typeof sections)[number]

const sectionPaths: Record<HeaderSection, string> = {
  Explore: '/explore',
  'My Tasks': '/my-tasks',
  'My Requests': '/my-requests',
}

export default function Header() {
  const { pathname } = useLocation()
  const [editingInfo, setEditingInfo] = useState(false)
  const [creatingRequest, setCreatingRequest] = useState(false)
  const navigate = useNavigate()
  const createRef = useRef<HTMLButtonElement>(null)
  const profileRef = useRef<HTMLButtonElement>(null)

  return (
    <header className="app-header">
      <nav className="header-nav" aria-label="Main navigation">
        {sections.map((section) => (
          <Link
            key={section}
            to={sectionPaths[section]}
            className="header-nav-item"
            aria-current={
              pathname === sectionPaths[section] ? 'page' : undefined
            }
          >
            <span>{section}</span>
          </Link>
        ))}
      </nav>

      <div className="header-actions">
        <Link
          to="/suppliers"
          className="header-icon-button header-secondary-action"
          aria-label="Supplier"
        >
          <Store size={20} strokeWidth={1.8} aria-hidden="true" />
        </Link>

        <button
          className="header-icon-button header-create"
          type="button"
          ref={createRef}
          aria-label="Create request"
          onClick={() => setCreatingRequest(true)}
        >
          <Plus size={22} strokeWidth={1.8} aria-hidden="true" />
        </button>

        <DropdownMenu.Root>
          <DropdownMenu.Trigger asChild>
            <button
              className="header-icon-button header-profile"
              type="button"
              ref={profileRef}
              aria-label="Profile menu"
            >
              <UserRound size={22} strokeWidth={1.8} aria-hidden="true" />
            </button>
          </DropdownMenu.Trigger>

          <DropdownMenu.Portal>
            <DropdownMenu.Content
              className="header-menu"
              align="end"
              sideOffset={10}
              collisionPadding={12}
              onCloseAutoFocus={(event: Event) => {
                // Keep focus on the dialog
                if (editingInfo) event.preventDefault()
              }}
            >
              <DropdownMenu.Item
                className="header-menu-item"
                onSelect={() => setEditingInfo(true)}
              >
                <UserRound size={18} aria-hidden="true" />
                Edit info
              </DropdownMenu.Item>

              {/* These two below only visible for mobile widths */}
              <DropdownMenu.Item
                className="header-menu-item header-mobile-action"
                asChild
              >
                <Link to="/suppliers">
                  <Store size={18} aria-hidden="true" />
                  Suppliers
                </Link>
              </DropdownMenu.Item>

              <DropdownMenu.Separator className="header-menu-separator" />

              <DropdownMenu.Item
                className="header-menu-item"
                asChild
                onSelect={clearSession}
              >
                <Link to="/login" replace>
                  <LogOut size={18} aria-hidden="true" />
                  Logout
                </Link>
              </DropdownMenu.Item>
            </DropdownMenu.Content>
          </DropdownMenu.Portal>
        </DropdownMenu.Root>
      </div>

      {creatingRequest && (
        <UpdateRequestDialog
          onClose={() => setCreatingRequest(false)}
          onCreated={() => {
            setCreatingRequest(false)
            void navigate('/my-requests')
          }}
          onRestoreFocus={() => createRef.current?.focus()}
        />
      )}

      {editingInfo && (
        <EditInfoDialog
          onClose={() => setEditingInfo(false)}
          onRestoreFocus={() => profileRef.current?.focus()}
        />
      )}
    </header>
  )
}
