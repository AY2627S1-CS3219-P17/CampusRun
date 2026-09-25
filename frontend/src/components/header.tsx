import { useRef, useState } from 'react'
import { Link } from 'react-router'
import { DropdownMenu } from 'radix-ui'
import { LogOut, MessageCircle, Plus, Store, UserRound } from 'lucide-react'
import EditInfoDialog from './edit-user-info'
import './header.css'

const sections = ['Explore', 'My Tasks', 'My Requests'] as const
type HeaderSection = (typeof sections)[number]

const sectionPaths: Record<HeaderSection, string> = {
  Explore: '/explore',
  'My Tasks': '/my-tasks',
  'My Requests': '/my-requests',
}

type HeaderProps = {
  initialSection: HeaderSection
}

export default function Header({ initialSection }: HeaderProps) {
  const [activeSection, setActiveSection] = useState(initialSection)
  const [editingInfo, setEditingInfo] = useState(false)
  const profileRef = useRef<HTMLButtonElement>(null)

  return (
    <header className="app-header">
      <nav className="header-nav" aria-label="Main navigation">
        {sections.map((section) => (
          <Link
            key={section}
            to={sectionPaths[section]}
            className="header-nav-item"
            aria-current={activeSection === section ? 'page' : undefined}
            onClick={() => setActiveSection(section)}
          >
            <span>{section}</span>
          </Link>
        ))}
      </nav>

      <div className="header-actions">
        <button
          className="header-icon-button header-secondary-action"
          type="button"
          aria-label="Messages"
        >
          <MessageCircle size={20} strokeWidth={1.8} aria-hidden="true" />
        </button>

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
          aria-label="Create request"
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
              <DropdownMenu.Item className="header-menu-item header-mobile-action">
                <MessageCircle size={18} aria-hidden="true" />
                Messages
              </DropdownMenu.Item>

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

              <DropdownMenu.Item className="header-menu-item" asChild>
                <Link to="/login" replace>
                  <LogOut size={18} aria-hidden="true" />
                  Logout
                </Link>
              </DropdownMenu.Item>
            </DropdownMenu.Content>
          </DropdownMenu.Portal>
        </DropdownMenu.Root>
      </div>

      {editingInfo && (
        <EditInfoDialog
          onClose={() => setEditingInfo(false)}
          onRestoreFocus={() => profileRef.current?.focus()}
        />
      )}
    </header>
  )
}
