import React, { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useAuthStore } from '../../store/authStore'

/**
 * Computes password complexity heuristics
 */
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
    email: '', 
    username: '', 
    display_name: '', 
    password: '', 
    password2: ''
  })
  
  const [showPw, setShowPw] = useState(false)
  const [errors, setErrors] = useState({})
  const [agree, setAgree] = useState(false)
  const [loading, setLoading] = useState(false)
  const [pwScore, setPwScore] = useState(0)

  /**
   * WHAT: Unified state mutator transaction
   * WHY: Prevents async batching race conditions and schedules only one state-update per tick.
   */
  function set(field, val) {
    setForm(prev => {
      const nextState = { ...prev, [field]: val }
      
      // Calculate password strength safely
      if (field === 'password') {
        setPwScore(getStrength(val))
      }
      
      // Auto-suggest username securely from email prefix, strictly stripping non-alphanumeric chars
      if (field === 'email') {
        const emailPrefix = val.split('@')[0] || ''
        const suggested = emailPrefix.toLowerCase().replace(/[^a-z0-9]/g, '')
        // Ensure we do not overwrite a username the user has already manually typed
        nextState.username = prev.username || suggested
      }
      
      return nextState
    })

    // Dynamically clear target error state
    setErrors(prev => ({ ...prev, [field]: '', general: '' }))
  }

  /**
   * WHAT: Defensive form validation scanner
   * WHY: Ensures compliance with RFC DNS guidelines and isolates formatting bugs before hitting Django.
   */
  function validate() {
    const e = {}
    
    // Strict email structure check
    if (!form.email || !/\S+@\S+\.\S+/.test(form.email)) {
      e.email = 'Enter a valid email'
    }
    
    // Subdomain Validation Protocol (Strict RFC 1035 / RFC 1123 Compliance)
    const cleanUsername = form.username.trim()
    if (!cleanUsername || cleanUsername.length < 3) {
      e.username = 'Username must be 3+ characters'
    } else {
      // Must only contain letters, numbers, and isolated single hyphens. No underscores, no leading/trailing hyphens.
      const dnsRegex = /^[a-z0-9]+(?:-[a-z0-9]+)*$/
      if (!dnsRegex.test(cleanUsername)) {
        e.username = 'Only lowercase letters, numbers, and single hyphens are allowed. Cannot start/end with hyphens.'
      }
    }
    
    if (!form.password || form.password.length < 8) {
      e.password = 'Password must be 8+ characters'
    }
    
    if (form.password !== form.password2) {
      e.password2 = 'Passwords do not match'
    }
    
    return e
  }

  const handleSubmit = async (e) => {
    e.preventDefault()
    if (loading) return // Prevent duplicate execution streams on multiple clicks

    const errs = validate()
    if (Object.keys(errs).length) { 
      setErrors(errs)
      return 
    }
    
    if (!agree) { 
      setErrors({ agree: 'Please agree to the Terms of Service' })
      return 
    }
    
    setErrors({})
    setLoading(true)
    
    try {
      // payload-sanitize: Include password2 to satisfy backend validation checks
      const payload = {
        email: form.email,
        username: form.username,
        display_name: form.display_name,
        password: form.password,
        password2: form.password2
      }
      
      await register(payload)
      navigate('/dashboard')
    } catch (err) {
      // Standardize structured exception mapping
      setErrors(err.response?.data || { general: 'Registration failed. Please check your inputs.' })
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
          <button className="auth-tab auth-tab--active" type="button">Create account</button>
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
                placeholder=""
                value={form.display_name}
                onChange={e => set('display_name', e.target.value)}
                autoComplete="name"
                disabled={loading}
              />
              {errors.display_name && <div className="form-error">{errors.display_name}</div>}
            </div>
            
            <div className="form-group">
              <label className="form-label">Username</label>
              <input
                className={`form-input ${errors.username ? 'error' : ''}`}
                placeholder="yourname"
                // Enforce strict lowercase, transform spaces to hyphens instantly, and strip underscores
                value={form.username}
                onChange={e => {
                  const sanitizedValue = e.target.value
                    .toLowerCase()
                    .replace(/\s+/g, '-')
                    .replace(/[^a-z0-9-]/g, '') // Strict exclusion of underscores
                  set('username', sanitizedValue)
                }}
                autoComplete="username"
                disabled={loading}
              />
              {errors.username && <div className="form-error">{errors.username}</div>}
            </div>
          </div>

          {/* Subdomain URL live projection */}
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
                placeholder="Minimum 8 characters"
                value={form.password}
                onChange={e => set('password', e.target.value)}
                autoComplete="new-password"
                disabled={loading}
              />
              <button type="button" className="eye-btn" onClick={() => setShowPw(p => !p)} disabled={loading}>
                {showPw ? '🙈' : '👁'}
              </button>
            </div>
            
            {form.password && (
              <div className="pw-strength">
                <div className="pw-strength__bars">
                  {[1, 2, 3, 4].map(i => (
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
              disabled={loading}
            />
            {errors.password2 && <div className="form-error">{errors.password2}</div>}
          </div>

          {/* Terms */}
          <label className="auth-check auth-check--terms">
            <input 
              type="checkbox" 
              checked={agree} 
              onChange={e => setAgree(e.target.checked)} 
              disabled={loading}
            />
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

          {/* Submit Button with Loading states */}
          <button className="btn-submit" type="submit" disabled={loading}>
            {loading ? (
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8 }}>
                <div className="spinner" /> 
                <span>Creating account…</span>
              </div>
            ) : (
              'Create my account ✨'
            )}
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