import { useEffect, useMemo, useRef, useState } from 'react'
import { Link } from 'react-router'
import { DropdownMenu } from 'radix-ui'
import {
  ArrowLeft,
  Check,
  Clock,
  ChevronDown,
  Filter,
  MapPin,
  Plus,
  Search,
  Settings,
  Pencil,
  Power,
} from 'lucide-react'
import './suppliers.css'
import CreateSupplierDialog from '../components/update-supplier'
import { initialSuppliers } from '../api/supplier'
import type { Supplier, SupplierCategory } from '../types/supplier'

export default function SuppliersPage() {
  const [editor, setEditor] = useState<{ supplier?: Supplier } | null>(null)
  const editorTrigger = useRef<HTMLElement | null>(null)
  const createButton = useRef<HTMLButtonElement>(null)
  const [suppliers, setSuppliers] = useState<Supplier[]>(initialSuppliers)
  const [status, setStatus] = useState<'active' | 'deactivated'>('active')
  const [query, setQuery] = useState('')
  const [debouncedQuery, setDebouncedQuery] = useState('')
  const [selectedType, setSelectedType] = useState<
    SupplierCategory | 'All Types'
  >('All Types')

  useEffect(() => {
    const timeout = setTimeout(() => setDebouncedQuery(query), 300)
    return () => clearTimeout(timeout)
  }, [query])

  // Filter suppliers based on status, search query, and selected type
  const filteredSuppliers = useMemo(
    () =>
      suppliers.filter((supplier) => {
        const matchesStatus =
          status === 'active' ? supplier.active : !supplier.active

        const matchesQuery = `${supplier.name} ${supplier.location}`
          .toLowerCase()
          .includes(debouncedQuery.trim().toLowerCase())

        return (
          matchesStatus &&
          matchesQuery &&
          (selectedType === 'All Types' || supplier.type === selectedType)
        )
      }),
    [suppliers, status, debouncedQuery, selectedType],
  )

  return (
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
            <h1>Suppliers</h1>
            <p>Our supported suppliers.</p>
          </div>
        </section>

        <section className="supplier-directory" aria-label="Supplier directory">
          <div className="directory-toolbar">
            <div
              className="supplier-tabs"
              role="tablist"
              aria-label="Supplier status"
            >
              <button
                className={status === 'active' ? 'is-active' : ''}
                onClick={() => setStatus('active')}
                role="tab"
                aria-selected={status === 'active'}
              >
                Active
              </button>
              <button
                className={status === 'deactivated' ? 'is-active' : ''}
                onClick={() => setStatus('deactivated')}
                role="tab"
                aria-selected={status === 'deactivated'}
              >
                Deactivated
              </button>
            </div>

            <div className="directory-controls">
              <label className="supplier-search">
                <Search size={18} aria-hidden="true" />
                <input
                  value={query}
                  onChange={(event) => setQuery(event.target.value)}
                  placeholder="Search by name or location"
                  aria-label="Search suppliers by name or location"
                />
              </label>

              <DropdownMenu.Root modal={false}>
                <DropdownMenu.Trigger asChild>
                  <button
                    className="supplier-filter"
                    type="button"
                    aria-label={`Filter suppliers by type: ${selectedType}`}
                  >
                    <Filter size={16} aria-hidden="true" />
                    <span>{selectedType}</span>
                    <ChevronDown size={15} aria-hidden="true" />
                  </button>
                </DropdownMenu.Trigger>
                <DropdownMenu.Portal>
                  <DropdownMenu.Content
                    className="supplier-filter-menu"
                    align="end"
                    sideOffset={6}
                    collisionPadding={12}
                  >
                    <DropdownMenu.RadioGroup
                      value={selectedType}
                      onValueChange={(value) => {
                        if (
                          value === 'All Types' ||
                          value === 'Food' ||
                          value === 'Drinks' ||
                          value === 'Shopping' ||
                          value === 'Printing'
                        ) {
                          setSelectedType(value)
                        }
                      }}
                      aria-label="Supplier type"
                    >
                      <DropdownMenu.RadioItem
                        className="supplier-filter-option"
                        value="All Types"
                      >
                        All Types
                        <DropdownMenu.ItemIndicator>
                          <Check size={16} aria-hidden="true" />
                        </DropdownMenu.ItemIndicator>
                      </DropdownMenu.RadioItem>
                      <DropdownMenu.Separator className="supplier-filter-separator" />
                      {['Food', 'Drinks', 'Shopping', 'Printing'].map(
                        (type) => (
                          <DropdownMenu.RadioItem
                            className="supplier-filter-option"
                            key={type}
                            value={type}
                          >
                            {type}
                            <DropdownMenu.ItemIndicator>
                              <Check size={16} aria-hidden="true" />
                            </DropdownMenu.ItemIndicator>
                          </DropdownMenu.RadioItem>
                        ),
                      )}
                    </DropdownMenu.RadioGroup>
                  </DropdownMenu.Content>
                </DropdownMenu.Portal>
              </DropdownMenu.Root>

              {/* Admin Only */}
              <button
                className="create-supplier"
                type="button"
                aria-label="Create supplier"
                ref={createButton}
                onClick={(event) => {
                  editorTrigger.current = event.currentTarget
                  setEditor({})
                }}
              >
                <Plus size={18} aria-hidden="true" />
              </button>
            </div>
          </div>

          <div className="supplier-list" aria-live="polite">
            {filteredSuppliers.map((supplier) => (
              <article className="supplier-card" key={supplier.name}>
                <div>
                  <h2>{supplier.name}</h2>
                  <p className="supplier-location">
                    <MapPin size={16} aria-hidden="true" />
                    {supplier.location}
                  </p>
                  <p className="supplier-hours">
                    <Clock size={16} aria-hidden="true" />
                    <span>
                      {supplier.startTime} - {supplier.endTime}
                    </span>
                  </p>
                </div>
                <aside className="supplier-card-actions">
                  <span
                    className={`supplier-type supplier-type-${supplier.type.toLowerCase()}`}
                  >
                    {supplier.type}
                  </span>
                  <DropdownMenu.Root modal={false}>
                    <DropdownMenu.Trigger asChild>
                      <button
                        className="supplier-settings"
                        type="button"
                        aria-label={`Settings for ${supplier.name}`}
                        onFocus={(event) => {
                          editorTrigger.current = event.currentTarget
                        }}
                      >
                        <Settings size={18} aria-hidden="true" />
                      </button>
                    </DropdownMenu.Trigger>
                    <DropdownMenu.Portal>
                      <DropdownMenu.Content
                        className="supplier-filter-menu supplier-settings-menu"
                        onCloseAutoFocus={(event) => {
                          if (editor) event.preventDefault()
                        }}
                        align="end"
                        sideOffset={6}
                        collisionPadding={12}
                      >
                        <DropdownMenu.Item
                          className="supplier-filter-option supplier-settings-option"
                          onSelect={() => setEditor({ supplier })}
                        >
                          <Pencil size={16} aria-hidden="true" />
                          Edit
                        </DropdownMenu.Item>
                        <DropdownMenu.Item
                          className="supplier-filter-option supplier-settings-option"
                          onSelect={() =>
                            setSuppliers((current) =>
                              current.map((item) =>
                                item === supplier
                                  ? { ...item, active: !item.active }
                                  : item,
                              ),
                            )
                          }
                        >
                          <Power size={16} aria-hidden="true" />
                          {supplier.active ? 'Deactivate' : 'Activate'}
                        </DropdownMenu.Item>
                      </DropdownMenu.Content>
                    </DropdownMenu.Portal>
                  </DropdownMenu.Root>
                </aside>
              </article>
            ))}

            {filteredSuppliers.length === 0 && (
              <p className="supplier-empty">No suppliers found.</p>
            )}
          </div>
        </section>
      </main>
      {editor && (
        <CreateSupplierDialog
          supplier={editor.supplier}
          onClose={() => setEditor(null)}
          onRestoreFocus={() => {
            const trigger = editorTrigger.current
            if (trigger?.isConnected) trigger.focus()
            else createButton.current?.focus()
          }}
          onSave={(saved) => {
            setSuppliers((current) =>
              editor.supplier
                ? current.map((item) =>
                    item === editor.supplier ? saved : item,
                  )
                : [...current, saved],
            )
            if (!editor.supplier) {
              setStatus('active')
              setQuery('')
              setDebouncedQuery('')
              setSelectedType('All Types')
            }
          }}
        />
      )}
    </div>
  )
}
