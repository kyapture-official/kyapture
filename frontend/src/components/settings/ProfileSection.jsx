// File Location: frontend/src/components/settings/ProfileSection.jsx
import { useRef, useState } from 'react'
import { authApi } from '../../api/authApi'
import { useAuthStore } from '../../store/authStore'
import { useToast } from '../ui/Toast'
import Input from '../ui/Input'
import Button from '../ui/Button'
import Spinner from '../ui/Spinner'
import { parseApiError } from '../../utils/apiErrors'
import { Card, InlineStatus } from './SettingsUI'

const FIELDS = ['display_name', 'username', 'bio', 'phone', 'website']
const MAX_AVATAR_BYTES = 2 * 1024 * 1024

const fromUser = (user) => ({
  display_name: user?.display_name || '',
  username: user?.username || '',
  bio: user?.bio || '',
  phone: user?.phone || '',
  website: user?.website || '',
})

export default function ProfileSection() {
  const toast = useToast()
  const user = useAuthStore((s) => s.user)
  const updateUser = useAuthStore((s) => s.updateUser)
  const fileInputRef = useRef(null)

  const [form, setForm] = useState(() => fromUser(user))
  const [errors, setErrors] = useState({})
  const [status, setStatus] = useState(null)
  const [saving, setSaving] = useState(false)
  const [avatarBusy, setAvatarBusy] = useState(false)
  const [avatarStatus, setAvatarStatus] = useState(null)

  const saved = fromUser(user)
  const dirty = FIELDS.some((key) => form[key].trim() !== saved[key].trim())
  const usernameChanged = form.username.trim().toLowerCase() !== saved.username
  const initial = (user?.display_name || user?.username || '?').charAt(0).toUpperCase()

  const setField = (key) => (event) => {
    setForm((prev) => ({ ...prev, [key]: event.target.value }))
    setErrors((prev) => ({ ...prev, [key]: undefined }))
    setStatus(null)
  }

  const handleSave = async (event) => {
    event.preventDefault()
    if (!dirty || saving) return

    const next = {}
    if (!form.display_name.trim()) next.display_name = 'Display name is required.'
    if (!form.username.trim()) next.username = 'Username is required.'
    if (Object.keys(next).length) { setErrors(next); return }

    if (usernameChanged && !window.confirm(
      `Change your username from "${saved.username}" to "${form.username.trim().toLowerCase()}"?\n\n` +
      'Your public links will change with it — every gallery link you have already shared will stop working.',
    )) return

    // Send only what changed: an untouched field is never re-submitted.
    const payload = {}
    for (const key of FIELDS) {
      if (form[key].trim() !== saved[key].trim()) {
        payload[key] = key === 'username' ? form[key].trim().toLowerCase() : form[key].trim()
      }
    }

    setSaving(true)
    setStatus(null)
    try {
      const updated = await authApi.updateMe(payload)
      updateUser(updated)
      setForm(fromUser(updated))
      setErrors({})
      setStatus({ kind: 'success', message: 'Profile saved.' })
      toast('Profile saved', 'success')
    } catch (err) {
      const parsed = parseApiError(err, 'Could not save your profile.')
      setErrors(parsed.fieldErrors)
      setStatus({ kind: 'error', message: parsed.message || 'Please fix the highlighted fields.' })
    } finally {
      setSaving(false)
    }
  }

  const handleAvatarChosen = async (event) => {
    const file = event.target.files?.[0]
    event.target.value = ''
    if (!file) return
    if (file.size > MAX_AVATAR_BYTES) {
      setAvatarStatus({ kind: 'error', message: 'Profile picture exceeds the 2MB size limit.' })
      return
    }
    setAvatarBusy(true)
    setAvatarStatus(null)
    try {
      const body = new FormData()
      body.append('avatar', file)
      const updated = await authApi.updateMe(body)
      updateUser(updated)
      setAvatarStatus({ kind: 'success', message: 'Profile picture updated.' })
    } catch (err) {
      const parsed = parseApiError(err, 'Could not upload your profile picture.')
      setAvatarStatus({ kind: 'error', message: parsed.fieldErrors.avatar || parsed.message })
    } finally {
      setAvatarBusy(false)
    }
  }

  const handleAvatarRemove = async () => {
    if (avatarBusy) return
    setAvatarBusy(true)
    setAvatarStatus(null)
    try {
      const updated = await authApi.updateMe({ avatar: null })
      updateUser(updated)
      setAvatarStatus({ kind: 'success', message: 'Profile picture removed.' })
    } catch (err) {
      setAvatarStatus({ kind: 'error', message: parseApiError(err, 'Could not remove your profile picture.').message })
    } finally {
      setAvatarBusy(false)
    }
  }

  return (
    <div className="space-y-6">
      <Card title="Profile picture" description="Shown on your public portfolio page. PNG, JPG or WEBP, up to 2MB.">
        <div className="flex flex-wrap items-center gap-5">
          <div className="relative flex h-20 w-20 flex-shrink-0 items-center justify-center overflow-hidden rounded-full border border-cream-200 bg-cream-100">
            {user?.avatar ? (
              <img src={user.avatar} alt="Your profile picture" className="h-full w-full object-cover" />
            ) : (
              <span aria-hidden="true" className="font-serif text-3xl text-muted">{initial}</span>
            )}
            {avatarBusy && (
              <div className="absolute inset-0 flex items-center justify-center bg-white/80"><Spinner /></div>
            )}
          </div>
          <div className="flex flex-wrap gap-2">
            <Button variant="secondary" size="sm" onClick={() => fileInputRef.current?.click()} disabled={avatarBusy}>
              {user?.avatar ? 'Replace picture' : 'Upload picture'}
            </Button>
            {user?.avatar && (
              <Button variant="ghost" size="sm" onClick={handleAvatarRemove} disabled={avatarBusy}>
                Remove
              </Button>
            )}
            <input
              ref={fileInputRef}
              type="file"
              accept="image/png, image/jpeg, image/webp"
              onChange={handleAvatarChosen}
              className="hidden"
              aria-label="Choose a profile picture"
            />
          </div>
        </div>
        {avatarStatus && <div className="mt-4"><InlineStatus status={avatarStatus} /></div>}
      </Card>

      <Card title="Profile" description="How you appear to your clients.">
        <form onSubmit={handleSave} noValidate className="space-y-5">
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <Input
              label="Display name"
              name="display_name"
              value={form.display_name}
              onChange={setField('display_name')}
              error={errors.display_name}
              maxLength={100}
              hint="Shown to clients as your studio or business name."
              autoComplete="organization"
              required
            />
            <Input
              label="Username"
              name="username"
              value={form.username}
              onChange={setField('username')}
              error={errors.username}
              maxLength={50}
              autoCapitalize="none"
              spellCheck={false}
              hint={`Your gallery links look like /g/${form.username.trim().toLowerCase() || 'username'}/…`}
              required
            />
          </div>

          {usernameChanged && (
            <div role="alert" className="rounded-xl border border-amber-200 bg-amber-50 p-4 text-xs leading-relaxed text-amber-800">
              <p className="font-semibold text-amber-900">Changing your username changes your public links.</p>
              <p className="mt-1">
                Gallery links you've already shared use <strong>{saved.username}</strong> and will stop working. Your
                collections themselves, and their individual addresses, are not changed.
              </p>
            </div>
          )}

          <Input
            label="Email"
            name="email"
            type="email"
            value={user?.email || ''}
            disabled
            readOnly
            hint="Your email is your sign-in identity and can't be changed here yet."
          />

          <div className="flex flex-col gap-1.5">
            <label htmlFor="profile-bio" className="text-sm font-medium text-ink/80">Biography</label>
            <textarea
              id="profile-bio"
              name="bio"
              rows={4}
              value={form.bio}
              onChange={setField('bio')}
              aria-invalid={errors.bio ? true : undefined}
              placeholder="Tell your clients about yourself…"
              className="w-full resize-none rounded-xl border border-cream-200 bg-cream-100/20 px-4 py-2.5 text-sm text-ink placeholder:text-muted focus:border-brand-green-500 focus:outline-none focus:ring-2 focus:ring-brand-green-500/10"
            />
            {errors.bio && <p role="alert" className="text-xs text-red-600">{errors.bio}</p>}
          </div>

          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <Input
              label="Phone"
              name="phone"
              value={form.phone}
              onChange={setField('phone')}
              error={errors.phone}
              maxLength={20}
              inputMode="tel"
              autoComplete="tel"
              placeholder="Optional"
            />
            <Input
              label="Website"
              name="website"
              type="url"
              value={form.website}
              onChange={setField('website')}
              error={errors.website}
              autoComplete="url"
              placeholder="https://"
            />
          </div>

          <InlineStatus status={status} />

          <div className="flex justify-end border-t border-cream-200 pt-4">
            <Button type="submit" loading={saving} disabled={!dirty}>
              {saving ? 'Saving…' : 'Save profile'}
            </Button>
          </div>
        </form>
      </Card>
    </div>
  )
}
