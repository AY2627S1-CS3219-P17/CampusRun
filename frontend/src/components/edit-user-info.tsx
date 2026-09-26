// AI Assistance Disclosure:
// Tool: Claude Code (model: Claude Opus 5.5), date: 2026-09-27
// Scope: AI-wired the dialog to the User Service: loads the current username, sends only changed fields,
//        and keeps Save disabled until something has changed.
// Author review: <to be completed by author>

import { validateUsername, validatePassword } from '../utils/validation'
import { useEffect, useState, type SubmitEvent } from 'react'
import { useNavigate } from 'react-router'
import { Dialog } from 'radix-ui'
import { Eye, EyeOff, LockKeyhole, Plus, UserRound, X } from 'lucide-react'
import { ApiError } from '../api/client'
import { getCurrentUser, updateUser } from '../api/user'
import type { UpdateUserPayload } from '../types/user'
import { clearSession } from '../utils/session'
import './edit-user-info.css'

type EditInfoDialogProps = {
  onClose: () => void
  onRestoreFocus: () => void
}

export default function EditInfoDialog({
  onClose,
  onRestoreFocus,
}: EditInfoDialogProps) {
  const navigate = useNavigate()

  // The saved username, from GET /users/me; null until it has loaded
  const [savedUsername, setSavedUsername] = useState<string | null>(null)
  const [username, setUsername] = useState('')
  const [currentPassword, setCurrentPassword] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [showCurrentPassword, setShowCurrentPassword] = useState(false)
  const [showNewPassword, setShowNewPassword] = useState(false)
  const [loading, setLoading] = useState(false)
  // Note this is BE error
  const [error, setError] = useState('')

  const [submitted, setSubmitted] = useState(false)
  const [touched, setTouched] = useState({
    username: false,
    currentPassword: false,
    newPassword: false,
  })

  useEffect(() => {
    const controller = new AbortController()
    getCurrentUser(controller.signal)
      .then((user) => {
        setSavedUsername(user.username)
        setUsername(user.username)
      })
      .catch((error: unknown) => {
        if (error instanceof DOMException && error.name === 'AbortError') return
        setError(
          error instanceof ApiError
            ? error.message
            : 'Could not load your details. Please try again.',
        )
      })
    return () => controller.abort()
  }, [])

  // The service trims the username too, so surrounding spaces aren't a change
  const usernameChanged =
    savedUsername !== null && username.trim() !== savedUsername
  // Save stays disabled until something would actually change
  const hasChanges = usernameChanged || Boolean(newPassword)
  const loaded = savedUsername !== null

  // The service checks the current password, since only it knows the stored one
  const errors = {
    // Only a changed username is checked, so an older username that predates these rules can't block a password change
    username: usernameChanged ? validateUsername(username.trim()) : '',
    currentPassword:
      newPassword && !currentPassword ? 'Enter your current password.' : '',
    newPassword: !newPassword
      ? ''
      : currentPassword === newPassword
        ? 'Choose a different new password.'
        : validatePassword(newPassword),
  }

  const fieldErrors = {
    username: submitted || touched.username ? errors.username : '',
    currentPassword:
      submitted || touched.currentPassword ? errors.currentPassword : '',
    newPassword: submitted || touched.newPassword ? errors.newPassword : '',
  }

  async function handleSubmit(event: SubmitEvent<HTMLFormElement>) {
    event.preventDefault()
    if (loading) return
    setError('')

    setSubmitted(true)
    if (Object.values(errors).some(Boolean)) return

    if (!hasChanges) return

    // Only the changed fields, so a success response always means something changed
    const payload: UpdateUserPayload = {}
    if (usernameChanged) payload.username = username.trim()
    if (newPassword) {
      payload.current_password = currentPassword
      payload.new_password = newPassword
    }

    setLoading(true)
    try {
      await updateUser(payload)

      onClose()
      if (newPassword) {
        // Sign in again with the new password. The old token would keep working
        // until it expires, since the service can't revoke it.
        clearSession()
        await navigate('/login', { replace: true })
      }
    } catch (error) {
      // e.g. "Current password is incorrect" or "Username is already in use"
      setError(
        error instanceof ApiError
          ? error.message
          : 'Could not save changes. Please try again.',
      )
    } finally {
      setLoading(false)
    }
  }

  return (
    <Dialog.Root
      open
      onOpenChange={(open) => {
        if (!open && !loading) onClose()
      }}
    >
      <Dialog.Portal>
        <Dialog.Overlay className="edit-info-overlay" />
        <Dialog.Content
          className="edit-info-dialog"
          onCloseAutoFocus={(event: Event) => {
            event.preventDefault()
            onRestoreFocus()
          }}
        >
          <div className="edit-info-header">
            <Dialog.Title className="edit-info-title">Edit Info</Dialog.Title>
            <Dialog.Close
              className="edit-info-close"
              aria-label="Close"
              disabled={loading}
            >
              {/* Mocked for now */}
              <X size={20} aria-hidden="true" />
            </Dialog.Close>
          </div>

          <form
            className="edit-info-form"
            noValidate
            onSubmit={(event) => {
              void handleSubmit(event)
            }}
          >
            <div className="edit-info-avatar">
              <UserRound size={46} strokeWidth={1.5} aria-hidden="true" />
              <button
                className="edit-info-photo"
                type="button"
                aria-label="Change profile photo"
              >
                <Plus size={18} aria-hidden="true" />
              </button>
            </div>

            <div className="edit-info-field">
              <label htmlFor="edit-username">Username</label>
              <div className="edit-info-input">
                <UserRound size={20} aria-hidden="true" />
                <input
                  id="edit-username"
                  name="username"
                  aria-invalid={Boolean(fieldErrors.username)}
                  aria-describedby={
                    fieldErrors.username ? 'edit-username-error' : undefined
                  }
                  onBlur={() =>
                    setTouched((current) => ({ ...current, username: true }))
                  }
                  autoComplete="username"
                  placeholder="Zhong Xi Na"
                  value={username}
                  onChange={(event) => setUsername(event.target.value)}
                  required
                  disabled={loading || !loaded}
                />
              </div>
              {fieldErrors.username && (
                <p
                  className="edit-info-field-error"
                  id="edit-username-error"
                  aria-live="polite"
                >
                  {fieldErrors.username}
                </p>
              )}
            </div>

            <div className="edit-info-field">
              <label htmlFor="edit-currentPassword">Current Password</label>
              <div className="edit-info-input">
                <LockKeyhole size={20} aria-hidden="true" />
                <input
                  id="edit-currentPassword"
                  name="currentPassword"
                  aria-invalid={Boolean(fieldErrors.currentPassword)}
                  aria-describedby={
                    fieldErrors.currentPassword
                      ? 'edit-currentPassword-error'
                      : undefined
                  }
                  onBlur={() =>
                    setTouched((current) => ({
                      ...current,
                      currentPassword: true,
                    }))
                  }
                  type={showCurrentPassword ? 'text' : 'password'}
                  autoComplete="current-password"
                  value={currentPassword}
                  onChange={(event) => setCurrentPassword(event.target.value)}
                  required={Boolean(newPassword)}
                  disabled={loading || !loaded}
                />
                <button
                  className="edit-info-password-toggle"
                  type="button"
                  aria-label={
                    showCurrentPassword
                      ? 'Hide current password'
                      : 'Show current password'
                  }
                  aria-pressed={showCurrentPassword}
                  aria-controls="edit-currentPassword"
                  onClick={() => setShowCurrentPassword((current) => !current)}
                  disabled={loading}
                >
                  {showCurrentPassword ? (
                    <EyeOff size={20} aria-hidden="true" />
                  ) : (
                    <Eye size={20} aria-hidden="true" />
                  )}
                </button>
              </div>
              {fieldErrors.currentPassword && (
                <p
                  className="edit-info-field-error"
                  id="edit-currentPassword-error"
                  aria-live="polite"
                >
                  {fieldErrors.currentPassword}
                </p>
              )}
            </div>

            <div className="edit-info-field">
              <label htmlFor="edit-newPassword">New Password</label>
              <div className="edit-info-input">
                <LockKeyhole size={20} aria-hidden="true" />
                <input
                  id="edit-newPassword"
                  name="newPassword"
                  aria-invalid={Boolean(fieldErrors.newPassword)}
                  aria-describedby={
                    fieldErrors.newPassword
                      ? 'edit-newPassword-error'
                      : undefined
                  }
                  onBlur={() =>
                    setTouched((current) => ({ ...current, newPassword: true }))
                  }
                  type={showNewPassword ? 'text' : 'password'}
                  autoComplete="new-password"
                  value={newPassword}
                  onChange={(event) => setNewPassword(event.target.value)}
                  disabled={loading || !loaded}
                />
                <button
                  className="edit-info-password-toggle"
                  type="button"
                  aria-label={
                    showNewPassword ? 'Hide new password' : 'Show new password'
                  }
                  aria-pressed={showNewPassword}
                  aria-controls="edit-newPassword"
                  onClick={() => setShowNewPassword((current) => !current)}
                  disabled={loading}
                >
                  {showNewPassword ? (
                    <EyeOff size={20} aria-hidden="true" />
                  ) : (
                    <Eye size={20} aria-hidden="true" />
                  )}
                </button>
              </div>
              {fieldErrors.newPassword && (
                <p
                  className="edit-info-field-error"
                  id="edit-newPassword-error"
                  aria-live="polite"
                >
                  {fieldErrors.newPassword}
                </p>
              )}
            </div>

            {error && (
              <p className="edit-info-error" role="alert">
                {error}
              </p>
            )}

            <button
              className="edit-info-save"
              type="submit"
              disabled={loading || !hasChanges}
            >
              {loading ? 'Saving…' : 'Save'}
            </button>
          </form>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  )
}
