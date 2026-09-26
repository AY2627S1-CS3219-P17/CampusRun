// AI Assistance Disclosure:
// Tool: Claude Code (model: Claude Opus 5.5), date: 2026-09-27
// Scope: AI-wired the form to the User Service's registration and showed its error messages.
// Author review: <to be completed by author>

import {
  validateUsername,
  validatePassword,
  validateEmail,
  validateConfirmPassword,
} from '../utils/validation'
import { useState, type SubmitEvent } from 'react'
import { Link, useNavigate } from 'react-router'
import { ApiError } from '../api/client'
import { registerUser } from '../api/user'
import type { RegisterUserValues } from '../types/user'
import {
  Eye,
  EyeOff,
  Footprints,
  LockKeyhole,
  Mail,
  UserRound,
} from 'lucide-react'

import './login.css'
import './register.css'

const emptyValues: RegisterUserValues = {
  username: '',
  email: '',
  password: '',
  confirmPassword: '',
}

const fields = [
  {
    name: 'username',
    label: 'Username',
    icon: <UserRound size={20} aria-hidden="true" />,
    autoComplete: 'username',
  },
  {
    name: 'email',
    label: 'Email',
    icon: <Mail size={20} aria-hidden="true" />,
    autoComplete: 'email',
  },
  {
    name: 'password',
    label: 'Password',
    icon: <LockKeyhole size={20} aria-hidden="true" />,
    autoComplete: 'new-password',
  },
  {
    name: 'confirmPassword',
    label: 'Confirm Password',
    icon: <LockKeyhole size={20} aria-hidden="true" />,
    autoComplete: 'new-password',
  },
] as const

function validateRegistration(
  values: RegisterUserValues,
): Record<keyof RegisterUserValues, string> {
  return {
    username: validateUsername(values.username),
    email: validateEmail(values.email),
    password: validatePassword(values.password),
    confirmPassword: validateConfirmPassword(
      values.password,
      values.confirmPassword,
    ),
  }
}

export default function RegisterPage() {
  const navigate = useNavigate()

  const [values, setValues] = useState(emptyValues)
  const [touched, setTouched] = useState<
    Partial<Record<keyof RegisterUserValues, boolean>>
  >({})

  const [submitted, setSubmitted] = useState(false)
  const [visiblePasswords, setVisiblePasswords] = useState({
    password: false,
    confirmPassword: false,
  })

  const [loading, setLoading] = useState(false)
  // Note this is BE error
  const [error, setError] = useState('')

  const errors = validateRegistration(values)

  async function handleSubmit(event: SubmitEvent<HTMLFormElement>) {
    event.preventDefault()
    if (loading) return

    // Set submited = true, then reveal the field-side errors
    setError('')
    setSubmitted(true)
    if (Object.values(errors).some(Boolean)) return

    setLoading(true)

    try {
      await registerUser({
        username: values.username,
        email: values.email.trim(),
        password: values.password,
      })

      setValues(emptyValues)
      setTouched({})
      setSubmitted(false)
      setVisiblePasswords({ password: false, confirmPassword: false })

      await navigate('/login', { replace: true })
    } catch (error) {
      // e.g. "Username or email is already in use"
      setError(
        error instanceof ApiError
          ? error.message
          : 'Could not create your account. Please try again.',
      )
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="login-page">
      <main className="login-content">
        <section className="login-card" aria-labelledby="register-title">
          <div className="login-brand">
            <Footprints size={38} strokeWidth={2.4} aria-hidden="true" />
            <h1 id="register-title">CampusRun</h1>
            <p>Create your account</p>
          </div>

          <form
            className="login-form"
            noValidate
            onSubmit={(event) => {
              void handleSubmit(event)
            }}
          >
            {fields.map(({ name, label, icon, autoComplete }) => {
              const isPassword =
                name === 'password' || name === 'confirmPassword'
              const visible = isPassword && visiblePasswords[name]

              // Visible error on submit/blur
              const fieldError = submitted || touched[name] ? errors[name] : ''

              return (
                <div className="register-field" key={name}>
                  <div className="login-input">
                    {icon}

                    <input
                      id={`register-${name}`}
                      name={name}
                      aria-label={label}
                      type={
                        isPassword
                          ? visible
                            ? 'text'
                            : 'password'
                          : name === 'email'
                            ? 'email'
                            : 'text'
                      }
                      autoComplete={autoComplete}
                      placeholder={label}
                      value={values[name]}
                      disabled={loading}
                      aria-invalid={Boolean(fieldError)}
                      aria-describedby={
                        fieldError ? `register-${name}-error` : undefined
                      }
                      onBlur={() =>
                        setTouched((current) => ({ ...current, [name]: true }))
                      }
                      onChange={(event) => {
                        setValues((current) => ({
                          ...current,
                          [name]: event.target.value,
                        }))
                        setError('')
                      }}
                      required
                    />

                    {isPassword && (
                      <button
                        className="login-password-toggle"
                        type="button"
                        aria-label={`${visible ? 'Hide' : 'Show'} ${label.toLowerCase()}`}
                        aria-pressed={visible}
                        onClick={() =>
                          setVisiblePasswords((current) => ({
                            ...current,
                            [name]: !current[name],
                          }))
                        }
                      >
                        {visible ? (
                          <EyeOff size={20} aria-hidden="true" />
                        ) : (
                          <Eye size={20} aria-hidden="true" />
                        )}
                      </button>
                    )}
                  </div>

                  {fieldError && (
                    <p
                      className="register-field-error"
                      id={`register-${name}-error`}
                      aria-live="polite"
                    >
                      {fieldError}
                    </p>
                  )}
                </div>
              )
            })}

            {error && (
              <p className="login-error" role="alert">
                {error}
              </p>
            )}

            <button className="login-submit" type="submit" disabled={loading}>
              <span>{loading ? 'Registering…' : 'Register'}</span>
            </button>
          </form>

          <p className="login-register">
            Already have an account? <Link to="/login">Log in</Link>
          </p>
        </section>
      </main>

      <div className="login-art" aria-hidden="true" />
    </div>
  )
}
