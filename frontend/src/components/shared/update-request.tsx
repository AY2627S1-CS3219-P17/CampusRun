// AI Assistance Disclosure:
// Tool: Codex (OpenAI), date: 2026-10-16
// Scope: Added the request dialog with supplier lookup, user-defined delivery location, validation, and scrollable supplier menu.
// Author review: <to be completed by author>

import { useEffect, useState, type SubmitEvent } from 'react'
import { Dialog, DropdownMenu } from 'radix-ui'
import { Check, ChevronDown, MapPin, Search, X } from 'lucide-react'
import { listSuppliers } from '../../api/supplier'
import type { Supplier } from '../../types/supplier'
import { type MapPosition } from '../../utils/map'
import InteractiveMap from './interactive-map'
import './update-request.css'

type Field =
  | 'title'
  | 'supplier'
  | 'building'
  | 'floor'
  | 'description'
  | 'location'
  | 'deliveryBy'
  | 'credits'
  | 'form'

type Errors = Partial<Record<Field, string>>

type Props = {
  onClose: () => void
  onRestoreFocus: () => void
}

function inputDate(date: Date) {
  const local = new Date(date.getTime() - date.getTimezoneOffset() * 60_000)
  return local.toISOString().slice(0, 16)
}

function validate(
  title: string,
  supplier: Supplier | null,
  building: string,
  floor: string,
  description: string,
  location: MapPosition | null,
  deliveryBy: string,
  credits: string,
): Errors {
  const errors: Errors = {}
  const now = Date.now()
  const deliveryTime = new Date(deliveryBy).getTime()

  if (!title.trim()) errors.title = 'Required'
  else if (title.trim().length > 100) errors.title = 'At most 100 characters'

  if (!supplier) errors.supplier = 'Required'
  if (!building.trim()) errors.building = 'Building is required'
  else if (building.trim().length > 100)
    errors.building = 'At most 100 characters'

  if (floor.trim().length > 10) errors.floor = 'At most 10 characters'
  if (!description.trim()) errors.description = 'Required'
  else if (description.trim().length > 200)
    errors.description = 'At most 200 characters'

  if (!location) errors.location = 'Choose a location on the map'

  if (!deliveryBy || Number.isNaN(deliveryTime)) errors.deliveryBy = 'Required'
  else if (deliveryTime < now + 15 * 60_000)
    errors.deliveryBy = 'At least 15 minutes from now'
  else if (deliveryTime > now + 24 * 60 * 60_000)
    errors.deliveryBy = 'Within 24 hours'

  const creditValue = Number(credits)
  if (!/^\d+$/.test(credits) || creditValue < 1 || creditValue > 100)
    errors.credits = 'Whole number from 1 to 100'

  return errors
}

export default function UpdateRequestDialog({
  onClose,
  onRestoreFocus,
}: Props) {
  const [title, setTitle] = useState('')
  const [supplier, setSupplier] = useState<Supplier | null>(null)
  const [supplierQuery, setSupplierQuery] = useState('')
  const [suppliers, setSuppliers] = useState<Supplier[]>([])
  const [supplierOpen, setSupplierOpen] = useState(false)
  const [supplierError, setSupplierError] = useState('')
  const [dialogContent, setDialogContent] = useState<HTMLDivElement | null>(
    null,
  )
  const [building, setBuilding] = useState('')
  const [floor, setFloor] = useState('')
  const [description, setDescription] = useState('')
  const [location, setLocation] = useState<MapPosition | null>(null)
  const [deliveryBy, setDeliveryBy] = useState(() =>
    inputDate(new Date(Date.now() + 30 * 60_000)),
  )
  const [credits, setCredits] = useState('')
  const [touched, setTouched] = useState<Set<Field>>(new Set())
  const [submitted, setSubmitted] = useState(false)
  const [serverErrors, setServerErrors] = useState<Errors>({})

  useEffect(() => {
    if (!supplierOpen) return
    const controller = new AbortController()
    const timeout = setTimeout(() => {
      listSuppliers(
        {
          q: supplierQuery,
          type: null,
          active: true,
          sort: 'name',
          page: 1,
          pageSize: 20,
        },
        controller.signal,
      )
        .then((page) => {
          setSuppliers(page.items)
          setSupplierError('')
        })
        .catch((error: unknown) => {
          if (error instanceof DOMException && error.name === 'AbortError')
            return
          setSupplierError('Could not load suppliers.')
        })
    }, 250)

    return () => {
      clearTimeout(timeout)
      controller.abort()
    }
  }, [supplierOpen, supplierQuery])

  const clientErrors = validate(
    title,
    supplier,
    building,
    floor,
    description,
    location,
    deliveryBy,
    credits,
  )
  const errorFor = (field: Field) =>
    serverErrors[field] ??
    (submitted || touched.has(field) ? clientErrors[field] : undefined)
  const touch = (field: Field) =>
    setTouched((current) => new Set(current).add(field))

  function handleSubmit(event: SubmitEvent<HTMLFormElement>) {
    event.preventDefault()
    setSubmitted(true)
    setServerErrors({})
    if (Object.keys(clientErrors).length > 0) return

    setServerErrors({
      form: 'The order service is not connected yet. Your request was not created.',
    })
  }

  const now = new Date()
  const minDelivery = inputDate(new Date(now.getTime() + 15 * 60_000))
  const maxDelivery = inputDate(new Date(now.getTime() + 24 * 60 * 60_000))

  return (
    <Dialog.Root open onOpenChange={(open) => !open && onClose()}>
      <Dialog.Portal>
        <Dialog.Overlay className="request-dialog-overlay" />
        <Dialog.Content
          ref={setDialogContent}
          className="request-dialog"
          onCloseAutoFocus={(event) => {
            event.preventDefault()
            onRestoreFocus()
          }}
        >
          <div className="request-dialog-heading">
            <Dialog.Title>Create Request</Dialog.Title>
            <Dialog.Close className="request-dialog-close" aria-label="Close">
              <X size={20} aria-hidden="true" />
            </Dialog.Close>
          </div>

          <form noValidate onSubmit={handleSubmit}>
            <div className="request-dialog-section">
              <label>
                Title
                <input
                  value={title}
                  placeholder="Pick up printed notes"
                  onChange={(event) => setTitle(event.target.value)}
                  onBlur={() => touch('title')}
                  aria-invalid={errorFor('title') ? true : undefined}
                />
                {errorFor('title') && <small>{errorFor('title')}</small>}
              </label>

              <div className="request-field">
                <span>Supplier</span>
                <DropdownMenu.Root
                  open={supplierOpen}
                  onOpenChange={setSupplierOpen}
                  modal={false}
                >
                  <DropdownMenu.Trigger asChild>
                    <button
                      className="request-supplier-trigger"
                      type="button"
                      aria-invalid={errorFor('supplier') ? true : undefined}
                      onBlur={() => touch('supplier')}
                    >
                      <span>{supplier?.name ?? 'Choose a supplier'}</span>
                      <ChevronDown size={16} aria-hidden="true" />
                    </button>
                  </DropdownMenu.Trigger>
                  <DropdownMenu.Portal container={dialogContent}>
                    <DropdownMenu.Content
                      className="request-supplier-menu"
                      align="start"
                      sideOffset={6}
                      collisionPadding={12}
                    >
                      <label className="request-supplier-search">
                        <Search size={16} aria-hidden="true" />
                        <input
                          value={supplierQuery}
                          placeholder="Search suppliers"
                          aria-label="Search suppliers"
                          onChange={(event) =>
                            setSupplierQuery(event.target.value)
                          }
                          onKeyDown={(event) => event.stopPropagation()}
                        />
                      </label>
                      {supplierError ? (
                        <p>{supplierError}</p>
                      ) : suppliers.length ? (
                        suppliers.map((option) => (
                          <DropdownMenu.Item
                            className="request-supplier-option"
                            key={option.id}
                            onSelect={() => {
                              setSupplier(option)
                              setSupplierQuery(option.name)
                              setServerErrors((current) => ({
                                ...current,
                                supplier: undefined,
                              }))
                            }}
                          >
                            <span>
                              <strong>{option.name}</strong>
                              <small>{option.location}</small>
                            </span>
                            {supplier?.id === option.id && (
                              <Check size={16} aria-hidden="true" />
                            )}
                          </DropdownMenu.Item>
                        ))
                      ) : (
                        <p>No suppliers found.</p>
                      )}
                    </DropdownMenu.Content>
                  </DropdownMenu.Portal>
                </DropdownMenu.Root>
                {errorFor('supplier') && <small>{errorFor('supplier')}</small>}
              </div>
            </div>

            <div className="request-dialog-section">
              <div className="request-dialog-row-group">
                <div className="request-dialog-row">
                  <label>
                    Building
                    <input
                      value={building}
                      placeholder="COM3"
                      onChange={(event) => setBuilding(event.target.value)}
                      onBlur={() => touch('building')}
                      aria-invalid={errorFor('building') ? true : undefined}
                      aria-describedby={
                        errorFor('building')
                          ? 'request-building-error'
                          : undefined
                      }
                    />
                  </label>
                  <label>
                    Floor
                    <input
                      value={floor}
                      placeholder="1 (optional)"
                      onChange={(event) => setFloor(event.target.value)}
                      onBlur={() => touch('floor')}
                      aria-invalid={errorFor('floor') ? true : undefined}
                      aria-describedby={
                        errorFor('floor') ? 'request-floor-error' : undefined
                      }
                    />
                  </label>
                </div>
                {(errorFor('building') || errorFor('floor')) && (
                  <div className="request-dialog-row-errors">
                    {errorFor('building') && (
                      <small id="request-building-error">
                        {errorFor('building')}
                      </small>
                    )}
                    {errorFor('floor') && (
                      <small id="request-floor-error">
                        {errorFor('floor')}
                      </small>
                    )}
                  </div>
                )}
              </div>

              <label>
                Description
                <input
                  value={description}
                  placeholder="Next to LT19"
                  onChange={(event) => setDescription(event.target.value)}
                  onBlur={() => touch('description')}
                  aria-invalid={errorFor('description') ? true : undefined}
                />
                {errorFor('description') && (
                  <small>{errorFor('description')}</small>
                )}
              </label>

              <div className="request-field">
                <span>Location</span>
                <InteractiveMap
                  value={location}
                  ariaLabel="Choose location on map"
                  onChange={(position) => {
                    setLocation(position)
                    setServerErrors((current) => ({
                      ...current,
                      location: undefined,
                    }))
                  }}
                />
                <span className="request-dialog-hint">
                  <MapPin size={14} aria-hidden="true" />
                  {location
                    ? `${location.latitude.toFixed(5)}, ${location.longitude.toFixed(5)}`
                    : 'Click the map to choose a location'}
                </span>
                {errorFor('location') && <small>{errorFor('location')}</small>}
              </div>
            </div>

            <div className="request-dialog-section request-dialog-section-last">
              <label>
                Deliver By
                <input
                  type="datetime-local"
                  value={deliveryBy}
                  min={minDelivery}
                  max={maxDelivery}
                  onChange={(event) => setDeliveryBy(event.target.value)}
                  onBlur={() => touch('deliveryBy')}
                  onClick={(event) => event.currentTarget.showPicker?.()}
                  aria-invalid={errorFor('deliveryBy') ? true : undefined}
                />
                {errorFor('deliveryBy') && (
                  <small>{errorFor('deliveryBy')}</small>
                )}
              </label>

              <label>
                Credits
                <input
                  type="number"
                  min="1"
                  max="100"
                  step="1"
                  value={credits}
                  placeholder="10"
                  onChange={(event) => setCredits(event.target.value)}
                  onBlur={() => touch('credits')}
                  aria-invalid={errorFor('credits') ? true : undefined}
                />
                {errorFor('credits') && <small>{errorFor('credits')}</small>}
              </label>
            </div>

            {serverErrors.form && (
              <p className="request-dialog-error" role="alert">
                {serverErrors.form}
              </p>
            )}

            <div className="request-dialog-footer">
              <Dialog.Close type="button">Cancel</Dialog.Close>
              <button type="submit">Create</button>
            </div>
          </form>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  )
}
