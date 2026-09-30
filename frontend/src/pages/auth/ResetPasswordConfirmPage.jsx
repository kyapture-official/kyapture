// C:/Users/LENOVO/Desktop/kyapture/frontend/src/pages/auth/ResetPasswordConfirmPage.jsx
import React, { useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { useAuthStore } from '../../store/authStore'
import { Camera } from 'lucide-react'

/**
 * WHAT: Password Reset Confirmation Portal
 * WHY:  Landing page for the link sent by ForgotPasswordPage's email. Reads
 *       the uidb64/token pair out of the URL, collects a new password, and
 *       submits it to the backend confirm endpoint. Mirrors
 *       ForgotPasswordPage's structure/status-machine/error-parsing so the
 *       two pages stay visually and behaviorally consistent.
 */
export default function ResetPasswordConfirmPage() {
  const { uidb64, token } = useParams()

  const [newPassword, setNewPassword]   = useState('')
  const [newPassword2, setNewPassword2] = useState('')
  const [status, setStatus]     = useState('idle')  // 'idle' | 'loading' | 'done' | 'error'
  const [errorMsg, setErrorMsg] = useState('')

  // Selector pattern: subscribes strictly to the confirm dispatch action
  const resetPasswordConfirm = useAuthStore((s) => s.resetPasswordConfirm)

  const linkIncomplete = !uidb64 || !token

  async function handleSubmit(e) {
    e.preventDefault()
    if (status === 'loading' || linkIncomplete) return

    if (!newPassword || newPassword.length < 8) {
      setErrorMsg('Password must be at least 8 characters.')
      setStatus('error')
      return
    }

    if (newPassword !== newPassword2) {
      setErrorMsg('Passwords do not match.')
      setStatus('error')
      return
    }

    setStatus('loading')
    setErrorMsg('')

    try {
      await resetPasswordConfirm({ uidb64, token, newPassword, newPassword2 })
      setStatus('done')
    } catch (err) {
      const data = err.response?.data || {}

      // Standardize and map raw Django REST Framework payload errors
      const parsedMsg =
        data.error                 ||
        data.detail                ||
        data.non_field_errors?.[0] ||
        data.new_password?.[0]     ||
        data.new_password2?.[0]    ||
        'This reset link is invalid or has expired. Please request a new one.'

      setErrorMsg(parsedMsg)
      setStatus('error')
    }
  }

  // ── SUCCESS PORTLET VIEW ───────────────────────────────────────────────────
  const successContent = (
    <div className="auth-card__body">
      <div aria-hidden="true" className="auth-card__icon">✅</div>
      <h1 className="auth-card__title">Password updated</h1>
      <p className="auth-card__sub">
        Your password has been reset. You can now log in with your new password.
      </p>
      <Link to="/login" className="auth-link-btn">
        Go to login
      </Link>
    </div>
  )

  // ── BROKEN LINK VIEW ────────────────────────────────────────────────────────
  const brokenLinkContent = (
    <div className="auth-card__body">
      <h1 className="auth-card__title">Invalid reset link</h1>
      <p className="auth-card__sub">
        This password reset link is incomplete or malformed. Please request a new one.
      </p>
      <Link to="/forgot-password" className="auth-link-btn">
        Request a new link
      </Link>
    </div>
  )

  // ── FORM PORTLET VIEW ──────────────────────────────────────────────────────
  const formContent = (
    <div className="auth-card__body">
      <h1 className="auth-card__title">Set a new password</h1>
      <p className="auth-card__sub">Choose a new password for your account.</p>

      <form onSubmit={handleSubmit} noValidate>
        {status === 'error' && (
          <div role="alert" className="form-error-alert">
            {errorMsg}
          </div>
        )}

        <div className="form-group">
          <label className="form-label" htmlFor="new-password">
            New password
          </label>
          <input
            id="new-password"
            className={`form-input${status === 'error' ? ' error' : ''}`}
            type="password"
            name="new_password"
            placeholder="••••••••"
            value={newPassword}
            onChange={(e) => {
              setNewPassword(e.target.value)
              if (status === 'error') setStatus('idle')
            }}
            autoComplete="new-password"
            disabled={status === 'loading'}
            aria-invalid={status === 'error'}
          />
        </div>

        <div className="form-group">
          <label className="form-label" htmlFor="new-password-confirm">
            Confirm new password
          </label>
          <input
            id="new-password-confirm"
            className={`form-input${status === 'error' ? ' error' : ''}`}
            type="password"
            name="new_password2"
            placeholder="••••••••"
            value={newPassword2}
            onChange={(e) => {
              setNewPassword2(e.target.value)
              if (status === 'error') setStatus('idle')
            }}
            autoComplete="new-password"
            disabled={status === 'loading'}
            aria-invalid={status === 'error'}
          />
        </div>

        <button className="btn-submit" type="submit" disabled={status === 'loading'}>
          {status === 'loading' ? (
            <span className="btn-submit__loader">
              <span className="spinner" aria-hidden="true" />
              Updating password…
            </span>
          ) : (
            'Reset password'
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
  return (
    <div className="auth-page">
      <div className="auth-page__bg" />
      <div className="auth-page__grid" />

      <Link to="/login" className="auth-page__back">← Back to login</Link>

      <div className="auth-card animate-fadeUp">
        <div className="auth-card__logo">
          <div className="auth-card__logo-icon"><Camera size={24} strokeWidth={1.8} aria-hidden="true" /></div>
          <div className="auth-card__brand">Kyapture</div>
        </div>

        {linkIncomplete
          ? brokenLinkContent
          : status === 'done'
            ? successContent
            : formContent}
      </div>
    </div>
  )
}
