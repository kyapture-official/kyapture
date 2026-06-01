import React, { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useAuthStore } from '../../store/authStore'

export default function LoginPage() {
  const navigate = useNavigate()
  const { login } = useAuthStore()
  const [form, setForm] = useState({ email: '', password: '' })
  const [showPw, setShowPw] = useState(false)
  const [errors, setErrors] = useState({})
  const [loading, setLoading] = useState(false)

  const set = (k) => (e) => {
    setForm(f => ({ ...f, [k]: e.target.value }))
    setErrors(prev => ({ ...prev, [k]: '', general: '' }))
  }

  function validate() {
    const e = {}
    if (!form.email || !/\S+@\S+\.\S+/.test(form.email)) e.email = 'Enter a valid email address'
    if (!form.password || form.password.length < 6) e.password = 'Password must be at least 6 characters'
    return e
  }

  const handleSubmit = async (e) => {
    e.preventDefault()
    const errs = validate()
    if (Object.keys(errs).length) { setErrors(errs); return }
    setErrors({})
    setLoading(true)
    try {
      await login(form.email, form.password)
      navigate('/dashboard')
    } catch (err) {
      const data = err.response?.data || {}
      if (data.non_field_errors) setErrors({ general: data.non_field_errors[0] })
      else setErrors({ ...data, general: data.detail || 'Invalid email or password' })
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
          <button className="auth-tab auth-tab--active">Sign in</button>
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
              placeholder="you@example.com"
              value={form.email}
              onChange={set('email')}
              autoComplete="email"
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
                placeholder="Your password"
                value={form.password}
                onChange={set('password')}
                autoComplete="current-password"
              />
              <button type="button" className="eye-btn" onClick={() => setShowPw(p => !p)}>
                {showPw ? '🙈' : '👁'}
              </button>
            </div>
            {errors.password && <div className="form-error">{errors.password}</div>}
          </div>

          {/* Remember + forgot */}
          <div className="auth-row">
            <label className="auth-check" style={{ marginBottom: 0 }}>
              <input type="checkbox" />
              <span>Remember me</span>
            </label>
            <a href="#" className="auth-link">Forgot password?</a>
          </div>

          <button className="btn-submit" type="submit" disabled={loading}>
            {loading ? <><div className="spinner" /> Signing in…</> : 'Sign in to Kyapture'}
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
