import React, { useState, useEffect } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useAuthStore } from '../../store/authStore'

export default function LoginPage() {
  const navigate = useNavigate()
  const { login } = useAuthStore()

  // Initialize state based on persistent caching rules
  const [rememberMe, setRememberMe] = useState(() => {
    return localStorage.getItem('remember_me') === 'true'
  })

  const [form, setForm] = useState({ 
    email: localStorage.getItem('saved_email') || '', 
    password: '' 
  })

  const [showPw, setShowPw] = useState(false)
  const [errors, setErrors] = useState({})
  const [loading, setLoading] = useState(false)

  /**
   * WHAT: Unified change handler
   * WHY: Eliminates memory allocation spikes during render loops.
   */
  const handleChange = (e) => {
    const { name, value } = e.target
    setForm(prev => ({ ...prev, [name]: value }))
    // Clear field-specific error states dynamically
    setErrors(prev => ({ ...prev, [name]: '', general: '' }))
  }

  /**
   * WHAT: Frontend validation check
   * WHY: Catches structural issues before invoking server request cycles.
   */
  function validate() {
    const e = {}
    if (!form.email || !/\S+@\S+\.\S+/.test(form.email)) {
      e.email = 'Enter a valid email address'
    }
    // Match the 8-character password system schema
    if (!form.password || form.password.length < 8) {
      e.password = 'Password must be at least 8 characters'
    }
    return e
  }

  const handleSubmit = async (e) => {
    e.preventDefault()
    if (loading) return // Strict lock against multi-click transaction duplicates

    const errs = validate()
    if (Object.keys(errs).length) { 
      setErrors(errs)
      return 
    }

    setErrors({})
    setLoading(true)

    try {
      await login(form.email, form.password)

      // Handle credentials caching for Remember Me
      if (rememberMe) {
        localStorage.setItem('saved_email', form.email)
        localStorage.setItem('remember_me', 'true')
      } else {
        localStorage.removeItem('saved_email')
        localStorage.setItem('remember_me', 'false')
      }

      navigate('/dashboard')
    } catch (err) {
      const data = err.response?.data || {}
      if (data.non_field_errors) {
        setErrors({ general: data.non_field_errors[0] })
      } else {
        setErrors({ 
          ...data, 
          general: data.detail || 'Invalid email address or password. Please try again.' 
        })
      }
    } finally {
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
          {errors.general && (
            <div style={{
              marginBottom: 16, padding: '10px 14px',
              background: 'rgba(192,72,58,0.08)', border: '1px solid rgba(192,72,58,0.2)',
              borderRadius: 9, fontSize: 13, color: 'var(--red)'
            }}>
              {errors.general}
            </div>
          )}

          {/* Email */}
          <div className="form-group">
            <label className="form-label">Email address</label>
            <input
              className={`form-input ${errors.email ? 'error' : ''}`}
              type="email"
              name="email"
              placeholder="you@example.com"
              value={form.email}
              onChange={handleChange}
              autoComplete="email"
              disabled={loading}
            />
            {errors.email && <div className="form-error">{errors.email}</div>}
          </div>

          {/* Password */}
          <div className="form-group">
            <label className="form-label">Password</label>
            <div className="input-wrap">
              <input
                className={`form-input ${errors.password ? 'error' : ''}`}
                type={showPw ? 'text' : 'password'}
                name="password"
                placeholder="Your password"
                value={form.password}
                onChange={handleChange}
                autoComplete="current-password"
                disabled={loading}
              />
              <button 
                type="button" 
                className="eye-btn" 
                onClick={() => setShowPw(p => !p)}
                disabled={loading}
              >
                {showPw ? '🙈' : '👁'}
              </button>
            </div>
            {errors.password && <div className="form-error">{errors.password}</div>}
          </div>

          {/* Remember + forgot */}
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