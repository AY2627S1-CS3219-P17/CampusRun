// AI Assistance Disclosure:
// Tool: Claude (claude.ai chat, model: Claude Opus 5.5), date: 2026-09-26
// Scope: AI-modified: saves through the Supplier Service; adds building, floor, directions,
//        coordinates and photo fields, and per-field validation including errors from the service.
//        AI-refactored the form sections, paired-field errors and time-picker interaction
// Author review: Validated form validation, API errors, and input boundaries.

import {
  useState,
  type InputHTMLAttributes,
  type ReactNode,
  type SubmitEvent,
} from 'react'
import { Dialog, Select } from 'radix-ui'
import { Check, ChevronDown, X } from 'lucide-react'
import { ApiError } from '../api/client'
import { createSupplier, editSupplier } from '../api/supplier'
import {
  SUPPLIER_CATEGORIES,
  type CreateSupplierPayload,
  type Supplier,
  type SupplierCategory,
} from '../types/supplier'
import './update-supplier.css'

type Props = {
  supplier?: Supplier
  onSave: (supplier: Supplier) => void
  onClose: () => void
  onRestoreFocus: () => void
}

type InputValue<T> = T extends number | null ? string : T
type Values = {
  [Key in keyof CreateSupplierPayload]: InputValue<CreateSupplierPayload[Key]>
}
type Field = keyof Values
type Errors = Partial<Record<Field | 'form', string>>

// Matches BE, for NUS campus geo boundary
const COORDINATE_BOUNDS = {
  latitude: { min: 1.287, max: 1.31 },
  longitude: { min: 103.764, max: 103.788 },
} as const

function toValues(supplier?: Supplier): Values {
  return {
    name: supplier?.name ?? '',
    type: supplier?.type ?? 'Food',
    building: supplier?.building ?? '',
    floor: supplier?.floor ?? '',
    locationDescription: supplier?.locationDescription ?? '',
    latitude: supplier ? String(supplier.latitude) : '',
    longitude: supplier ? String(supplier.longitude) : '',
    startTime: supplier?.startTime ?? '09:00',
    endTime: supplier?.endTime ?? '18:00',
    imageUrl: supplier?.imageUrl ?? '',
  }
}

function toPayload(values: Values): CreateSupplierPayload {
  const optional = (value: string) => value.trim() || null
  return {
    name: values.name.trim(),
    type: values.type,
    building: values.building.trim(),
    floor: optional(values.floor),
    locationDescription: values.locationDescription.trim(),
    latitude: Number(values.latitude),
    longitude: Number(values.longitude),
    startTime: values.startTime,
    endTime: values.endTime,
    imageUrl: optional(values.imageUrl),
  }
}

// The same rules the Supplier Service applies. Whether a point is on campus is
// checked by the service, and its message appears under the field.
function validate(values: Values): Errors {
  const errors: Errors = {}
  const text = (field: Field, max: number, required: string | null) => {
    const value = values[field].trim()
    if (!value && required) errors[field] = required
    else if (value.length > max)
      errors[field] = `Use at most ${max} characters.`
  }

  text('name', 100, 'Required')
  text('building', 100, 'Building is required')
  text('floor', 10, null)
  text('locationDescription', 300, 'Required')

  for (const field of ['latitude', 'longitude'] as const) {
    const value = values[field].trim()
    if (!value)
      errors[field] =
        `${field.charAt(0).toUpperCase() + field.slice(1)} is required`
    else {
      const { min, max } = COORDINATE_BOUNDS[field]
      if (Number(value) < min || Number(value) > max)
        errors[field] = `Use a value from ${min} to ${max}.`
    }
  }

  const url = values.imageUrl.trim()
  if (url && !/^https?:\/\/\S+$/i.test(url))
    errors.imageUrl = 'Enter a full link starting with https://.'

  return errors
}

export default function UpdateSupplierDialog({
  supplier,
  onSave,
  onClose,
  onRestoreFocus,
}: Props) {
  const [initial] = useState(() => toValues(supplier))
  const [values, setValues] = useState<Values>(initial)
  const [touched, setTouched] = useState<Set<Field>>(new Set())
  const [submitted, setSubmitted] = useState(false)
  const [serverErrors, setServerErrors] = useState<Errors>({})
  const [saving, setSaving] = useState(false)

  const clientErrors = validate(values)
  const errorFor = (field: Field) =>
    serverErrors[field] ??
    (submitted || touched.has(field) ? clientErrors[field] : undefined)

  function update(field: Field, value: string) {
    setValues((current) => ({ ...current, [field]: value }))
    setServerErrors((current) => ({ ...current, [field]: undefined }))
  }

  async function handleSubmit(event: SubmitEvent<HTMLFormElement>) {
    event.preventDefault()
    if (saving) return
    setSubmitted(true)

    const payload = toPayload(values)
    let changes: Partial<CreateSupplierPayload> = payload
    if (supplier) {
      // Only send what changed
      const before = toPayload(initial)
      changes = Object.fromEntries(
        Object.entries(payload).filter(
          ([key, value]) =>
            before[key as keyof CreateSupplierPayload] !== value,
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
      const saved = supplier
        ? await editSupplier(supplier.id, changes)
        : await createSupplier(payload)
      onSave(saved)
      onClose()
    } catch (error) {
      if (error instanceof ApiError && error.status === 409)
        setServerErrors({ name: error.message })
      else if (error instanceof ApiError)
        setServerErrors({ form: error.message, ...error.fieldErrors })
      else
        setServerErrors({ form: 'Could not save supplier. Please try again.' })
    } finally {
      setSaving(false)
    }
  }

  const input = (
    field: Field,
    props: InputHTMLAttributes<HTMLInputElement> = {},
  ) => (
    <input
      {...props}
      value={values[field]}
      onChange={(event) => update(field, event.target.value)}
      onBlur={() => setTouched((current) => new Set(current).add(field))}
      onClick={(event) => {
        props.onClick?.(event)
        if (props.type === 'time') event.currentTarget.showPicker?.()
      }}
      aria-invalid={errorFor(field) ? true : undefined}
      aria-describedby={`supplier-${field}-error`}
    />
  )

  const field = (
    name: Field,
    label: string,
    control: ReactNode,
    showError = true,
  ) => (
    <label>
      {label}
      {control}
      {showError && errorFor(name) && (
        <span
          className="supplier-dialog-field-error"
          id={`supplier-${name}-error`}
        >
          {errorFor(name)}
        </span>
      )}
    </label>
  )

  const rowErrors = (...fields: Field[]) => {
    const invalid = fields.filter((name) => errorFor(name))
    if (invalid.length === 0) return null
    return (
      <div className="supplier-dialog-row-errors">
        {invalid.map((name) => (
          <span key={name} id={`supplier-${name}-error`}>
            {errorFor(name)}
          </span>
        ))}
      </div>
    )
  }

  return (
    <Dialog.Root
      open
      onOpenChange={(open) => {
        if (!open && !saving) onClose()
      }}
    >
      <Dialog.Portal>
        <Dialog.Overlay className="supplier-dialog-overlay" />
        <Dialog.Content
          className="supplier-dialog"
          onCloseAutoFocus={(event) => {
            event.preventDefault()
            onRestoreFocus()
          }}
        >
          <div className="supplier-dialog-heading">
            <Dialog.Title>
              {supplier ? 'Edit Supplier' : 'Create Supplier'}
            </Dialog.Title>
            <Dialog.Close
              className="supplier-dialog-close"
              aria-label="Close"
              disabled={saving}
            >
              <X size={20} />
            </Dialog.Close>
          </div>

          <form
            noValidate
            onSubmit={(event) => {
              void handleSubmit(event)
            }}
          >
            <fieldset disabled={saving}>
              <div className="supplier-dialog-section">
                {field(
                  'name',
                  'Name',
                  input('name', { placeholder: 'Starbucks' }),
                )}

                <label htmlFor="supplier-category">Type</label>
                <Select.Root
                  value={values.type}
                  disabled={saving}
                  onValueChange={(type) => {
                    if (SUPPLIER_CATEGORIES.includes(type as SupplierCategory))
                      update('type', type)
                  }}
                >
                  <Select.Trigger
                    id="supplier-category"
                    className="supplier-dialog-select"
                  >
                    <Select.Value />
                    <Select.Icon>
                      <ChevronDown size={16} />
                    </Select.Icon>
                  </Select.Trigger>
                  <Select.Portal>
                    <Select.Content
                      className="supplier-dialog-options"
                      position="popper"
                      sideOffset={4}
                      collisionPadding={12}
                    >
                      <Select.Viewport>
                        {SUPPLIER_CATEGORIES.map((type) => (
                          <Select.Item
                            className="supplier-dialog-option"
                            key={type}
                            value={type}
                          >
                            <Select.ItemText>{type}</Select.ItemText>
                            <Select.ItemIndicator>
                              <Check size={16} />
                            </Select.ItemIndicator>
                          </Select.Item>
                        ))}
                      </Select.Viewport>
                    </Select.Content>
                  </Select.Portal>
                </Select.Root>
              </div>

              <div className="supplier-dialog-section">
                <div className="supplier-dialog-fields">
                  {field(
                    'building',
                    'Building',
                    input('building', { placeholder: 'COM3' }),
                    false,
                  )}
                  {field(
                    'floor',
                    'Floor (optional)',
                    input('floor', { placeholder: '1' }),
                    false,
                  )}
                  {rowErrors('building', 'floor')}
                </div>

                {field(
                  'locationDescription',
                  'Description',
                  input('locationDescription', {
                    placeholder: 'Next to LT19',
                  }),
                )}

                <div className="supplier-dialog-fields">
                  {field(
                    'latitude',
                    'Latitude',
                    input('latitude', {
                      type: 'number',
                      min: COORDINATE_BOUNDS.latitude.min,
                      max: COORDINATE_BOUNDS.latitude.max,
                      step: 'any',
                      inputMode: 'decimal',
                      placeholder: '1.2949',
                    }),
                    false,
                  )}
                  {field(
                    'longitude',
                    'Longitude',
                    input('longitude', {
                      type: 'number',
                      min: COORDINATE_BOUNDS.longitude.min,
                      max: COORDINATE_BOUNDS.longitude.max,
                      step: 'any',
                      inputMode: 'decimal',
                      placeholder: '103.7744',
                    }),
                    false,
                  )}
                  {rowErrors('latitude', 'longitude')}
                </div>
                <p className="supplier-dialog-hint">
                  In Google Maps, right-click the spot to copy its coordinates.
                </p>
              </div>

              <div className="supplier-dialog-section">
                <div className="supplier-dialog-fields">
                  {field(
                    'startTime',
                    'Opening',
                    input('startTime', { type: 'time' }),
                    false,
                  )}
                  {field(
                    'endTime',
                    'Closing',
                    input('endTime', { type: 'time' }),
                    false,
                  )}
                </div>
                <p className="supplier-dialog-hint">
                  A closing time earlier than the opening time means it closes
                  after midnight.
                </p>

                {field(
                  'imageUrl',
                  'Photo Link (optional)',
                  input('imageUrl', { type: 'url', placeholder: 'https://' }),
                )}
              </div>
            </fieldset>

            {serverErrors.form && (
              <p className="supplier-dialog-error" role="alert">
                {serverErrors.form}
              </p>
            )}
            <div className="supplier-dialog-footer">
              <Dialog.Close disabled={saving}>Cancel</Dialog.Close>
              <button type="submit" disabled={saving}>
                {saving ? 'Saving...' : supplier ? 'Edit' : 'Create'}
              </button>
            </div>
          </form>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  )
}
