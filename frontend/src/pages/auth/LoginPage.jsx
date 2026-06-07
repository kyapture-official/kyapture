import React, { useState, useEffect } from 'react'
import { Link, useNavigate, useLocation } from 'react-router-dom'
import { useAuthStore } from '../../store/authStore'

/**
 * WHAT: Core Authentication Login Portal
 * WHY:  Authenticates photographers, handles credential caching via "Remember Me",
 *       normalizes DRF server array errors, and respects active deep-link redirects.
 */
export default function LoginPage() {
  const navigate   = useNavigate()
  const location   = useLocation()
  const { login, isAuthenticated } = useAuthStore()

  const [rememberMe, setRememberMe] = useState(
    () => localStorage.getItem('remember_me') === 'true'
  )
  const [form, setForm] = useState({
    email:    localStorage.getItem('saved_email') || '',
    password: ''
  })
  const [showPw,  setShowPw]  = useState(false)
  const [errors,  setErrors]  = useState({})
  const [loading, setLoading] = useState(false)

  /**
   * WHAT: Passive Session Guard
   * WHY:  Redirects users who land on /login while already authenticated
   *       (e.g. browser back-button after login, direct URL entry).
   *       Intentionally kept separate from handleSubmit navigation so that
   *       the try-block retains full access to the login API response for
   *       conditional routing decisions (onboarding, subscription checks, etc).
   */
  useEffect(() => {
    if (isAuthenticated) {
      const destination = location.state?.from?.pathname || '/dashboard'
      navigate(destination, { replace: true })
    }
  }, [isAuthenticated, navigate, location])

  // Clears per-field errors on every keystroke so stale messages never linger
  const handleChange = (e) => {
    const { name, value } = e.target
    setForm(prev => ({ ...prev, [name]: value }))
    setErrors(prev => ({ ...prev, [name]: '', general: '' }))
  }

  /**
   * WHAT: Frontend pre-flight validation
   * WHY:  Password length is deliberately NOT checked here — that is a
   *       registration constraint. Enforcing it on login would permanently
   *       lock out accounts created before the rule was introduced.
   */
  function validate() {
    const e = {}
    if (!form.email || !/\S+@\S+\.\S+/.test(form.email)) {
      e.email = 'Enter a valid email address'
    }
    if (!form.password) {
      e.password = 'Please enter your password'
    }
    return e
  }

  const handleSubmit = async (e) => {
    e.preventDefault()
    if (loading) return

    const errs = validate()
    if (Object.keys(errs).length) {
      setErrors(errs)
      return
    }

    setErrors({})
    setLoading(true)

    try {
      // Store the response so we can inspect it for conditional routing.
      // Example: loginResponse.user.needs_onboarding → navigate('/onboarding')
      const loginResponse = await login(form.email, form.password)

      // Persist Remember Me credentials
      if (rememberMe) {
        localStorage.setItem('saved_email', form.email)
        localStorage.setItem('remember_me', 'true')
      } else {
        localStorage.removeItem('saved_email')
        localStorage.setItem('remember_me', 'false')
      }

      // Conditional routing hook — extend here as business rules grow
      const destination = location.state?.from?.pathname || '/dashboard'
      navigate(destination, { replace: true })
      // Note: setLoading(false) is intentionally omitted on success.
      // The component unmounts on navigation; updating state on an
      // unmounted component triggers a React warning.

    } catch (err) {
      // Renamed to errData to avoid shadowing loginResponse above
      const errData = err.response?.data || {}
      const parsedErrors = {}

      // Normalize DRF error shapes into a flat { field: message } map
      if (errData.non_field_errors) {
        parsedErrors.general = errData.non_field_errors[0]
      } else if (errData.detail) {
        parsedErrors.general = errData.detail
      } else {
        Object.keys(errData).forEach((key) => {
          const val = errData[key]
          parsedErrors[key] = Array.isArray(val) ? val[0] : val
        })
      }

      // Generic fallback only fires when the server returned nothing parseable,
      // preventing the fallback from stacking on top of real field errors.
      if (Object.keys(parsedErrors).length === 0) {
        parsedErrors.general = 'Invalid email address or password. Please try again.'
      }

      setErrors(parsedErrors)
      setLoading(false)
    }
  }

  return (
    <div className="auth-page">
      <div className="auth-page__bg" />
      <div className="auth-page__grid" />

      <Link to="/" className="auth-page__back">← Back to home</Link>

      <div className="auth-card animate-fadeUp">
        {/* Logo */}
        <div className="auth-card__logo">
          <div className="auth-card__logo-icon">📸</div>
          <div className="auth-card__brand">Kyapture</div>
        </div>

        <h1 className="auth-card__title">Welcome back</h1>
        <p className="auth-card__sub">Sign in to your Kyapture account</p>

        {/* Tabs */}
        <div className="auth-tabs">
          <button className="auth-tab auth-tab--active" type="button">Sign in</button>
          <Link to="/register" className="auth-tab" style={{ textDecoration: 'none', textAlign: 'center' }}>
            Create account
          </Link>
        </div>

        <form onSubmit={handleSubmit} noValidate>

          {/* General error banner */}
          {errors.general && (
            <div
              role="alert"
              style={{
                marginBottom: 16, padding: '10px 14px',
                background: 'rgba(192,72,58,0.08)', border: '1px solid rgba(192,72,58,0.2)',
                borderRadius: 9, fontSize: 13, color: 'var(--red)'
              }}
            >
              {errors.general}
            </div>
          )}

          {/* Email — htmlFor links label to input; aria-describedby links input to its error */}
          <div className="form-group">
            <label className="form-label" htmlFor="login-email">Email address</label>
            <input
              id="login-email"
              className={`form-input ${errors.email ? 'error' : ''}`}
              type="email"
              name="email"
              placeholder="you@example.com"
              value={form.email}
              onChange={handleChange}
              autoComplete="email"
              disabled={loading}
              aria-invalid={!!errors.email}
              aria-describedby={errors.email ? 'login-email-error' : undefined}
            />
            {errors.email && (
              <div id="login-email-error" className="form-error">{errors.email}</div>
            )}
          </div>

          {/* Password — same aria pattern as email */}
          <div className="form-group">
            <label className="form-label" htmlFor="login-password">Password</label>
            <div className="input-wrap">
              <input
                id="login-password"
                className={`form-input ${errors.password ? 'error' : ''}`}
                type={showPw ? 'text' : 'password'}
                name="password"
                placeholder="Your password"
                value={form.password}
                onChange={handleChange}
                autoComplete="current-password"
                disabled={loading}
                aria-invalid={!!errors.password}
                aria-describedby={errors.password ? 'login-password-error' : undefined}
              />
              <button
                type="button"
                className="eye-btn"
                onClick={() => setShowPw(p => !p)}
                disabled={loading}
                aria-label={showPw ? 'Hide password' : 'Show password'}
              >
                {showPw ? '🙈' : '👁'}
              </button>
            </div>
            {errors.password && (
              <div id="login-password-error" className="form-error">{errors.password}</div>
            )}
          </div>

          {/* Remember me + Forgot password */}
          <div className="auth-row">
            <label className="auth-check" style={{ marginBottom: 0 }}>
              <input
                type="checkbox"
                checked={rememberMe}
                onChange={(e) => setRememberMe(e.target.checked)}
                disabled={loading}
              />
              <span>Remember me</span>
            </label>
            <Link to="/forgot-password" className="auth-link">Forgot password?</Link>
          </div>

          <button className="btn-submit" type="submit" disabled={loading}>
            {loading ? (
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8 }}>
                <div className="spinner" />
                <span>Signing in…</span>
              </div>
            ) : (
              'Sign in to Kyapture'
            )}
          </button>

          <p className="auth-footer-text">
            Don't have an account?{' '}
            <Link to="/register" className="auth-link">Create one free</Link>
          </p>

        </form>
      </div>
    </div>
  )
}
