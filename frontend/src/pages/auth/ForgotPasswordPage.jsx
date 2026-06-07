import React, { useState } from 'react'
import { Link } from 'react-router-dom'
import { useAuthStore } from '../../store/authStore'

/**
 * WHAT: Password Recovery Portal
 * WHY:  Enables photographers to request recovery tokens, handles server validation,
 *       implements a11y standards, and conforms strictly to the Kyapture design language.
 */
export default function ForgotPasswordPage() {
  const [email, setEmail]   = useState('')
  const [status, setStatus] = useState('idle')  // 'idle' | 'loading' | 'sent' | 'error'
  const [errorMsg, setErrorMsg] = useState('')

  // Selector pattern: subscribes strictly to the recovery dispatch action
  const forgotPassword = useAuthStore((s) => s.forgotPassword)

  async function handleSubmit(e) {
    e.preventDefault()
    if (status === 'loading') return

    if (!email || !/\S+@\S+\.\S+/.test(email)) {
      setErrorMsg('Enter a valid email address.')
      setStatus('error')
      return
    }

    setStatus('loading')
    setErrorMsg('')

    try {
      await forgotPassword(email)
      setStatus('sent')
    } catch (err) {
      const data = err.response?.data || {}
      
      // Standardize and map raw Django REST Framework payload errors
      const parsedMsg =
        data.detail              ||
        data.non_field_errors?.[0] ||
        data.email?.[0]          ||
        'Something went wrong. Please try again.'
        
      setErrorMsg(parsedMsg)
      setStatus('error')
    }
  }

  // ── SUCCESS PORTLET VIEW ───────────────────────────────────────────────────
  const successContent = (
    <div className="auth-card__body">
      <div aria-hidden="true" className="auth-card__icon">📬</div>
      <h1 className="auth-card__title">Check your email</h1>
      <p className="auth-card__sub">
        If <strong className="auth-card__highlight">{email}</strong> is registered,
        a reset link is on its way to your inbox.
      </p>
      <Link to="/login" className="auth-link-btn">
        Return to login
      </Link>
    </div>
  )

  // ── FORM PORTLET VIEW ──────────────────────────────────────────────────────
  const formContent = (
    <div className="auth-card__body">
      <h1 className="auth-card__title">Forgot your password?</h1>
      <p className="auth-card__sub">Enter your email and we'll send you a reset link.</p>

      <form onSubmit={handleSubmit} noValidate>
        {status === 'error' && (
          <div role="alert" className="form-error-alert">
            {errorMsg}
          </div>
        )}

        <div className="form-group">
          <label className="form-label" htmlFor="recovery-email">
            Email address
          </label>
          <input
            id="recovery-email"
            className={`form-input${status === 'error' ? ' error' : ''}`}
            type="email"
            name="email"
            placeholder="you@example.com"
            value={email}
            onChange={(e) => {
              setEmail(e.target.value)
              if (status === 'error') setStatus('idle')
            }}
            autoComplete="email"
            disabled={status === 'loading'}
            aria-invalid={status === 'error'}
          />
        </div>

        <button className="btn-submit" type="submit" disabled={status === 'loading'}>
          {status === 'loading' ? (
            <span className="btn-submit__loader">
              <span className="spinner" aria-hidden="true" />
              Sending reset link…
            </span>
          ) : (
            'Send reset link'
          )}
        </button>

        <p className="auth-footer-text">
          Remembered your password?{' '}
          <Link to="/login" className="auth-link">Back to login</Link>
        </p>
      </form>
    </div>
  )

  // ── SHARED OUTER SHELL ─────────────────────────────────────────────────────
  // The outer wrapper renders exactly ONCE. Only the inner body is swapped,
  // preventing browser layout flashes and unmount animation re-triggers [16].
  return (
    <div className="auth-page">
      <div className="auth-page__bg" />
      <div className="auth-page__grid" />

      <Link to="/login" className="auth-page__back">← Back to login</Link>

      <div className="auth-card animate-fadeUp">
        <div className="auth-card__logo">
          <div className="auth-card__logo-icon">📸</div>
          <div className="auth-card__brand">Kyapture</div>
        </div>

        {status === 'sent' ? successContent : formContent}
      </div>
    </div>
  )
}