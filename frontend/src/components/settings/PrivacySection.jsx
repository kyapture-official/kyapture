// File Location: frontend/src/components/settings/PrivacySection.jsx
import { useState } from 'react'
import { useAuthStore } from '../../store/authStore'
import { useToast } from '../ui/Toast'
import { Card, ErrorBlock, InlineStatus, LoadingBlock, Switch } from './SettingsUI'
import { useUserSettings } from './useUserSettings'

/**
 * Privacy: the controls that exist today. The public portfolio page is the one
 * persisted, enforced profile-visibility setting. Everything else on this page
 * is a plain statement of how the app already behaves — not a toggle — because
 * nothing else about privacy is configurable yet.
 */
export default function PrivacySection() {
  const toast = useToast()
  const username = useAuthStore((s) => s.user?.username)
  const { settings, loading, loadError, reload, save } = useUserSettings()
  const [busy, setBusy] = useState(false)
  const [status, setStatus] = useState(null)

  const handleToggle = async (checked) => {
    if (busy) return
    setBusy(true)
    setStatus(null)
    try {
      const saved = await save({ privacy: { portfolio_public: checked } })
      setStatus({
        kind: 'success',
        message: saved.privacy.portfolio_public
          ? 'Your public portfolio page is visible.'
          : 'Your public portfolio page is hidden.',
      })
      toast('Privacy setting saved', 'success')
    } catch (err) {
      setStatus({ kind: 'error', message: err.message || 'Could not save that setting.' })
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="space-y-6">
      <Card title="Public portfolio" description="Control whether your portfolio page can be found at all.">
        {loading ? (
          <LoadingBlock label="Loading your privacy settings…" />
        ) : loadError ? (
          <ErrorBlock message={loadError} onRetry={reload} />
        ) : (
          <div className="space-y-3">
            <Switch
              id="privacy-portfolio"
              label="Show my public portfolio page"
              description={`/g/${username || 'username'} lists your published, non-password-protected collections. Turn it off and that page stops existing (it looks the same as a page that was never there). Direct links to individual collections you've shared keep working.`}
              checked={Boolean(settings.privacy.portfolio_public)}
              busy={busy}
              onChange={handleToggle}
            />
            <InlineStatus status={status} />
          </div>
        )}
      </Card>

      <Card title="How your data is handled" description="These aren't settings — they describe how the app already works.">
        <ul className="space-y-2 text-xs leading-relaxed text-muted">
          <li>Client emails collected when someone downloads are visible only to you, in each collection's Download Activity.</li>
          <li>Your original photo files are stored privately and are only handed out through a collection's download controls — and only when downloads are enabled for it.</li>
          <li>Password-protected collections never appear on your public portfolio.</li>
          <li>Whether a collection is published, password-protected or downloadable is set per collection.</li>
        </ul>
      </Card>
    </div>
  )
}
