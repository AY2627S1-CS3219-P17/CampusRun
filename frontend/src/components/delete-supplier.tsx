// AI Assistance Disclosure:
// Tool: Claude (claude.ai chat, model: Claude Opus 5.5), date: 2026-09-26
// Scope: AI-assisted review and debugging for confirmation dialog for deleting a supplier through the Supplier Service.
// Author review: <to be completed by author>

import { useState } from 'react'
import { AlertDialog } from 'radix-ui'
import { ApiError } from '../api/client'
import { deleteSupplier } from '../api/supplier'
import type { Supplier } from '../types/supplier'
import './update-supplier.css'

type Props = {
  supplier: Supplier
  onDeleted: (supplier: Supplier) => void
  onClose: () => void
}

export default function DeleteSupplierDialog({
  supplier,
  onDeleted,
  onClose,
}: Props) {
  const [deleting, setDeleting] = useState(false)
  const [error, setError] = useState('')

  async function handleDelete() {
    setDeleting(true)
    setError('')
    try {
      await deleteSupplier(supplier.id)
      onDeleted(supplier)
      onClose()
    } catch (err) {
      setError(
        err instanceof ApiError
          ? err.message
          : 'Could not delete supplier. Please try again.',
      )
    } finally {
      setDeleting(false)
    }
  }

  return (
    <AlertDialog.Root
      open
      onOpenChange={(open) => {
        if (!open && !deleting) onClose()
      }}
    >
      <AlertDialog.Portal>
        <AlertDialog.Overlay className="supplier-dialog-overlay" />
        <AlertDialog.Content className="supplier-dialog">
          <AlertDialog.Title>Delete {supplier.name}?</AlertDialog.Title>
          <AlertDialog.Description>
            Students will no longer see it or be able to choose it for new
            errands. To hide it for a while instead, deactivate it.
          </AlertDialog.Description>
          {error && (
            <p className="supplier-dialog-error" role="alert">
              {error}
            </p>
          )}
          <div className="supplier-dialog-footer">
            <AlertDialog.Cancel disabled={deleting}>Cancel</AlertDialog.Cancel>
            <button
              type="button"
              className="supplier-dialog-danger"
              disabled={deleting}
              onClick={() => {
                void handleDelete()
              }}
            >
              {deleting ? 'Deleting...' : 'Delete'}
            </button>
          </div>
        </AlertDialog.Content>
      </AlertDialog.Portal>
    </AlertDialog.Root>
  )
}
