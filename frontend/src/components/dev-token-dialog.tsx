// AI Assistance Disclosure:
// Tool: Claude (claude.ai chat, model: Claude Opus 5.5), date: 2026-09-26
// Scope: AI-generated development-only dialog for using a token from make_token.py until the User Service login exists;
//        AI-updated the make_token.py flag (Claude Code, 2026-09-27).
// Author review: <to be completed by author>

import { useState } from 'react'
import { Dialog } from 'radix-ui'
import { X } from 'lucide-react'
import { saveToken } from '../utils/session'
import './update-supplier.css'

type Props = {
  onClose: () => void
}

// Remove once the login page saves the User Service's token (utils/session.ts)
export default function DevTokenDialog({ onClose }: Props) {
  const [token, setToken] = useState('')
  const [error, setError] = useState('')

  return (
    <Dialog.Root open onOpenChange={(open) => !open && onClose()}>
      <Dialog.Portal>
        <Dialog.Overlay className="supplier-dialog-overlay" />
        <Dialog.Content className="supplier-dialog">
          <div className="supplier-dialog-heading">
            <Dialog.Title>Use a development token</Dialog.Title>
            <Dialog.Close className="supplier-dialog-close" aria-label="Close">
              <X size={20} />
            </Dialog.Close>
          </div>
          <Dialog.Description>
            Login isn&apos;t connected to the User Service yet. In the
            supplier-service folder, run{' '}
            <code>uv run python scripts/make_token.py --type admin</code> (or{' '}
            <code>--type student</code>) and paste the token here.
          </Dialog.Description>
          <form
            onSubmit={(event) => {
              event.preventDefault()
              if (saveToken(token)) onClose()
              else
                setError(
                  "This token isn't valid or has expired. Make a new one and paste it again.",
                )
            }}
          >
            <fieldset>
              <label>
                Access token
                <textarea
                  className="supplier-dialog-token"
                  rows={4}
                  value={token}
                  spellCheck={false}
                  onChange={(event) => {
                    setToken(event.target.value)
                    setError('')
                  }}
                />
              </label>
            </fieldset>
            {error && (
              <p className="supplier-dialog-error" role="alert">
                {error}
              </p>
            )}
            <div className="supplier-dialog-footer">
              <Dialog.Close type="button">Cancel</Dialog.Close>
              <button type="submit" disabled={!token.trim()}>
                Use token
              </button>
            </div>
          </form>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  )
}
