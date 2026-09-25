import { validateUsername, validatePassword } from '../utils/validation'
import { useState, type SubmitEvent } from 'react'
import { useNavigate } from 'react-router'
import { Dialog } from 'radix-ui'
import { Eye, EyeOff, LockKeyhole, Plus, UserRound, X } from 'lucide-react'
import { updateUser } from '../api/user'
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

  // Username should be prefilled from BE
  const [username, setUsername] = useState('CampusRunner')
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

  // Should also check that current password is correct, if present
  const errors = {
    username: validateUsername(username),
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

    setLoading(true)
    try {
      // Probably should send the actual current password (if no new password is provided)
      await updateUser({
        username,
        password: newPassword,
      })

      onClose()
      if (newPassword) {
        await navigate('/login', { replace: true })
      }
    } catch {
      setError('Could not save changes. Please try again.')
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
                  disabled={loading}
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
                  disabled={loading}
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
                  disabled={loading}
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

            <button className="edit-info-save" type="submit" disabled={loading}>
              {loading ? 'Saving…' : 'Save'}
            </button>
          </form>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  )
}
