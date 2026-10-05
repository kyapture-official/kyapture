// File Location: frontend/src/components/settings/BrandingSection.jsx
import { useState } from 'react'
import { authApi } from '../../api/authApi'
import { useAuthStore } from '../../store/authStore'
import { useSubscription } from '../../hooks/useSubscription'
import { useToast } from '../ui/Toast'
import Button from '../ui/Button'
import Spinner from '../ui/Spinner'
import UpgradePrompt from '../shared/UpgradePrompt'
import { parseApiError } from '../../utils/apiErrors'
import { Card, InlineStatus } from './SettingsUI'

const HEX = /^#[0-9a-fA-F]{6}$/

/**
 * Branding — the business logo (Pro+) and the brand colour. This is the Task 2
 * branding implementation, relocated into the Settings structure unchanged in
 * behaviour: the server decides and enforces the plan check, and the locked
 * state below only explains the API's refusal.
 */
export default function BrandingSection() {
  const toast = useToast()
  const user = useAuthStore((s) => s.user)
  const updateUser = useAuthStore((s) => s.updateUser)
  const { entitlements, loading: planLoading } = useSubscription()
  const brandingLocked = !planLoading && !entitlements.branding

  const logoURL = user?.logo || null
  const [logoBusy, setLogoBusy] = useState(false)
  const [logoStatus, setLogoStatus] = useState(null)

  const savedColor = user?.branding_color || '#111827'
  const [color, setColor] = useState(savedColor)
  const [colorSaving, setColorSaving] = useState(false)
  const [colorStatus, setColorStatus] = useState(null)
  const colorDirty = color.toLowerCase() !== savedColor.toLowerCase()

  const handleLogoUpload = async (event) => {
    const file = event.target.files?.[0]
    // Reset so choosing the same file again (after a rejection) still fires onChange.
    event.target.value = ''
    if (!file) return

    if (!entitlements.branding) {
      setLogoStatus({ kind: 'error', message: 'Custom branding is not included in your plan. Upgrade to add your logo.' })
      return
    }
    if (file.size > 2 * 1024 * 1024) {
      setLogoStatus({ kind: 'error', message: 'Logo file exceeds the 2MB size limit.' })
      return
    }

    setLogoBusy(true)
    setLogoStatus(null)
    try {
      const body = new FormData()
      body.append('logo', file)
      const updated = await authApi.updateMe(body)
      updateUser(updated)
      setLogoStatus({ kind: 'success', message: 'Logo uploaded.' })
      toast('Logo uploaded', 'success')
    } catch (err) {
      const parsed = parseApiError(err, 'Logo upload failed.')
      setLogoStatus({
        kind: 'error',
        message:
          parsed.code === 'branding_requires_upgrade'
            ? parsed.message || 'Custom branding is not included in your plan.'
            : parsed.fieldErrors.logo || parsed.message,
      })
    } finally {
      setLogoBusy(false)
    }
  }

  const handleLogoRemove = async () => {
    if (logoBusy) return
    setLogoBusy(true)
    setLogoStatus(null)
    try {
      const updated = await authApi.updateMe({ logo: null })
      updateUser(updated)
      setLogoStatus({ kind: 'success', message: 'Logo removed.' })
      toast('Logo removed', 'success')
    } catch (err) {
      setLogoStatus({ kind: 'error', message: parseApiError(err, 'Failed to remove the logo.').message })
    } finally {
      setLogoBusy(false)
    }
  }

  const handleColorSave = async (event) => {
    event.preventDefault()
    if (!colorDirty || colorSaving) return
    if (!HEX.test(color)) {
      setColorStatus({ kind: 'error', message: 'Enter a valid hex colour, like #336699.' })
      return
    }
    setColorSaving(true)
    setColorStatus(null)
    try {
      const updated = await authApi.updateMe({ branding_color: color })
      updateUser(updated)
      setColor(updated.branding_color)
      setColorStatus({ kind: 'success', message: 'Brand colour saved.' })
      toast('Brand colour saved', 'success')
    } catch (err) {
      const parsed = parseApiError(err, 'Could not save your brand colour.')
      setColorStatus({ kind: 'error', message: parsed.fieldErrors.branding_color || parsed.message })
    } finally {
      setColorSaving(false)
    }
  }

  return (
    <div className="space-y-6">
      <Card title="Business logo" description="Appears at the top of your client galleries. PNG, JPG or WEBP, up to 2MB.">
        <div className="flex flex-col gap-5 sm:flex-row sm:items-start">
          <div className="relative flex h-32 w-32 flex-shrink-0 items-center justify-center overflow-hidden rounded-2xl border border-cream-200 bg-cream-100/20">
            {logoURL ? (
              <img src={logoURL} alt={user?.display_name || 'Your logo'} className="pointer-events-none h-full w-full select-none object-contain p-3" />
            ) : (
              <svg className="h-10 w-10 text-muted" fill="none" viewBox="0 0 24 24" stroke="currentColor" aria-hidden="true">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z" />
              </svg>
            )}
            {logoBusy && <div className="absolute inset-0 flex items-center justify-center bg-white/80"><Spinner /></div>}
          </div>

          <div className="min-w-0 flex-1 space-y-3">
            {brandingLocked ? (
              <UpgradePrompt
                feature="branding"
                message="Add your business logo to every client gallery."
              />
            ) : (
              <label className="inline-block cursor-pointer rounded-xl border border-cream-200 bg-surface-light px-4 py-2.5 text-center text-xs font-medium uppercase tracking-wide text-ink transition-all hover:border-cream-300 hover:bg-cream-100 focus-within:ring-2 focus-within:ring-brand-green-500">
                {logoURL ? 'Replace Logo' : 'Upload New Logo'}
                <input
                  type="file"
                  accept="image/png, image/jpeg, image/webp"
                  onChange={handleLogoUpload}
                  disabled={logoBusy || planLoading}
                  className="sr-only"
                />
              </label>
            )}

            {logoURL && (
              <div>
                <button
                  type="button"
                  onClick={handleLogoRemove}
                  disabled={logoBusy}
                  className="cursor-pointer rounded-xl border border-transparent px-3 py-2 text-xs font-semibold text-red-600 transition-colors hover:border-red-100 hover:bg-red-50 hover:text-red-700 disabled:opacity-50"
                >
                  Remove Logo
                </button>
              </div>
            )}
            <InlineStatus status={logoStatus} />
          </div>
        </div>
      </Card>

      <Card
        title="Brand colour"
        description="Your accent colour. It's the starting colour for each new collection you create, and tints your public pages."
      >
        <form onSubmit={handleColorSave} noValidate className="space-y-4">
          <div className="flex flex-wrap items-center gap-3">
            <input
              type="color"
              aria-label="Pick brand colour"
              value={HEX.test(color) ? color : '#111827'}
              onChange={(e) => { setColor(e.target.value); setColorStatus(null) }}
              disabled={colorSaving}
              className="h-10 w-10 cursor-pointer rounded-xl border border-cream-200 bg-transparent"
            />
            <input
              type="text"
              aria-label="Brand colour hex value"
              value={color}
              onChange={(e) => { setColor(e.target.value); setColorStatus(null) }}
              disabled={colorSaving}
              maxLength={7}
              spellCheck={false}
              className="w-28 rounded-xl border border-cream-200 bg-surface-light px-3 py-1.5 font-mono text-sm uppercase focus:border-brand-green-500 focus:outline-none"
            />
          </div>
          <InlineStatus status={colorStatus} />
          <div className="flex justify-end border-t border-cream-200 pt-4">
            <Button type="submit" loading={colorSaving} disabled={!colorDirty}>Save colour</Button>
          </div>
        </form>
      </Card>
    </div>
  )
}
