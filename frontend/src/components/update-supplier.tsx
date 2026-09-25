import { useState, type SubmitEvent } from 'react'
import { Dialog, Select } from 'radix-ui'
import { Check, ChevronDown, X } from 'lucide-react'
import { createSupplier, editSupplier } from '../api/supplier'
import type { Supplier, CreateSupplierPayload } from '../types/supplier'
import './update-supplier.css'

type Props = {
  supplier?: Supplier
  onSave: (supplier: Supplier) => void
  onClose: () => void
  onRestoreFocus: () => void
}

export default function CreateSupplierDialog({
  supplier,
  onSave,
  onClose,
  onRestoreFocus,
}: Props) {
  const [values, setValues] = useState<CreateSupplierPayload>(() => ({
    name: supplier?.name ?? '',
    location: supplier?.location ?? '',
    startTime: supplier?.startTime ?? '09:00',
    endTime: supplier?.endTime ?? '18:00',
    type: supplier?.type ?? 'Food',
  }))
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')

  async function handleSubmit(event: SubmitEvent<HTMLFormElement>) {
    event.preventDefault()
    if (saving) return
    const payload = {
      ...values,
      name: values.name.trim(),
      location: values.location.trim(),
    }
    if (!payload.name || !payload.location) {
      setError('Enter a name and location.')
      return
    }
    setSaving(true)
    setError('')
    try {
      await (supplier ? editSupplier(payload) : createSupplier(payload))
      onSave({ ...payload, active: supplier?.active ?? true })
      onClose()
    } catch {
      setError('Could not save supplier. Please try again.')
    } finally {
      setSaving(false)
    }
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
            Enter the supplier details and opening hours.
          </Dialog.Description>
          <form
            onSubmit={(event) => {
              void handleSubmit(event)
            }}
          >
            <fieldset disabled={saving}>
              {(['name', 'location'] as const).map((field) => (
                <label key={field}>
                  {field === 'name' ? 'Name' : 'Location'}
                  <input
                    required
                    value={values[field]}
                    onChange={(event) =>
                      setValues({ ...values, [field]: event.target.value })
                    }
                  />
                </label>
              ))}
              <div className="supplier-dialog-times">
                {(['startTime', 'endTime'] as const).map((field) => (
                  <label key={field}>
                    {field === 'startTime' ? 'Opening time' : 'Closing time'}
                    <input
                      type="time"
                      required
                      value={values[field]}
                      onChange={(event) =>
                        setValues({ ...values, [field]: event.target.value })
                      }
                    />
                  </label>
                ))}
              </div>
              <label htmlFor="supplier-category">Type</label>
              <Select.Root
                value={values.type}
                disabled={saving}
                onValueChange={(type) => {
                  if (
                    type === 'Food' ||
                    type === 'Drinks' ||
                    type === 'Shopping' ||
                    type === 'Printing'
                  )
                    setValues({ ...values, type })
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
                      {['Food', 'Drinks', 'Shopping', 'Printing'].map(
                        (type) => (
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
                        ),
                      )}
                    </Select.Viewport>
                  </Select.Content>
                </Select.Portal>
              </Select.Root>
            </fieldset>
            {error && (
              <p className="supplier-dialog-error" role="alert">
                {error}
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
