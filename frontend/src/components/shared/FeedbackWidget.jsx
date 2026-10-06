// File Location: frontend/src/components/shared/FeedbackWidget.jsx
import { useCallback, useEffect, useId, useRef, useState } from 'react'
import { useLocation } from 'react-router-dom'
import { MessageSquare, X, CheckCircle2 } from 'lucide-react'
import { useAuthStore } from '../../store/authStore'
import { useToast } from '../ui/Toast'
import { feedbackApi } from '../../api/feedbackApi'
import {
  buildFeedbackPayload,
  describeFeedbackError,
  FEEDBACK_CATEGORIES,
  isWorkspacePath,
  MESSAGE_MAX,
  pathOnly,
  SUBJECT_MAX,
  validateFeedback,
  widgetVisibleOn,
} from '../../utils/feedbackFlow'

// Anything that takes over the screen or reports upload progress: the button steps
// aside while one of these is in the page (modals and the limit modals are
// aria-modal, the lightbox is aria-modal, the phone menu drawer is aria-modal; the
// upload progress list marks itself with data-hide-feedback-fab while a file is
// still uploading). The panel and the draft stay in memory and come back with it.
const BLOCKERS = '[aria-modal="true"], [role="alertdialog"], [data-hide-feedback-fab]'

const EMPTY_FORM = { category: '', subject: '', message: '' }

function useScreenBlocked() {
  const [blocked, setBlocked] = useState(false)
  useEffect(() => {
    let frame = 0
    const check = () => {
      frame = 0
      const next = Boolean(document.querySelector(BLOCKERS))
      setBlocked((current) => (current === next ? current : next))
    }
    const schedule = () => { if (!frame) frame = requestAnimationFrame(check) }
    check()
    const observer = new MutationObserver(schedule)
    observer.observe(document.body, {
      childList: true,
      subtree: true,
      attributes: true,
      attributeFilter: ['aria-modal', 'role', 'data-hide-feedback-fab'],
    })
    return () => {
      observer.disconnect()
      if (frame) cancelAnimationFrame(frame)
    }
  }, [])
  return blocked
}

const fieldClass = (invalid) =>
  `w-full rounded-lg border bg-white px-3 py-2 text-sm text-ink placeholder:text-muted/70 focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-green-500 ${
    invalid ? 'border-red-400' : 'border-cream-300'
  }`

function FeedbackWidgetInner() {
  const location = useLocation()
  const toast = useToast()
  const panelId = useId()
  const titleId = useId()
  const fabRef = useRef(null)
  const firstFieldRef = useRef(null)
  const messageRef = useRef(null)
  const sentHeadingRef = useRef(null)
  const isMountedRef = useRef(true)
  const openRef = useRef(false)

  const [open, setOpen] = useState(false)
  const [form, setForm] = useState(EMPTY_FORM)
  const [phase, setPhase] = useState('idle') // idle | sending | sent
  const [error, setError] = useState('')
  const [fieldErrors, setFieldErrors] = useState({})
  const blocked = useScreenBlocked()

  useEffect(() => {
    isMountedRef.current = true
    return () => { isMountedRef.current = false }
  }, [])
  useEffect(() => { openRef.current = open }, [open])

  const workspace = isWorkspacePath(location.pathname)
  const showing = !blocked

  const close = useCallback(() => {
    setOpen(false)
    // Focus goes back to the button that opened the panel.
    requestAnimationFrame(() => fabRef.current?.focus())
  }, [])

  const openPanel = () => {
    if (phase === 'sent') setPhase('idle')
    setOpen(true)
  }

  // Focus: first field on open (or the confirmation once sent).
  useEffect(() => {
    if (!open || !showing) return
    const frame = requestAnimationFrame(() => {
      if (phase === 'sent') sentHeadingRef.current?.focus()
      else firstFieldRef.current?.focus()
    })
    return () => cancelAnimationFrame(frame)
  }, [open, showing, phase === 'sent']) // eslint-disable-line react-hooks/exhaustive-deps

  // Escape closes the panel from anywhere on the page.
  useEffect(() => {
    if (!open || !showing) return undefined
    const onKeyDown = (event) => {
      if (event.key === 'Escape' && !event.defaultPrevented) close()
    }
    document.addEventListener('keydown', onKeyDown)
    return () => document.removeEventListener('keydown', onKeyDown)
  }, [open, showing, close])

  const update = (name) => (event) => {
    const value = event.target.value
    setForm((current) => ({ ...current, [name]: value }))
    if (fieldErrors[name]) setFieldErrors((current) => ({ ...current, [name]: undefined }))
  }

  const handleSubmit = async (event) => {
    event.preventDefault()
    if (phase === 'sending') return
    const problems = validateFeedback(form)
    setFieldErrors(problems)
    if (Object.keys(problems).length) {
      setError('')
      const target = problems.category ? firstFieldRef.current : problems.subject ? null : messageRef.current
      target?.focus()
      return
    }
    setPhase('sending')
    setError('')
    try {
      await feedbackApi.submit(buildFeedbackPayload(form, location.pathname))
      if (!isMountedRef.current) return
      setForm(EMPTY_FORM)
      setFieldErrors({})
      setPhase('sent')
      // A panel the person already closed gets a toast instead (only after the API said yes).
      if (!openRef.current) toast('Feedback sent. Thank you!', 'success')
    } catch (err) {
      if (!isMountedRef.current) return
      const failure = describeFeedbackError(err, 'submit')
      setPhase('idle')
      setFieldErrors(failure.fieldErrors)
      setError(failure.message || 'Could not send your feedback. Please try again.')
      if (!openRef.current) toast(failure.message || 'Could not send your feedback.', 'error')
      // The typed text stays in `form`: nothing is cleared on failure.
    }
  }

  if (!showing) return null

  const fabBottom = workspace
    ? 'bottom-[calc(7.75rem+env(safe-area-inset-bottom))]'
    : 'bottom-[calc(1rem+env(safe-area-inset-bottom))]'
  const panelBottom = workspace
    ? 'bottom-[calc(11rem+env(safe-area-inset-bottom))]'
    : 'bottom-[calc(4.75rem+env(safe-area-inset-bottom))]'
  const panelMaxHeight = workspace ? 'max-h-[calc(100dvh-14rem)]' : 'max-h-[calc(100dvh-8rem)]'
  const sending = phase === 'sending'

  return (
    <>
      <button
        ref={fabRef}
        type="button"
        onClick={() => (open ? close() : openPanel())}
        aria-label="Send feedback"
        aria-haspopup="dialog"
        aria-expanded={open}
        aria-controls={open ? panelId : undefined}
        data-testid="feedback-fab"
        className={`fixed right-4 z-40 flex h-11 w-11 cursor-pointer items-center justify-center rounded-full bg-brand-green-600 text-white shadow-lg transition-colors hover:bg-brand-green-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-green-500 focus-visible:ring-offset-2 md:bottom-6 md:right-6 ${fabBottom}`}
      >
        <MessageSquare className="h-5 w-5" aria-hidden="true" />
      </button>

      {open && (
        <div
          id={panelId}
          role="dialog"
          aria-modal="false"
          aria-labelledby={titleId}
          data-testid="feedback-panel"
          className={`fixed inset-x-3 z-[45] overflow-y-auto rounded-2xl border border-cream-200 bg-surface-light p-4 shadow-2xl md:inset-x-auto md:bottom-[5.25rem] md:right-6 md:w-[24rem] ${panelBottom} ${panelMaxHeight}`}
        >
          <div className="mb-3 flex items-start justify-between gap-3">
            <h2 id={titleId} ref={sentHeadingRef} tabIndex={-1} className="font-serif text-lg text-ink focus:outline-none">
              {phase === 'sent' ? 'Feedback sent' : 'Send feedback'}
            </h2>
            <button
              type="button"
              onClick={close}
              aria-label="Close feedback form"
              className="-mr-1 -mt-1 cursor-pointer rounded-lg p-1.5 text-muted transition-colors hover:bg-cream-100 hover:text-ink focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-green-500"
            >
              <X className="h-4 w-4" aria-hidden="true" />
            </button>
          </div>

          {phase === 'sent' ? (
            <div role="status" className="space-y-4">
              <p className="flex items-start gap-2 text-sm text-ink">
                <CheckCircle2 className="mt-0.5 h-4 w-4 flex-shrink-0 text-brand-green-600" aria-hidden="true" />
                Thank you. The KYAPTURE team received your message.
              </p>
              <button
                type="button"
                onClick={close}
                className="w-full cursor-pointer rounded-lg bg-brand-green-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-brand-green-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-green-500 focus-visible:ring-offset-2"
              >
                Done
              </button>
            </div>
          ) : (
            <form onSubmit={handleSubmit} noValidate className="space-y-3">
              {error && (
                <p role="alert" className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-800">
                  {error}
                </p>
              )}

              <div>
                <label htmlFor={`${panelId}-category`} className="mb-1 block text-xs font-medium text-ink">
                  Category <span className="text-red-600" aria-hidden="true">*</span>
                </label>
                <select
                  id={`${panelId}-category`}
                  ref={firstFieldRef}
                  value={form.category}
                  onChange={update('category')}
                  required
                  aria-required="true"
                  aria-invalid={Boolean(fieldErrors.category)}
                  aria-describedby={fieldErrors.category ? `${panelId}-category-error` : undefined}
                  className={fieldClass(fieldErrors.category)}
                >
                  <option value="">Choose a category…</option>
                  {FEEDBACK_CATEGORIES.map((c) => (
                    <option key={c.value} value={c.value}>{c.label}</option>
                  ))}
                </select>
                {fieldErrors.category && (
                  <p id={`${panelId}-category-error`} className="mt-1 text-xs text-red-700">{fieldErrors.category}</p>
                )}
              </div>

              <div>
                <label htmlFor={`${panelId}-subject`} className="mb-1 block text-xs font-medium text-ink">
                  Subject <span className="font-normal text-muted">(optional)</span>
                </label>
                <input
                  id={`${panelId}-subject`}
                  type="text"
                  value={form.subject}
                  onChange={update('subject')}
                  maxLength={SUBJECT_MAX}
                  autoComplete="off"
                  aria-invalid={Boolean(fieldErrors.subject)}
                  aria-describedby={fieldErrors.subject ? `${panelId}-subject-error` : undefined}
                  className={fieldClass(fieldErrors.subject)}
                />
                {fieldErrors.subject && (
                  <p id={`${panelId}-subject-error`} className="mt-1 text-xs text-red-700">{fieldErrors.subject}</p>
                )}
              </div>

              <div>
                <label htmlFor={`${panelId}-message`} className="mb-1 block text-xs font-medium text-ink">
                  Message <span className="text-red-600" aria-hidden="true">*</span>
                </label>
                <textarea
                  id={`${panelId}-message`}
                  ref={messageRef}
                  value={form.message}
                  onChange={update('message')}
                  maxLength={MESSAGE_MAX}
                  rows={5}
                  required
                  aria-required="true"
                  aria-invalid={Boolean(fieldErrors.message)}
                  aria-describedby={`${panelId}-message-hint${fieldErrors.message ? ` ${panelId}-message-error` : ''}`}
                  placeholder="What happened, or what would you like to see?"
                  className={`${fieldClass(fieldErrors.message)} resize-y`}
                />
                <div className="mt-1 flex items-start justify-between gap-3">
                  {fieldErrors.message ? (
                    <p id={`${panelId}-message-error`} className="text-xs text-red-700">{fieldErrors.message}</p>
                  ) : <span />}
                  <span id={`${panelId}-message-hint`} className="flex-shrink-0 text-[11px] text-muted">
                    {form.message.length}/{MESSAGE_MAX}
                  </span>
                </div>
              </div>

              <p className="text-[11px] leading-snug text-muted">
                We attach the page you are on ({pathOnly(location.pathname) || '/'}) and the app version. No files or screenshots are sent.
              </p>

              <div className="flex justify-end gap-2 pt-1">
                <button
                  type="button"
                  onClick={close}
                  className="cursor-pointer rounded-lg px-3 py-2 text-sm text-muted transition-colors hover:bg-cream-100 hover:text-ink focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-green-500"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={sending}
                  aria-busy={sending}
                  className="cursor-pointer rounded-lg bg-brand-green-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-brand-green-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-green-500 focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-60"
                >
                  {sending ? 'Sending…' : 'Send'}
                </button>
              </div>
            </form>
          )}
        </div>
      )}
    </>
  )
}

/**
 * The floating "Send feedback" button and its panel. It exists ONLY for a signed-in
 * photographer on /dashboard/* (the dashboard and the gallery workspace) and never
 * on public client-gallery, download, login, register or landing routes. The inner
 * widget is keyed by user id and unmounted off the dashboard, so a draft never
 * survives a sign-out or a different account.
 */
export default function FeedbackWidget() {
  const { pathname } = useLocation()
  const user = useAuthStore((s) => s.user)
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated)
  const loading = useAuthStore((s) => s.loading)

  if (loading || !isAuthenticated || !user || !widgetVisibleOn(pathname)) return null
  return <FeedbackWidgetInner key={user.id} />
}
