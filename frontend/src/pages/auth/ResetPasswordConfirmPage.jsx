// C:/Users/LENOVO/Desktop/kyapture/frontend/src/pages/auth/ResetPasswordConfirmPage.jsx
import React, { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { useAuthStore } from '../../store/authStore'
import { Camera } from 'lucide-react'
import { useNoIndex } from '../../hooks/useNoIndex'
import { readResetToken, resetErrorState } from '../../utils/resetFlow'

/**
 * WHAT: Landing page of the emailed "forgot password" link (7-C):
 *       /reset-password#token=...
 * WHY:  The token travels in the URL fragment, so no server ever receives it in
 *       a URL. It is read ONCE when the page loads, removed from the address
 *       bar and the history entry right away (history.replaceState), kept only
 *       in memory, and sent in a POST body. The link is checked before the form
 *       shows, so an expired or used link says so at once.
 *
 * States: checking -> form -> done, or invalid (unknown / expired / used /
 * replaced by a newer link). A refused password keeps the form (the link stays
 * usable); too many tries and network errors show a message on the form.
 */
export default function ResetPasswordConfirmPage() {
  useNoIndex()

  // Read before the first paint; the effect below wipes it from the URL.
  const [token, setToken] = useState(() => readResetToken(window.location.hash))
  // Bumped when another link is opened in this same tab, so it is checked even if it is the same token.
  const [linkOpen, setLinkOpen] = useState(0)

  const [phase, setPhase] = useState(token ? 'checking' : 'invalid') // checking | form | invalid | done
  const [submitting, setSubmitting] = useState(false)
  const [newPassword, setNewPassword]   = useState('')
  const [newPassword2, setNewPassword2] = useState('')
  const [passwordErrors, setPasswordErrors] = useState([])
  const [confirmError, setConfirmError] = useState('')
  const [formError, setFormError] = useState('')

  const checkResetToken = useAuthStore((s) => s.checkResetToken)
  const resetPasswordConfirm = useAuthStore((s) => s.resetPasswordConfirm)

  useEffect(() => {
    const stripHash = () => {
      if (window.location.hash) {
        window.history.replaceState(window.history.state, '', window.location.pathname)
      }
    }
    stripHash()
    // Opening a link while this page is already open (same path, new fragment)
    // does not reload the page: read the new token, wipe it, start over.
    function onHashChange() {
      const next = readResetToken(window.location.hash)
      stripHash()
      setNewPassword('')
      setNewPassword2('')
      setPasswordErrors([])
      setConfirmError('')
      setFormError('')
      setToken(next)
      setPhase(next ? 'checking' : 'invalid')
      setLinkOpen((n) => n + 1)
    }
    window.addEventListener('hashchange', onHashChange)
    return () => window.removeEventListener('hashchange', onHashChange)
  }, [])

  useEffect(() => {
    if (!token) return undefined
    let cancelled = false
    checkResetToken(token)
      .then(() => { if (!cancelled) setPhase('form') })
      .catch((err) => {
        if (cancelled) return
        const state = resetErrorState(err)
        if (state.kind === 'invalid') {
          setPhase('invalid')
        } else {
          // Throttled or offline: the link may be fine, so offer the form and say why the check failed.
          setFormError(state.message)
          setPhase('form')
        }
      })
    return () => { cancelled = true }
  }, [token, linkOpen, checkResetToken])

  function clearErrors() {
    setPasswordErrors([])
    setConfirmError('')
    setFormError('')
  }

  async function handleSubmit(e) {
    e.preventDefault()
    if (submitting) return
    clearErrors()

    if (newPassword.length < 8) {
      setPasswordErrors(['Use at least 8 characters.'])
      return
    }
    if (newPassword !== newPassword2) {
      setConfirmError('Passwords do not match.')
      return
    }

    setSubmitting(true)
    try {
      await resetPasswordConfirm({ token, newPassword, newPassword2 })
      setNewPassword('')
      setNewPassword2('')
      setPhase('done')
    } catch (err) {
      const state = resetErrorState(err)
      if (state.kind === 'invalid') {
        setPhase('invalid')
      } else if (state.kind === 'fields') {
        setPasswordErrors(state.password)
        setConfirmError(state.confirm)
      } else {
        setFormError(state.message)
      }
    } finally {
      setSubmitting(false)
    }
  }

  // ── SUCCESS ────────────────────────────────────────────────────────────────
  const successContent = (
    <div className="auth-card__body" data-reset-state="done">
      <div aria-hidden="true" className="auth-card__icon">✅</div>
      <h1 className="auth-card__title">Password updated</h1>
      <p className="auth-card__sub">
        Your password has been reset and every device that was signed in has been signed out.
        Sign in with your new password.
      </p>
      <Link to="/login" className="auth-link-btn">
        Go to login
      </Link>
    </div>
  )

  // ── INVALID / EXPIRED LINK ─────────────────────────────────────────────────
  const invalidContent = (
    <div className="auth-card__body" data-reset-state="invalid">
      <h1 className="auth-card__title">This link can't be used</h1>
      <p className="auth-card__sub">
        The reset link is invalid or has expired. A link works once, only the newest one you
        requested works, and it expires after a short time. Request a new one.
      </p>
      <Link to="/forgot-password" className="auth-link-btn">
        Request a new link
      </Link>
    </div>
  )

  // ── CHECKING ───────────────────────────────────────────────────────────────
  const checkingContent = (
    <div className="auth-card__body" data-reset-state="checking" aria-busy="true">
      <h1 className="auth-card__title">Checking your link…</h1>
      <p className="auth-card__sub">
        <span className="spinner" aria-hidden="true" /> One moment.
      </p>
    </div>
  )

  // ── FORM ───────────────────────────────────────────────────────────────────
  const formContent = (
    <div className="auth-card__body" data-reset-state="form">
      <h1 className="auth-card__title">Set a new password</h1>
      <p className="auth-card__sub">
        Use at least 8 characters. It can't be your email address or your current password.
      </p>

      <form onSubmit={handleSubmit} noValidate>
        {formError && (
          <div role="alert" className="form-error-alert">
            {formError}
          </div>
        )}

        <div className="form-group">
          <label className="form-label" htmlFor="new-password">
            New password
          </label>
          <input
            id="new-password"
            className={`form-input${passwordErrors.length ? ' error' : ''}`}
            type="password"
            name="new_password"
            placeholder="••••••••"
            value={newPassword}
            onChange={(e) => { setNewPassword(e.target.value); if (passwordErrors.length) setPasswordErrors([]) }}
            autoComplete="new-password"
            disabled={submitting}
            aria-invalid={passwordErrors.length > 0}
            aria-describedby={passwordErrors.length ? 'new-password-error' : undefined}
          />
          {passwordErrors.length > 0 && (
            <ul id="new-password-error" role="alert" className="form-error">
              {passwordErrors.map((msg) => <li key={msg}>{msg}</li>)}
            </ul>
          )}
        </div>

        <div className="form-group">
          <label className="form-label" htmlFor="new-password-confirm">
            Confirm new password
          </label>
          <input
            id="new-password-confirm"
            className={`form-input${confirmError ? ' error' : ''}`}
            type="password"
            name="new_password2"
            placeholder="••••••••"
            value={newPassword2}
            onChange={(e) => { setNewPassword2(e.target.value); if (confirmError) setConfirmError('') }}
            autoComplete="new-password"
            disabled={submitting}
            aria-invalid={Boolean(confirmError)}
            aria-describedby={confirmError ? 'new-password-confirm-error' : undefined}
          />
          {confirmError && (
            <p id="new-password-confirm-error" role="alert" className="form-error">{confirmError}</p>
          )}
        </div>

        <button className="btn-submit" type="submit" disabled={submitting}>
          {submitting ? (
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

  const content = {
    checking: checkingContent,
    form: formContent,
    invalid: invalidContent,
    done: successContent,
  }[phase]

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

        {content}
      </div>
    </div>
  )
}
