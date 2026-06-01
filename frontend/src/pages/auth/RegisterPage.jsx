import React, { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useAuthStore } from '../../store/authStore'

function getStrength(pw) {
  let score = 0
  if (pw.length >= 8)            score++
  if (/[A-Z]/.test(pw))          score++
  if (/[0-9]/.test(pw))          score++
  if (/[^A-Za-z0-9]/.test(pw))  score++
  return score
}
const STRENGTH_LABELS = ['', 'Weak', 'Fair', 'Good', 'Strong 💪']
const STRENGTH_COLORS = ['', '#c0483a', '#c17f3e', '#c17f3e', '#4a7c6f']

export default function RegisterPage() {
  const navigate = useNavigate()
  const { register } = useAuthStore()
  const [form, setForm] = useState({
    email: '', username: '', display_name: '', password: '', password2: ''
  })
  const [showPw, setShowPw] = useState(false)
  const [errors, setErrors] = useState({})
  const [agree, setAgree] = useState(false)
  const [loading, setLoading] = useState(false)
  const [pwScore, setPwScore] = useState(0)

  function set(field, val) {
    setForm(prev => ({ ...prev, [field]: val }))
    setErrors(prev => ({ ...prev, [field]: '' }))
    if (field === 'password') setPwScore(getStrength(val))
    if (field === 'email') {
      const suggested = val.split('@')[0].toLowerCase().replace(/[^a-z0-9]/g, '')
      setForm(prev => ({
        ...prev,
        email: val,
        username: prev.username || suggested,
      }))
    }
  }

  function validate() {
    const e = {}
    if (!form.email || !/\S+@\S+\.\S+/.test(form.email)) e.email = 'Enter a valid email'
    if (!form.username || form.username.length < 3) e.username = 'Username must be 3+ characters'
    if (!/^[a-z0-9_-]+$/.test(form.username)) e.username = 'Lowercase letters, numbers, _ and - only'
    if (!form.password || form.password.length < 8) e.password = 'Password must be 8+ characters'
    if (form.password !== form.password2) e.password2 = 'Passwords do not match'
    return e
  }

  const handleSubmit = async (e) => {
    e.preventDefault()
    const errs = validate()
    if (Object.keys(errs).length) { setErrors(errs); return }
    if (!agree) { setErrors({ agree: 'Please agree to the Terms of Service' }); return }
    setErrors({})
    setLoading(true)
    try {
      await register(form)
      navigate('/dashboard')
    } catch (err) {
      setErrors(err.response?.data || { general: 'Registration failed. Please try again.' })
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

        <h1 className="auth-card__title">Create account</h1>
        <p className="auth-card__sub">Start delivering beautiful galleries today</p>

        {/* Tabs */}
        <div className="auth-tabs">
          <Link to="/login" className="auth-tab" style={{ textDecoration: 'none', textAlign: 'center' }}>
            Sign in
          </Link>
          <button className="auth-tab auth-tab--active">Create account</button>
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

          {/* Name row */}
          <div className="form-row">
            <div className="form-group">
              <label className="form-label">Display name</label>
              <input
                className={`form-input ${errors.display_name ? 'error' : ''}`}
                placeholder="Jane Smith Photography"
                value={form.display_name}
                onChange={e => set('display_name', e.target.value)}
                autoComplete="name"
              />
              {errors.display_name && <div className="form-error">{errors.display_name}</div>}
            </div>
            <div className="form-group">
              <label className="form-label">Username</label>
              <input
                className={`form-input ${errors.username ? 'error' : ''}`}
                placeholder="yourname"
                value={form.username}
                onChange={e => set('username', e.target.value.toLowerCase().replace(/[^a-z0-9_-]/g, ''))}
                autoComplete="username"
              />
              {errors.username && <div className="form-error">{errors.username}</div>}
            </div>
          </div>

          {form.username && !errors.username && (
            <div className="form-hint" style={{ marginTop: -10, marginBottom: 14 }}>
              Your gallery link:{' '}
              <strong style={{ color: 'var(--accent)' }}>{form.username}.kyapture.com</strong>
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
              onChange={e => set('email', e.target.value)}
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
                placeholder="Minimum 8 characters"
                value={form.password}
                onChange={e => set('password', e.target.value)}
                autoComplete="new-password"
              />
              <button type="button" className="eye-btn" onClick={() => setShowPw(p => !p)}>
                {showPw ? '🙈' : '👁'}
              </button>
            </div>
            {form.password && (
              <div className="pw-strength">
                <div className="pw-strength__bars">
                  {[1,2,3,4].map(i => (
                    <div
                      key={i}
                      className="pw-strength__bar"
                      style={{ background: i <= pwScore ? STRENGTH_COLORS[pwScore] : 'var(--warm)' }}
                    />
                  ))}
                </div>
                <div className="pw-strength__label" style={{ color: STRENGTH_COLORS[pwScore] }}>
                  {STRENGTH_LABELS[pwScore]}
                </div>
              </div>
            )}
            {errors.password && <div className="form-error">{errors.password}</div>}
          </div>

          {/* Confirm password */}
          <div className="form-group">
            <label className="form-label">Confirm password</label>
            <input
              className={`form-input ${errors.password2 ? 'error' : ''}`}
              type="password"
              placeholder="Repeat password"
              value={form.password2}
              onChange={e => set('password2', e.target.value)}
              autoComplete="new-password"
            />
            {errors.password2 && <div className="form-error">{errors.password2}</div>}
          </div>

          {/* Terms */}
          <label className="auth-check auth-check--terms">
            <input type="checkbox" checked={agree} onChange={e => setAgree(e.target.checked)} />
            <span>
              I agree to the{' '}
              <a href="#" className="auth-link">Terms of Service</a>
              {' '}and{' '}
              <a href="#" className="auth-link">Privacy Policy</a>
            </span>
          </label>
          {errors.agree && <div className="form-error" style={{ marginTop: -12, marginBottom: 12 }}>{errors.agree}</div>}

          {errors.non_field_errors && (
            <div className="form-error" style={{ marginBottom: 12 }}>{errors.non_field_errors[0]}</div>
          )}

          <button className="btn-submit" type="submit" disabled={loading}>
            {loading ? <><div className="spinner" /> Creating account…</> : 'Create my account ✨'}
          </button>

          <p className="auth-footer-text">
            Already have an account?{' '}
            <Link to="/login" className="auth-link">Sign in</Link>
          </p>
        </form>
      </div>
    </div>
  )
}
