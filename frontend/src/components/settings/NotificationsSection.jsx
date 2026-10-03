// File Location: frontend/src/components/settings/NotificationsSection.jsx
import { useState } from 'react'
import { useAuthStore } from '../../store/authStore'
import { useToast } from '../ui/Toast'
import { Card, ErrorBlock, InlineStatus, LoadingBlock, Switch } from './SettingsUI'
import { useUserSettings } from './useUserSettings'

/**
 * Only alerts that are actually sent are listed. Each one maps to a real send
 * path on the backend (apps/users/notifications.py); there are no toggles for
 * anything the system can't deliver.
 */
const ALERTS = [
  {
    key: 'downloads',
    label: 'Download alerts',
    description:
      'Email me when a client downloads from one of my collections. At most one email per collection every 15 minutes.',
  },
  {
    key: 'favorites',
    label: 'Favorite alerts',
    description:
      'Email me when a client favorites a photo. At most one email per collection every 15 minutes.',
  },
  {
    key: 'payments',
    label: 'Payment alerts',
    description: 'Email me when a payment I submitted is approved or rejected.',
  },
]

export default function NotificationsSection() {
  const toast = useToast()
  const email = useAuthStore((s) => s.user?.email)
  const { settings, loading, loadError, reload, save } = useUserSettings()
  const [busyKey, setBusyKey] = useState(null)
  const [status, setStatus] = useState(null)

  const handleToggle = (key) => async (checked) => {
    if (busyKey) return
    setBusyKey(key)
    setStatus(null)
    try {
      // The switch re-renders from the server's answer, not from the click.
      const saved = await save({ notifications: { [key]: checked } })
      const label = ALERTS.find((a) => a.key === key).label
      setStatus({ kind: 'success', message: `${label} ${saved.notifications[key] ? 'turned on' : 'turned off'}.` })
      toast('Notification preference saved', 'success')
    } catch (err) {
      setStatus({ kind: 'error', message: err.message || 'Could not save that preference.' })
    } finally {
      setBusyKey(null)
    }
  }

  return (
    <Card
      title="Email notifications"
      description={email ? `Alerts are sent to ${email}.` : 'Alerts are sent to your account email.'}
    >
      {loading ? (
        <LoadingBlock label="Loading your preferences…" />
      ) : loadError ? (
        <ErrorBlock message={loadError} onRetry={reload} />
      ) : (
        <div className="space-y-3">
          {ALERTS.map((alert) => (
            <Switch
              key={alert.key}
              id={`notify-${alert.key}`}
              label={alert.label}
              description={alert.description}
              checked={Boolean(settings.notifications[alert.key])}
              busy={busyKey === alert.key}
              disabled={busyKey !== null}
              onChange={handleToggle(alert.key)}
            />
          ))}
          <InlineStatus status={status} />
        </div>
      )}
    </Card>
  )
}
