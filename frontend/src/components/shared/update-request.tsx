// AI Assistance Disclosure:
// Tool: Codex (OpenAI), date: 2026-10-16
// Scope: Added the request dialog with supplier lookup, user-defined delivery location, validation, scrollable supplier menu, and a text-only AI Autofill view.
// Tool: OpenAI Codex (GPT-6), date: 2026-10-17
// Scope: Connected AI Autofill to order-service with prompt validation, loading lock, errors, partial form updates, prompt reset, and unmount cancellation.
// Tool: Claude Code (model: Claude Opus 5.5), date: 2026-10-19
// Scope: AI-connected Create to the Order Service with the server's field errors mapped onto the form; AI-added
//        edit mode, pre-filled from the errand, which validates and sends only the changed fields.
// Tool: Claude Code (model: Claude Opus 5.5), date: 2026-10-20
// Scope: AI-added the pickup and dropoff headings, and the predefined delivery location picker that fills the
//        dropoff fields and zooms the map to it.
// Author review: <to be completed by author>

import { useEffect, useRef, useState, type SubmitEvent } from 'react'
import { Dialog, DropdownMenu } from 'radix-ui'
import { Check, ChevronDown, MapPin, Search, Sparkles, X } from 'lucide-react'
import { listSuppliers } from '../../api/supplier'
import {
  autofillRequest,
  createErrand,
  editErrand,
  listPredefinedLocations,
} from '../../api/order'
import { ApiError } from '../../api/client'
import type { Supplier } from '../../types/supplier'
import type {
  CreateErrandPayload,
  DeliveryLocation,
  EditErrandPayload,
  Errand,
} from '../../types/order'
import { SUPPLIER_UNAVAILABLE } from '../../utils/errand'
import { notifyErrandsChanged } from '../../utils/errand-events'
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
type SupplierRef = Pick<Supplier, 'id' | 'name'>
type LocationRef = Pick<DeliveryLocation, 'id' | 'name'>

type Props = {
  // Edits this errand instead of creating one
  errand?: Errand
  onClose: () => void
  onRestoreFocus: () => void
  onCreated?: (errand: Errand) => void
}

const DAY_MS = 24 * 60 * 60_000
const PLACE_FIELDS: Field[] = ['building', 'floor', 'description', 'location']

// The Order Service's field names (422 errors) and the form's fields they belong to
const SERVER_FIELDS: Record<string, Field> = {
  title: 'title',
  supplierId: 'supplier',
  building: 'building',
  floor: 'floor',
  description: 'description',
  latitude: 'location',
  longitude: 'location',
  deliveryLocationId: 'location',
  deliverBy: 'deliveryBy',
  credits: 'credits',
  form: 'form',
}

function serverErrorsOf(error: unknown): Errors {
  if (!(error instanceof ApiError))
    return { form: 'Something went wrong. Please try again.' }

  const errors: Errors = {}
  for (const [field, message] of Object.entries(error.fieldErrors))
    errors[SERVER_FIELDS[field] ?? 'form'] ??= message
  if (Object.keys(errors).length === 0) errors.form = error.message
  return errors
}

function inputDate(date: Date) {
  const local = new Date(date.getTime() - date.getTimezoneOffset() * 60_000)
  return local.toISOString().slice(0, 16)
}

type Values = {
  title: string
  supplier: SupplierRef | null
  building: string
  floor: string
  description: string
  location: MapPosition | null
  // The predefined location the delivery point was filled from, until any of its fields is changed
  predefined: LocationRef | null
  deliveryBy: string
  credits: string
}

function initialValues(errand?: Errand): Values {
  if (!errand)
    return {
      title: '',
      supplier: null,
      building: '',
      floor: '',
      description: '',
      location: null,
      predefined: null,
      deliveryBy: inputDate(new Date(Date.now() + 30 * 60_000)),
      credits: '',
    }

  const place = errand.deliveryLocation
  return {
    title: errand.title,
    supplier: {
      id: errand.supplierId,
      name: errand.supplier?.name ?? SUPPLIER_UNAVAILABLE,
    },
    building: place.name,
    floor: place.floor ?? '',
    description: place.description ?? '',
    location: { latitude: place.latitude, longitude: place.longitude },
    predefined: place.predefined ? { id: place.id, name: place.name } : null,
    deliveryBy: inputDate(new Date(errand.deliverBy)),
    credits: String(errand.credits),
  }
}

// The fields that differ from what the form was filled with; a delivery point counts as one change
function changedFields(values: Values, initial: Values): Set<Field> {
  const changed = new Set<Field>()
  if (values.title.trim() !== initial.title) changed.add('title')
  if (values.supplier?.id !== initial.supplier?.id) changed.add('supplier')
  if (
    values.predefined?.id !== initial.predefined?.id ||
    values.building.trim() !== initial.building ||
    values.floor.trim() !== initial.floor ||
    values.description.trim() !== initial.description ||
    values.location?.latitude !== initial.location?.latitude ||
    values.location?.longitude !== initial.location?.longitude
  )
    PLACE_FIELDS.forEach((field) => changed.add(field))
  if (values.deliveryBy !== initial.deliveryBy) changed.add('deliveryBy')
  if (values.credits !== initial.credits) changed.add('credits')
  return changed
}

// The new delivery point, without an empty floor (the service rejects "")
function placeOf(values: Values) {
  return {
    building: values.building.trim(),
    floor: values.floor.trim() || undefined,
    description: values.description.trim(),
    latitude: values.location?.latitude ?? 0,
    longitude: values.location?.longitude ?? 0,
  }
}

function createPayload(values: Values): CreateErrandPayload {
  return {
    title: values.title.trim(),
    supplierId: values.supplier?.id ?? 0,
    ...(values.predefined
      ? { deliveryLocationId: values.predefined.id }
      : placeOf(values)),
    deliverBy: new Date(values.deliveryBy).toISOString(),
    credits: Number(values.credits),
  }
}

// Only what changed: resending an unchanged delivery point would save a new location each time
function editPayload(values: Values, changed: Set<Field>): EditErrandPayload {
  const payload: EditErrandPayload = {}
  if (changed.has('title')) payload.title = values.title.trim()
  if (changed.has('supplier') && values.supplier)
    payload.supplierId = values.supplier.id
  if (changed.has('location') && values.predefined)
    payload.deliveryLocationId = values.predefined.id
  else if (changed.has('location')) {
    // null clears a floor the old location had
    Object.assign(payload, placeOf(values), {
      floor: values.floor.trim() || null,
    })
  }
  if (changed.has('deliveryBy'))
    payload.deliverBy = new Date(values.deliveryBy).toISOString()
  if (changed.has('credits')) payload.credits = Number(values.credits)
  return payload
}

function validate(
  title: string,
  supplier: SupplierRef | null,
  building: string,
  floor: string,
  description: string,
  location: MapPosition | null,
  // A predefined location is valid as it is, e.g. without a description
  predefined: boolean,
  deliveryBy: string,
  credits: string,
  // The latest deadline allowed: 24 hours from now, or from when an edited errand was posted
  latest: number,
): Errors {
  const errors: Errors = {}
  const now = Date.now()
  const deliveryTime = new Date(deliveryBy).getTime()

  if (!title.trim()) errors.title = 'Required'
  else if (title.trim().length > 100) errors.title = 'At most 100 characters'

  if (!supplier) errors.supplier = 'Required'
  if (!predefined) {
    if (!building.trim()) errors.building = 'Building is required'
    else if (building.trim().length > 100)
      errors.building = 'At most 100 characters'

    if (floor.trim().length > 10) errors.floor = 'At most 10 characters'
    if (!description.trim()) errors.description = 'Required'
    else if (description.trim().length > 200)
      errors.description = 'At most 200 characters'

    if (!location) errors.location = 'Choose a location on the map'
  }

  if (!deliveryBy || Number.isNaN(deliveryTime)) errors.deliveryBy = 'Required'
  else if (deliveryTime < now + 15 * 60_000)
    errors.deliveryBy = 'At least 15 minutes from now'
  else if (deliveryTime > latest)
    errors.deliveryBy =
      latest < now + DAY_MS ? 'Within 24 hours of posting' : 'Within 24 hours'

  const creditValue = Number(credits)
  if (!/^\d+$/.test(credits) || creditValue < 1 || creditValue > 100)
    errors.credits = 'Whole number from 1 to 100'

  return errors
}

export default function UpdateRequestDialog({
  errand,
  onClose,
  onRestoreFocus,
  onCreated,
}: Props) {
  const editing = errand !== undefined
  const [initial] = useState(() => initialValues(errand))
  const [title, setTitle] = useState(initial.title)
  const [supplier, setSupplier] = useState<SupplierRef | null>(initial.supplier)
  const [supplierQuery, setSupplierQuery] = useState(
    initial.supplier?.name ?? '',
  )
  const [suppliers, setSuppliers] = useState<Supplier[]>([])
  const [supplierOpen, setSupplierOpen] = useState(false)
  const [supplierError, setSupplierError] = useState('')
  const [dialogContent, setDialogContent] = useState<HTMLDivElement | null>(
    null,
  )
  const [building, setBuilding] = useState(initial.building)
  const [floor, setFloor] = useState(initial.floor)
  const [description, setDescription] = useState(initial.description)
  const [location, setLocation] = useState<MapPosition | null>(initial.location)
  const [predefined, setPredefined] = useState<LocationRef | null>(
    initial.predefined,
  )
  // Where the map flies to: the predefined location just picked
  const [mapFocus, setMapFocus] = useState<MapPosition | null>(null)
  const [locationQuery, setLocationQuery] = useState('')
  const [locations, setLocations] = useState<DeliveryLocation[]>([])
  const [locationOpen, setLocationOpen] = useState(false)
  const [locationError, setLocationError] = useState('')
  const [deliveryBy, setDeliveryBy] = useState(initial.deliveryBy)
  const [credits, setCredits] = useState(initial.credits)
  const [saving, setSaving] = useState(false)
  const [touched, setTouched] = useState<Set<Field>>(new Set())
  const [submitted, setSubmitted] = useState(false)
  const [serverErrors, setServerErrors] = useState<Errors>({})
  const [aiView, setAiView] = useState(false)
  const [aiPrompt, setAiPrompt] = useState('')
  const [aiSubmitted, setAiSubmitted] = useState(false)
  const [aiLoading, setAiLoading] = useState(false)
  const [aiError, setAiError] = useState('')
  const aiRequest = useRef<AbortController | null>(null)
  // The dialog can't be closed while either request is in flight
  const busy = aiLoading || saving

  useEffect(() => () => aiRequest.current?.abort(), [])

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

  useEffect(() => {
    if (!locationOpen) return
    const controller = new AbortController()
    const timeout = setTimeout(() => {
      listPredefinedLocations(locationQuery, controller.signal)
        .then((page) => {
          setLocations(page.items)
          setLocationError('')
        })
        .catch((error: unknown) => {
          if (error instanceof DOMException && error.name === 'AbortError')
            return
          setLocationError('Could not load locations.')
        })
    }, 250)

    return () => {
      clearTimeout(timeout)
      controller.abort()
    }
  }, [locationOpen, locationQuery])

  const values: Values = {
    title,
    supplier,
    building,
    floor,
    description,
    location,
    predefined,
    deliveryBy,
    credits,
  }
  const now = new Date()
  const latestDelivery = errand
    ? Math.min(
        now.getTime() + DAY_MS,
        new Date(errand.createdAt).getTime() + DAY_MS,
      )
    : now.getTime() + DAY_MS
  const allErrors = validate(
    title,
    supplier,
    building,
    floor,
    description,
    location,
    predefined !== null,
    deliveryBy,
    credits,
    latestDelivery,
  )
  const changed = editing ? changedFields(values, initial) : null
  // An edit checks only what changed, so e.g. the title can still be fixed close to the deadline
  const clientErrors: Errors = changed
    ? Object.fromEntries(
        Object.entries(allErrors).filter(([field]) =>
          changed.has(field as Field),
        ),
      )
    : allErrors
  const errorFor = (field: Field) =>
    serverErrors[field] ??
    (submitted || touched.has(field) ? clientErrors[field] : undefined)
  const touch = (field: Field) =>
    setTouched((current) => new Set(current).add(field))
  const clearServerError = (field: Field) =>
    setServerErrors((current) => ({ ...current, [field]: undefined }))
  // Changing any of the delivery point's fields makes it a new location of the requester's own
  const detachPredefined = () => {
    setPredefined(null)
    setMapFocus(null)
  }

  function choosePredefined(option: DeliveryLocation) {
    const position = { latitude: option.latitude, longitude: option.longitude }
    setPredefined(option)
    setBuilding(option.name)
    setFloor(option.floor ?? '')
    setDescription(option.description ?? '')
    setLocation(position)
    setMapFocus(position)
    setServerErrors((current) => ({
      ...current,
      building: undefined,
      floor: undefined,
      description: undefined,
      location: undefined,
    }))
  }

  async function handleSubmit(event: SubmitEvent<HTMLFormElement>) {
    event.preventDefault()
    if (saving) return
    setSubmitted(true)
    setServerErrors({})
    if (Object.keys(clientErrors).length > 0) return
    if (errand && changed?.size === 0) {
      onClose()
      return
    }

    setSaving(true)
    try {
      const saved = errand
        ? await editErrand(errand.id, editPayload(values, changed ?? new Set()))
        : await createErrand(createPayload(values))
      notifyErrandsChanged()
      if (!errand) onCreated?.(saved)
      onClose()
    } catch (error) {
      setServerErrors(serverErrorsOf(error))
      // e.g. a courier accepted it meanwhile: show the lists what it is now
      if (error instanceof ApiError && error.status === 409)
        notifyErrandsChanged()
      setSaving(false)
    }
  }

  function showAiView() {
    setSupplierOpen(false)
    setLocationOpen(false)
    setAiView(true)
    dialogContent?.scrollTo({ top: 0 })
  }

  function showRequestForm() {
    setAiView(false)
    dialogContent?.scrollTo({ top: 0 })
  }

  async function handleAiSubmit(event: SubmitEvent<HTMLFormElement>) {
    event.preventDefault()
    if (aiLoading) return

    setAiSubmitted(true)
    setAiError('')

    const prompt = aiPrompt.trim()
    if (prompt.length < 20 || prompt.length > 500) return

    const controller = new AbortController()
    aiRequest.current = controller
    setAiLoading(true)
    try {
      const suggestion = await autofillRequest(prompt, controller.signal)
      if (suggestion.title !== null) setTitle(suggestion.title)
      if (suggestion.supplier !== null) {
        setSupplier(suggestion.supplier)
        setSupplierQuery(suggestion.supplier.name)
      }

      if (
        suggestion.building !== null ||
        suggestion.floor !== null ||
        suggestion.description !== null
      )
        detachPredefined()
      if (suggestion.building !== null) setBuilding(suggestion.building)
      if (suggestion.floor !== null) setFloor(suggestion.floor)
      if (suggestion.description !== null) {
        setDescription(suggestion.description)
      }

      if (suggestion.deliveryBy !== null) setDeliveryBy(suggestion.deliveryBy)
      if (suggestion.credits !== null) setCredits(String(suggestion.credits))

      setServerErrors({})
      setSubmitted(false)

      setTouched(new Set())
      setAiPrompt('')
      setAiSubmitted(false)
      showRequestForm()
    } catch (error) {
      if (controller.signal.aborted) return
      setAiError(
        error instanceof ApiError
          ? error.message
          : 'Could not autofill the request. Try again.',
      )
    } finally {
      if (aiRequest.current === controller) aiRequest.current = null
      if (!controller.signal.aborted) setAiLoading(false)
    }
  }

  const aiPromptError =
    aiSubmitted && aiPrompt.trim().length < 20 ? 'At least 20 characters' : ''

  const minDelivery = inputDate(new Date(now.getTime() + 15 * 60_000))
  const maxDelivery = inputDate(new Date(latestDelivery))

  return (
    <Dialog.Root open onOpenChange={(open) => !open && !busy && onClose()}>
      <Dialog.Portal>
        <Dialog.Overlay className="request-dialog-overlay" />
        <Dialog.Content
          ref={setDialogContent}
          className="request-dialog"
          aria-busy={busy}
          onEscapeKeyDown={(event) => {
            if (busy) event.preventDefault()
          }}
          onPointerDownOutside={(event) => {
            if (busy) event.preventDefault()
          }}
          onCloseAutoFocus={(event) => {
            event.preventDefault()
            onRestoreFocus()
          }}
        >
          <div className="request-dialog-heading" inert={busy}>
            <div className="request-dialog-heading-main">
              <Dialog.Title>
                {aiView
                  ? 'AI Autofill'
                  : editing
                    ? 'Edit Request'
                    : 'Create Request'}
              </Dialog.Title>
              {!aiView && !editing && (
                <button
                  className="request-ai-trigger"
                  type="button"
                  aria-label="Describe request with AI"
                  onClick={showAiView}
                >
                  <Sparkles size={19} aria-hidden="true" />
                </button>
              )}
            </div>
            <Dialog.Close className="request-dialog-close" aria-label="Close">
              <X size={20} aria-hidden="true" />
            </Dialog.Close>
          </div>

          {aiView ? (
            <form
              className="request-ai-form"
              noValidate
              inert={aiLoading}
              onSubmit={(event) => {
                void handleAiSubmit(event)
              }}
            >
              <p className="request-ai-description">
                Describe your request, the supplier, where to deliver it, when
                you need it by, and the credits you are offering. Try to include
                all details.
              </p>
              <label htmlFor="request-ai-prompt">Description</label>
              <textarea
                id="request-ai-prompt"
                autoFocus
                required
                minLength={20}
                maxLength={500}
                aria-invalid={aiPromptError ? true : undefined}
                aria-describedby="request-ai-prompt-help"
                rows={8}
                value={aiPrompt}
                placeholder="Pick up my printed notes from the COM3 print shop and deliver them to the Central Library entrance by 5 pm. I can offer 10 credits."
                onChange={(event) => {
                  setAiPrompt(event.target.value)
                  setAiError('')
                }}
              />
              <div
                id="request-ai-prompt-help"
                className="request-ai-prompt-help"
              >
                <span>{aiPromptError || '\u00a0'}</span>
                <span>{aiPrompt.length}/500</span>
              </div>
              {aiError && (
                <p className="request-dialog-error" role="alert">
                  {aiError}
                </p>
              )}
              <div className="request-dialog-footer">
                <button type="button" onClick={showRequestForm}>
                  Back
                </button>
                <button type="submit">Submit</button>
              </div>
            </form>
          ) : (
            <form
              noValidate
              inert={busy}
              onSubmit={(event) => {
                void handleSubmit(event)
              }}
            >
              <div className="request-dialog-section">
                <label>
                  Title
                  <input
                    value={title}
                    placeholder="Pick up printed notes"
                    onChange={(event) => {
                      setTitle(event.target.value)
                      clearServerError('title')
                    }}
                    onBlur={() => touch('title')}
                    aria-invalid={errorFor('title') ? true : undefined}
                  />
                  {errorFor('title') && <small>{errorFor('title')}</small>}
                </label>
              </div>

              <div className="request-dialog-section">
                <h3 className="request-dialog-section-title">Select pickup</h3>
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
                  {errorFor('supplier') && (
                    <small>{errorFor('supplier')}</small>
                  )}
                </div>
              </div>

              <div className="request-dialog-section">
                <h3 className="request-dialog-section-title">Select dropoff</h3>
                <div className="request-field">
                  <span>Predefined location</span>
                  <DropdownMenu.Root
                    open={locationOpen}
                    onOpenChange={setLocationOpen}
                    modal={false}
                  >
                    <DropdownMenu.Trigger asChild>
                      <button
                        className="request-supplier-trigger"
                        type="button"
                      >
                        <span>
                          {predefined?.name ??
                            'Choose a campus location, or enter your own below'}
                        </span>
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
                            value={locationQuery}
                            placeholder="Search locations"
                            aria-label="Search locations"
                            onChange={(event) =>
                              setLocationQuery(event.target.value)
                            }
                            onKeyDown={(event) => event.stopPropagation()}
                          />
                        </label>
                        {locationError ? (
                          <p>{locationError}</p>
                        ) : locations.length ? (
                          locations.map((option) => (
                            <DropdownMenu.Item
                              className="request-supplier-option"
                              key={option.id}
                              onSelect={() => choosePredefined(option)}
                            >
                              <span>
                                <strong>{option.name}</strong>
                                {option.description && (
                                  <small>{option.description}</small>
                                )}
                              </span>
                              {predefined?.id === option.id && (
                                <Check size={16} aria-hidden="true" />
                              )}
                            </DropdownMenu.Item>
                          ))
                        ) : (
                          <p>No locations found.</p>
                        )}
                      </DropdownMenu.Content>
                    </DropdownMenu.Portal>
                  </DropdownMenu.Root>
                </div>

                <div className="request-dialog-row-group">
                  <div className="request-dialog-row">
                    <label>
                      Building
                      <input
                        value={building}
                        placeholder="COM3"
                        onChange={(event) => {
                          setBuilding(event.target.value)
                          detachPredefined()
                          clearServerError('building')
                        }}
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
                        onChange={(event) => {
                          setFloor(event.target.value)
                          detachPredefined()
                          clearServerError('floor')
                        }}
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
                    onChange={(event) => {
                      setDescription(event.target.value)
                      detachPredefined()
                      clearServerError('description')
                    }}
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
                    focus={mapFocus}
                    redPin={predefined !== null}
                    onChange={(position) => {
                      setLocation(position)
                      detachPredefined()
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
                      : 'Click the map to choose a delivery location'}
                  </span>
                  {errorFor('location') && (
                    <small>{errorFor('location')}</small>
                  )}
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
                    onChange={(event) => {
                      setDeliveryBy(event.target.value)
                      clearServerError('deliveryBy')
                    }}
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
                    onChange={(event) => {
                      setCredits(event.target.value)
                      clearServerError('credits')
                    }}
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
                <button type="submit" disabled={saving}>
                  {saving
                    ? editing
                      ? 'Saving...'
                      : 'Creating...'
                    : editing
                      ? 'Save'
                      : 'Create'}
                </button>
              </div>
            </form>
          )}
          {aiLoading && (
            <div
              className="request-ai-loading"
              role="status"
              aria-live="polite"
            >
              <span className="request-ai-spinner" aria-hidden="true" />
              Filling your request...
            </div>
          )}
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  )
}
