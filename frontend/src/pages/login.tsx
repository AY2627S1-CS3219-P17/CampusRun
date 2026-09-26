// AI Assistance Disclosure:
// Tool: Claude Code (model: Claude Opus 5.5), date: 2026-09-27
// Scope: AI-wired the form to the User Service's login and saved the returned access token.
// Author review: <to be completed by author>

import { useState, type SubmitEvent } from 'react'
import { Link, useNavigate } from 'react-router'
import { Label } from 'radix-ui'
import { ApiError } from '../api/client'
import { loginUser } from '../api/user'
import { saveToken } from '../utils/session'

import { Eye, EyeOff, Footprints, LockKeyhole, Mail } from 'lucide-react'
import './login.css'

export default function LoginPage() {
  const navigate = useNavigate()

  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [loading, setLoading] = useState(false)
  // Note this is BE error
  const [error, setError] = useState('')

  async function handleSubmit(event: SubmitEvent<HTMLFormElement>) {
    event.preventDefault()
    if (loading) return

    setError('')
    setLoading(true)

    try {
      const token = await loginUser({
        email: email.trim(),
        password,
      })
      // Only fails if the token isn't one the app understands (e.g. a different claim format)
      if (!saveToken(token)) throw new Error('Unrecognised access token')

      setEmail('')
      setPassword('')

      await navigate('/explore', { replace: true })
    } catch (error) {
      // e.g. "Incorrect login or password", or that the service can't be reached
      setError(
        error instanceof ApiError
          ? error.message
          : 'Could not log in. Check your details and try again.',
      )
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="login-page">
      <main className="login-content">
        <section className="login-card" aria-labelledby="login-title">
          <div className="login-brand">
            <Footprints size={38} strokeWidth={2.4} aria-hidden="true" />
            <h1 id="login-title">CampusRun</h1>
            <p>Run Errands, Build Community</p>
          </div>

          <form
            className="login-form"
            onSubmit={(event) => {
              void handleSubmit(event)
            }}
          >
            <div className="login-field">
              <Label.Root htmlFor="login-email">Email</Label.Root>

              <div className="login-input">
                <Mail size={20} aria-hidden="true" />

                <input
                  id="login-email"
                  name="email"
                  type="email"
                  autoComplete="email"
                  placeholder="you@u.nus.edu"
                  value={email}
                  onChange={(event) => setEmail(event.target.value)}
                  required
                />
              </div>
            </div>

            <div className="login-field">
              <Label.Root htmlFor="login-password">Password</Label.Root>

              <div className="login-input">
                <LockKeyhole size={20} aria-hidden="true" />

                <input
                  id="login-password"
                  name="password"
                  type={showPassword ? 'text' : 'password'}
                  autoComplete="current-password"
                  placeholder="Enter your password"
                  value={password}
                  onChange={(event) => setPassword(event.target.value)}
                  required
                />

                <button
                  className="login-password-toggle"
                  type="button"
                  aria-label={showPassword ? 'Hide password' : 'Show password'}
                  aria-pressed={showPassword}
                  onClick={() => setShowPassword((current) => !current)}
                >
                  {showPassword ? (
                    <EyeOff size={20} aria-hidden="true" />
                  ) : (
                    <Eye size={20} aria-hidden="true" />
                  )}
                </button>
              </div>
            </div>

            {error && (
              <p className="login-error" role="alert">
                {error}
              </p>
            )}

            <button className="login-submit" type="submit" disabled={loading}>
              <span>{loading ? 'Logging in…' : 'Log in'}</span>
            </button>
          </form>

          <p className="login-register">
            Don’t have an account? <Link to="/register">Register</Link>
          </p>
        </section>
      </main>

      <div className="login-art" aria-hidden="true" />
    </div>
  )
}
