import { useState, type SubmitEvent } from 'react'
import { Link } from 'react-router'
import {
  ArrowRight,
  Eye,
  EyeOff,
  Footprints,
  LockKeyhole,
  Mail,
} from 'lucide-react'
import './login.css'

export type RegisterCredentials = {
  email: string
  password: string
}

type RegisterPageProps = {
  onRegister: (credentials: RegisterCredentials) => Promise<void>
}

export default function RegisterPage({ onRegister }: RegisterPageProps) {
  // const navigate = useNavigate()

  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')

  const [showPassword, setShowPassword] = useState(false)
  const [showConfirmPassword, setShowConfirmPassword] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const passwordMismatch =
    confirmPassword.length > 0 && password !== confirmPassword

  async function handleSubmit(event: SubmitEvent<HTMLFormElement>) {
    event.preventDefault()
    if (loading || passwordMismatch) return

    setError('')
    setLoading(true)

    try {
      // Pass to user service
      await onRegister({
        email: email.trim(),
        password,
      })

      setEmail('')
      setPassword('')
      setConfirmPassword('')

      // await navigate('/login', { replace: true })
    } catch {
      setError('Could not create your account. Please try again.')
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
            onSubmit={(event) => {
              void handleSubmit(event)
            }}
          >
            <div className="login-input">
              <Mail size={20} aria-hidden="true" />

              <input
                id="register-email"
                name="email"
                aria-label="Email"
                type="email"
                autoComplete="email"
                placeholder="Email"
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                required
              />
            </div>

            <div className="login-input">
              <LockKeyhole size={20} aria-hidden="true" />

              <input
                id="register-password"
                name="password"
                aria-label="Password"
                type={showPassword ? 'text' : 'password'}
                autoComplete="new-password"
                placeholder="Password"
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

            <div className="login-input">
              <LockKeyhole size={20} aria-hidden="true" />

              <input
                id="register-confirm-password"
                name="confirmPassword"
                aria-label="Confirm password"
                type={showConfirmPassword ? 'text' : 'password'}
                autoComplete="new-password"
                placeholder="Confirm Password"
                value={confirmPassword}
                aria-invalid={passwordMismatch}
                aria-describedby={
                  passwordMismatch ? 'password-mismatch' : undefined
                }
                onChange={(event) => setConfirmPassword(event.target.value)}
                required
              />

              <button
                className="login-password-toggle"
                type="button"
                aria-label={
                  showConfirmPassword
                    ? 'Hide confirm password'
                    : 'Show confirm password'
                }
                aria-pressed={showConfirmPassword}
                onClick={() => setShowConfirmPassword((current) => !current)}
              >
                {showConfirmPassword ? (
                  <EyeOff size={20} aria-hidden="true" />
                ) : (
                  <Eye size={20} aria-hidden="true" />
                )}
              </button>
            </div>

            {passwordMismatch && (
              <p className="login-error" id="password-mismatch">
                Passwords do not match.
              </p>
            )}
            {error && (
              <p className="login-error" role="alert">
                {error}
              </p>
            )}

            <button className="login-submit" type="submit" disabled={loading}>
              <span>{loading ? 'Registering…' : 'Register'}</span>
              {!loading && <ArrowRight size={18} aria-hidden="true" />}
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
