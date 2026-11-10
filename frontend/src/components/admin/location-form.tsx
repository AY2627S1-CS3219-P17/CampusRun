// AI Assistance Disclosure:
// Tool: Claude Code (model: Claude Opus 5.5), date: 2026-11-10
// Scope: AI-generated the admin form to add or edit a predefined delivery location (name, floor, description and a
//        map position) and to deactivate or reactivate it, showing the Order Service's 409 and 422 errors. Adapted
//        from components/supplier/update-supplier.tsx and reuses its styles.
// Author review: I verified the UI: adding and editing a location saves and shows field errors.

import { useState, type InputHTMLAttributes, type SubmitEvent } from 'react'
import { Dialog } from 'radix-ui'
import { MapPin, X } from 'lucide-react'
import InteractiveMap from '../shared/interactive-map'
import { ApiError } from '../../api/client'
import { createLocation, updateLocation } from '../../api/order'
import type { DeliveryLocation, LocationPayload } from '../../types/order'
import type { MapPosition } from '../../utils/map'
import '../supplier/update-supplier.css'

type Field = 'name' | 'floor' | 'description' | 'latitude' | 'longitude'
type Values = { name: string; floor: string; description: string }
type Errors = Partial<Record<Field | 'form', string>>

// The Order Service's limits (order-service/src/order_service/tables.py)
const MAX_LENGTH = { name: 100, floor: 10, description: 300 }

function toPayload(values: Values, position: MapPosition): LocationPayload {
  return {
    name: values.name.trim(),
    floor: values.floor.trim() || null,
    description: values.description.trim() || null,
    latitude: position.latitude,
    longitude: position.longitude,
  }
}

function validate(values: Values, position: MapPosition | null): Errors {
  const errors: Errors = {}
  if (!values.name.trim()) errors.name = 'Required'
  for (const field of ['name', 'floor', 'description'] as const) {
    if (values[field].trim().length > MAX_LENGTH[field])
      errors[field] = `Use at most ${MAX_LENGTH[field]} characters.`
  }
  // Whether it's inside the served area is checked by the map and again by the service
  if (!position) errors.latitude = 'Choose a location on the map'
  return errors
}

function messageOf(error: unknown) {
  return error instanceof ApiError
    ? error.message
    : 'Could not save the location. Please try again.'
}

export default function LocationForm({
  location,
  onSave,
  onClose,
}: {
  // Absent when adding a new one
  location?: DeliveryLocation
  onSave: (saved: DeliveryLocation) => void
  onClose: () => void
}) {
  const [values, setValues] = useState<Values>({
    name: location?.name ?? '',
    floor: location?.floor ?? '',
    description: location?.description ?? '',
  })
  const [position, setPosition] = useState<MapPosition | null>(
    location
      ? { latitude: location.latitude, longitude: location.longitude }
      : null,
  )
  const [touched, setTouched] = useState<Set<Field>>(new Set())
  const [submitted, setSubmitted] = useState(false)
  const [serverErrors, setServerErrors] = useState<Errors>({})
  const [saving, setSaving] = useState(false)

  const clientErrors = validate(values, position)
  const errorFor = (field: Field) =>
    serverErrors[field] ??
    (submitted || touched.has(field) ? clientErrors[field] : undefined)
  const positionError = errorFor('latitude') ?? errorFor('longitude')

  function update(field: keyof Values, value: string) {
    setValues((current) => ({ ...current, [field]: value }))
    setServerErrors((current) => ({ ...current, [field]: undefined }))
  }

  function updatePosition(next: MapPosition) {
    setPosition(next)
    setServerErrors((current) => ({
      ...current,
      latitude: undefined,
      longitude: undefined,
    }))
  }

  function showError(error: unknown, isCreate: boolean) {
    if (error instanceof ApiError && error.status === 409) {
      // On create it can only be a duplicate name; on edit it may also be a courier on the way, so it goes on top
      setServerErrors(
        isCreate ? { name: error.message } : { form: error.message },
      )
    } else if (error instanceof ApiError) {
      // 422: e.g. a position outside the served area, under the map
      setServerErrors({ form: error.message, ...error.fieldErrors })
    } else {
      setServerErrors({ form: messageOf(error) })
    }
  }

  async function handleSubmit(event: SubmitEvent<HTMLFormElement>) {
    event.preventDefault()
    if (saving) return
    setSubmitted(true)
    if (Object.keys(clientErrors).length > 0 || !position) return

    const payload = toPayload(values, position)
    let changes: Partial<LocationPayload> = payload
    if (location) {
      // Only send what changed
      const before: LocationPayload = {
        name: location.name,
        floor: location.floor,
        description: location.description,
        latitude: location.latitude,
        longitude: location.longitude,
      }
      changes = Object.fromEntries(
        Object.entries(payload).filter(
          ([key, value]) => before[key as keyof LocationPayload] !== value,
        ),
      )
      if (Object.keys(changes).length === 0) {
        setServerErrors({ form: 'Nothing has changed yet.' })
        return
      }
    }

    setSaving(true)
    setServerErrors({})
    try {
      const saved = location
        ? await updateLocation(location.id, changes)
        : await createLocation(payload)
      onSave(saved)
      onClose()
    } catch (error) {
      showError(error, !location)
    } finally {
      setSaving(false)
    }
  }

  // Unsaved edits in the form aren't sent; only the status changes
  async function toggleActive() {
    if (!location || saving) return
    setSaving(true)
    setServerErrors({})
    try {
      const saved = await updateLocation(location.id, {
        active: !location.active,
      })
      onSave(saved)
      onClose()
    } catch (error) {
      showError(error, false)
    } finally {
      setSaving(false)
    }
  }

  const input = (
    field: keyof Values,
    props: InputHTMLAttributes<HTMLInputElement> = {},
  ) => (
    <input
      {...props}
      value={values[field]}
      onChange={(event) => update(field, event.target.value)}
      onBlur={() => setTouched((current) => new Set(current).add(field))}
      aria-invalid={errorFor(field) ? true : undefined}
      aria-describedby={`location-${field}-error`}
    />
  )

  const fieldError = (field: Field) =>
    errorFor(field) && (
      <span
        className="supplier-dialog-field-error"
        id={`location-${field}-error`}
      >
        {errorFor(field)}
      </span>
    )

  return (
    <Dialog.Root
      open
      onOpenChange={(open) => {
        if (!open && !saving) onClose()
      }}
    >
      <Dialog.Portal>
        <Dialog.Overlay className="supplier-dialog-overlay" />
        <Dialog.Content className="supplier-dialog">
          <div className="supplier-dialog-heading">
            <Dialog.Title>
              {location ? 'Edit delivery location' : 'Add delivery location'}
            </Dialog.Title>
            <Dialog.Close
              className="supplier-dialog-close"
              aria-label="Close"
              disabled={saving}
            >
              <X size={20} />
            </Dialog.Close>
          </div>
          <Dialog.Description className="supplier-dialog-hint">
            {location
              ? 'Changes apply to every errand delivered here.'
              : 'Every student can choose it when they make a request.'}
          </Dialog.Description>

          <form
            noValidate
            onSubmit={(event) => {
              void handleSubmit(event)
            }}
          >
            <fieldset disabled={saving}>
              <div className="supplier-dialog-section">
                <label>
                  Name
                  {input('name', { placeholder: 'COM3 lobby' })}
                  {fieldError('name')}
                </label>
                <label>
                  Floor (optional)
                  {input('floor', { placeholder: '1' })}
                  {fieldError('floor')}
                </label>
                <label>
                  Description (optional)
                  {input('description', {
                    placeholder: 'Benches beside the main entrance',
                  })}
                  {fieldError('description')}
                </label>
              </div>

              <div className="supplier-dialog-section">
                <div className="supplier-dialog-field">
                  <span>Location</span>
                  <InteractiveMap
                    value={position}
                    onChange={updatePosition}
                    ariaLabel="Choose the delivery location on the map"
                  />
                </div>
                <p className="supplier-dialog-hint supplier-dialog-map-hint">
                  <MapPin size={14} aria-hidden="true" />
                  {position
                    ? `${position.latitude.toFixed(5)}, ${position.longitude.toFixed(5)}`
                    : 'Click the map to place the location'}
                </p>
                {positionError && (
                  <div className="supplier-dialog-row-errors">
                    <span id="location-latitude-error">{positionError}</span>
                  </div>
                )}
              </div>
            </fieldset>

            {serverErrors.form && (
              <p className="supplier-dialog-error" role="alert">
                {serverErrors.form}
              </p>
            )}
            <div className="supplier-dialog-footer">
              {location && (
                <button
                  type="button"
                  className={`admin-location-toggle${location.active ? ' is-danger' : ''}`}
                  disabled={saving}
                  onClick={() => void toggleActive()}
                >
                  {location.active ? 'Deactivate' : 'Reactivate'}
                </button>
              )}
              <Dialog.Close disabled={saving}>Cancel</Dialog.Close>
              <button type="submit" disabled={saving}>
                {saving ? 'Saving...' : location ? 'Save' : 'Add'}
              </button>
            </div>
          </form>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  )
}
