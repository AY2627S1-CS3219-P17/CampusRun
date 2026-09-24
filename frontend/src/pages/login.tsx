import { useState, type SubmitEvent } from 'react'
import { Link } from 'react-router'
import { Label } from 'radix-ui'
import {
  ArrowRight,
  Eye,
  EyeOff,
  Footprints,
  LockKeyhole,
  Mail,
} from 'lucide-react'
import './login.css'

export type LoginCredentials = {
  email: string
  password: string
}

type LoginPageProps = {
  onLogin: (credentials: LoginCredentials) => Promise<void>
}

export default function LoginPage({ onLogin }: LoginPageProps) {
  // const navigate = useNavigate()

  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  async function handleSubmit(event: SubmitEvent<HTMLFormElement>) {
    event.preventDefault()
    if (loading) return

    setError('')
    setLoading(true)

    try {
      // Pass to user service
      await onLogin({
        email: email.trim(),
        password,
      })

      setEmail('')
      setPassword('')

      // await navigate('/explore', { replace: true })
    } catch {
      setError('Could not log in. Check your details and try again.')
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
              {!loading && <ArrowRight size={18} aria-hidden="true" />}
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
