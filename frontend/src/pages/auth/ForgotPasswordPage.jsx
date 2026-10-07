// C:/Users/LENOVO/Desktop/kyapture/frontend/src/pages/auth/ForgotPasswordPage.jsx
import React, { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { useAuthStore } from '../../store/authStore'
import { Camera } from 'lucide-react'
import { useNoIndex } from '../../hooks/useNoIndex'
import { forgotErrorMessage } from '../../utils/resetFlow'

const RESEND_COOLDOWN_SECONDS = 30

/**
 * WHAT: "Forgot password" (7-C).
 * WHY:  The server answers the same for every well-formed address, registered
 *       or not, so the "sent" state never says whether an account exists. It
 *       shows the server's own message. "Send another link" asks again for real
 *       (the server caps emails per address per hour and still answers the same);
 *       the short cooldown here only stops double clicks.
 */
export default function ForgotPasswordPage() {
  useNoIndex()

  const [email, setEmail]   = useState('')
  const [status, setStatus] = useState('idle')  // 'idle' | 'loading' | 'sent' | 'error'
  const [errorMsg, setErrorMsg] = useState('')
  const [sentMessage, setSentMessage] = useState('')
  const [cooldown, setCooldown] = useState(0)
  const [resent, setResent] = useState(false)

  const forgotPassword = useAuthStore((s) => s.forgotPassword)

  useEffect(() => {
    if (cooldown <= 0) return undefined
    const id = setTimeout(() => setCooldown((s) => s - 1), 1000)
    return () => clearTimeout(id)
  }, [cooldown])

  async function send({ again = false } = {}) {
    setStatus('loading')
    setErrorMsg('')
    try {
      const message = await forgotPassword(email.trim())
      setSentMessage(message)
      setResent(again)
      setCooldown(RESEND_COOLDOWN_SECONDS)
      setStatus('sent')
    } catch (err) {
      setErrorMsg(forgotErrorMessage(err))
      setStatus('error')
    }
  }

  function handleSubmit(e) {
    e.preventDefault()
    if (status === 'loading') return
    if (!email || !/\S+@\S+\.\S+/.test(email)) {
      setErrorMsg('Enter a valid email address.')
      setStatus('error')
      return
    }
    send()
  }

  // ── SENT ───────────────────────────────────────────────────────────────────
  const sentContent = (
    <div className="auth-card__body" data-forgot-state="sent">
      <div aria-hidden="true" className="auth-card__icon">📬</div>
      <h1 className="auth-card__title">Check your email</h1>
      <p className="auth-card__sub" role="status">
        {sentMessage}
      </p>
      <p className="auth-card__sub">
        Sent to <strong className="auth-card__highlight">{email.trim()}</strong>. Nothing there after a few
        minutes? Check your spam folder.
      </p>
      {resent && <p className="form-hint" role="status">We asked for another link. Only the newest link works.</p>}
      <Link to="/login" className="auth-link-btn">
        Return to login
      </Link>
      <button
        type="button"
        className="auth-secondary-btn"
        onClick={() => send({ again: true })}
        disabled={cooldown > 0}
      >
        {cooldown > 0 ? `Send another link (${cooldown}s)` : 'Send another link'}
      </button>
      <p className="auth-footer-text">
        Wrong address?{' '}
        <button type="button" className="auth-link" style={{ background: 'none', border: 0, padding: 0, cursor: 'pointer', font: 'inherit' }}
          onClick={() => { setStatus('idle'); setResent(false); setSentMessage('') }}>
          Use a different email
        </button>
      </p>
    </div>
  )

  // ── FORM ───────────────────────────────────────────────────────────────────
  const formContent = (
    <div className="auth-card__body" data-forgot-state={status === 'error' ? 'error' : 'form'}>
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
  // preventing browser layout flashes and unmount animation re-triggers.
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

        {status === 'sent' || (status === 'loading' && sentMessage) ? sentContent : formContent}
      </div>
    </div>
  )
}
