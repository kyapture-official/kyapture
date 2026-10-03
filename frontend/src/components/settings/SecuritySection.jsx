// File Location: frontend/src/components/settings/SecuritySection.jsx
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { authApi } from '../../api/authApi'
import { useAuthStore } from '../../store/authStore'
import { useToast } from '../ui/Toast'
import Input from '../ui/Input'
import Button from '../ui/Button'
import { parseApiError } from '../../utils/apiErrors'
import { Card, InlineStatus } from './SettingsUI'

const EMPTY = { old_password: '', new_password: '', new_password2: '' }

export default function SecuritySection() {
  const navigate = useNavigate()
  const toast = useToast()

  const [form, setForm] = useState(EMPTY)
  const [errors, setErrors] = useState({})
  const [status, setStatus] = useState(null)
  const [saving, setSaving] = useState(false)

  const [confirmingSignOut, setConfirmingSignOut] = useState(false)
  const [signingOut, setSigningOut] = useState(false)
  const [signOutError, setSignOutError] = useState('')

  const setField = (key) => (event) => {
    setForm((prev) => ({ ...prev, [key]: event.target.value }))
    setErrors((prev) => ({ ...prev, [key]: undefined }))
    setStatus(null)
  }

  const handleChangePassword = async (event) => {
    event.preventDefault()
    if (saving) return

    const next = {}
    if (!form.old_password) next.old_password = 'Enter your current password.'
    if (!form.new_password) next.new_password = 'Enter a new password.'
    else if (form.new_password.length < 8) next.new_password = 'Use at least 8 characters.'
    if (!form.new_password2) next.new_password2 = 'Confirm your new password.'
    else if (form.new_password !== form.new_password2) next.new_password2 = 'The two new passwords do not match.'
    if (Object.keys(next).length) { setErrors(next); return }

    setSaving(true)
    setStatus(null)
    try {
      await authApi.changePassword(form)
      setForm(EMPTY)
      setErrors({})
      setStatus({
        kind: 'success',
        message: 'Password changed. You stay signed in here; every other device has been signed out.',
      })
      toast('Password changed', 'success')
    } catch (err) {
      const parsed = parseApiError(err, 'Could not change your password.')
      setErrors(parsed.fieldErrors)
      setStatus({ kind: 'error', message: parsed.message || 'Please fix the highlighted fields.' })
    } finally {
      setSaving(false)
    }
  }

  const handleSignOutEverywhere = async () => {
    if (signingOut) return
    setSigningOut(true)
    setSignOutError('')
    try {
      // Real server-side revocation: every refresh token for the account is
      // blacklisted. Only after the server confirms is the local session dropped.
      await authApi.logoutAll()
      useAuthStore.setState({ user: null, isAuthenticated: false, loading: false })
      navigate('/login', { replace: true })
    } catch (err) {
      setSignOutError(parseApiError(err, 'Could not sign out of all sessions. Please try again.').message)
      setSigningOut(false)
    }
  }

  return (
    <div className="space-y-6">
      <Card title="Change password" description="Choose a strong password you don't use anywhere else.">
        <form onSubmit={handleChangePassword} noValidate className="space-y-4">
          <Input
            label="Current password"
            type="password"
            name="old_password"
            autoComplete="current-password"
            value={form.old_password}
            onChange={setField('old_password')}
            error={errors.old_password}
          />
          <Input
            label="New password"
            type="password"
            name="new_password"
            autoComplete="new-password"
            value={form.new_password}
            onChange={setField('new_password')}
            error={errors.new_password}
            hint="At least 8 characters. Not too common, not only numbers, not similar to your username or email."
          />
          <Input
            label="Confirm new password"
            type="password"
            name="new_password2"
            autoComplete="new-password"
            value={form.new_password2}
            onChange={setField('new_password2')}
            error={errors.new_password2}
          />
          <InlineStatus status={status} />
          <div className="flex justify-end border-t border-cream-200 pt-4">
            <Button type="submit" loading={saving}>{saving ? 'Changing…' : 'Change password'}</Button>
          </div>
        </form>
      </Card>

      <Card
        title="Sessions"
        description="Sign out everywhere if you've used a shared computer or think someone else has access."
      >
        {!confirmingSignOut ? (
          <Button variant="secondary" onClick={() => setConfirmingSignOut(true)}>Sign out of all sessions</Button>
        ) : (
          <div role="alertdialog" aria-labelledby="signout-all-title" className="rounded-xl border border-amber-200 bg-amber-50 p-4">
            <p id="signout-all-title" className="text-sm font-semibold text-amber-900">Sign out of every device, including this one?</p>
            <p className="mt-1 text-xs leading-relaxed text-amber-800">
              All sessions are revoked on the server and you'll need to sign in again. A device that was already
              signed in may keep working for up to 15 minutes until its short-lived access pass expires.
            </p>
            {signOutError && <p role="alert" className="mt-3 text-xs text-red-700">{signOutError}</p>}
            <div className="mt-4 flex flex-wrap gap-2">
              <Button variant="danger" size="sm" loading={signingOut} onClick={handleSignOutEverywhere}>
                {signingOut ? 'Signing out…' : 'Yes, sign out everywhere'}
              </Button>
              <Button variant="ghost" size="sm" disabled={signingOut} onClick={() => { setConfirmingSignOut(false); setSignOutError('') }}>
                Cancel
              </Button>
            </div>
          </div>
        )}
      </Card>
    </div>
  )
}
