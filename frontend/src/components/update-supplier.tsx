// AI Assistance Disclosure:
// Tool: Claude (claude.ai chat, model: Claude Opus 5.5), date: 2026-09-26
// Scope: AI-modified: saves through the Supplier Service; adds building, floor, directions,
//        coordinates and photo fields, and per-field validation including errors from the service.
// Author review: <to be completed by author>

import { useRef, useState, type ReactNode, type SubmitEvent } from 'react'
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

type Values = {
  name: string
  type: SupplierCategory
  building: string
  floor: string
  locationDescription: string
  latitude: string
  longitude: string
  startTime: string
  endTime: string
  imageUrl: string
}
type Field = keyof Values
type Errors = Partial<Record<Field | 'form', string>>

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
  text('name', 100, 'Enter a name.')
  text('building', 100, 'Enter the building.')
  text('floor', 10, null)
  text('locationDescription', 300, 'Say where to find it, e.g. "Next to LT19".')
  for (const field of ['latitude', 'longitude'] as const) {
    const value = values[field].trim()
    if (!value) errors[field] = `Enter the ${field}.`
    else if (!Number.isFinite(Number(value)))
      errors[field] = 'Enter a number, e.g. 1.2966.'
  }
  if (!values.startTime) errors.startTime = 'Enter an opening time.'
  if (!values.endTime) errors.endTime = 'Enter a closing time.'
  const url = values.imageUrl.trim()
  if (url && !/^https?:\/\/\S+$/i.test(url))
    errors.imageUrl = 'Enter a full link starting with https://.'
  return errors
}

export default function CreateSupplierDialog({
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
  const formRef = useRef<HTMLFormElement>(null)

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
    if (Object.keys(clientErrors).length > 0) {
      formRef.current
        ?.querySelector<HTMLElement>('[aria-invalid="true"]')
        ?.focus()
      return
    }
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

  const input = (field: Field, props: Record<string, string> = {}) => (
    <input
      {...props}
      value={values[field]}
      onChange={(event) => update(field, event.target.value)}
      onBlur={() => setTouched((current) => new Set(current).add(field))}
      aria-invalid={errorFor(field) ? true : undefined}
      aria-describedby={`supplier-${field}-error`}
    />
  )

  const field = (name: Field, label: string, control: ReactNode) => (
    <label className={errorFor(name) ? 'has-error' : undefined}>
      {label}
      {control}
      {errorFor(name) && (
        <span
          className="supplier-dialog-field-error"
          id={`supplier-${name}-error`}
        >
          {errorFor(name)}
        </span>
      )}
    </label>
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
        <Dialog.Content
          className="supplier-dialog"
          onCloseAutoFocus={(event) => {
            event.preventDefault()
            onRestoreFocus()
          }}
        >
          <div className="supplier-dialog-heading">
            <Dialog.Title>
              {supplier ? 'Edit supplier' : 'Create supplier'}
            </Dialog.Title>
            <Dialog.Close
              className="supplier-dialog-close"
              aria-label="Close"
              disabled={saving}
            >
              <X size={20} />
            </Dialog.Close>
          </div>
          <Dialog.Description>
            Enter the supplier details, where to find it and its opening hours.
          </Dialog.Description>
          <form
            ref={formRef}
            noValidate
            onSubmit={(event) => {
              void handleSubmit(event)
            }}
          >
            <fieldset disabled={saving}>
              {field('name', 'Name', input('name'))}

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

              <div className="supplier-dialog-times">
                {field(
                  'building',
                  'Building',
                  input('building', { placeholder: 'COM3' }),
                )}
                {field(
                  'floor',
                  'Floor (optional)',
                  input('floor', { placeholder: '1' }),
                )}
              </div>
              {field(
                'locationDescription',
                'Where to find it',
                input('locationDescription', {
                  placeholder: 'Next to LT19',
                }),
              )}
              <div className="supplier-dialog-times">
                {field(
                  'latitude',
                  'Latitude',
                  input('latitude', {
                    inputMode: 'decimal',
                    placeholder: '1.2949',
                  }),
                )}
                {field(
                  'longitude',
                  'Longitude',
                  input('longitude', {
                    inputMode: 'decimal',
                    placeholder: '103.7744',
                  }),
                )}
              </div>
              <p className="supplier-dialog-hint">
                In Google Maps, right-click the spot to copy its coordinates.
              </p>
              <div className="supplier-dialog-times">
                {field(
                  'startTime',
                  'Opening time',
                  input('startTime', { type: 'time' }),
                )}
                {field(
                  'endTime',
                  'Closing time',
                  input('endTime', { type: 'time' }),
                )}
              </div>
              <p className="supplier-dialog-hint">
                A closing time earlier than the opening time means it closes
                after midnight.
              </p>
              {field(
                'imageUrl',
                'Photo link (optional)',
                input('imageUrl', { type: 'url', placeholder: 'https://' }),
              )}
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
