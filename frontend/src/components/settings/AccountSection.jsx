// File Location: frontend/src/components/settings/AccountSection.jsx
import { Link, useNavigate } from 'react-router-dom'
import { useAuthStore } from '../../store/authStore'
import { useSubscription } from '../../hooks/useSubscription'
import Button from '../ui/Button'
import { formatDate } from '../../utils/formatters'
import { Card, ReadOnlyRow } from './SettingsUI'

/**
 * Account: the identity and standing of the signed-in account, from real data
 * only (the profile from /auth/me/, the plan from /subscriptions/my-subscription/).
 * No control here changes anything it can't actually change: the email is
 * display-only (there is no verified email-change flow), and account deletion
 * is shown as unavailable rather than faked — a destructive action that
 * removes a photographer's galleries and files must be enforced and
 * confirmed server-side, which does not exist yet.
 */
export default function AccountSection() {
  const navigate = useNavigate()
  const user = useAuthStore((s) => s.user)
  const logout = useAuthStore((s) => s.logout)
  const { subscription, plan, loading } = useSubscription()

  const planLabel = loading
    ? 'Loading…'
    : plan?.name && subscription?.status === 'active'
      ? `${plan.name} (active)`
      : plan?.name
        ? `${plan.name} (${subscription?.status || 'inactive'})`
        : 'Free'

  const handleSignOut = async () => {
    await logout()
    navigate('/login', { replace: true })
  }

  return (
    <div className="space-y-6">
      <Card title="Account" description="Your sign-in identity and account standing.">
        <dl>
          <ReadOnlyRow label="Email" value={user?.email} hint="Used to sign in. Changing it isn't supported yet." />
          <ReadOnlyRow label="Username" value={user?.username} />
          <ReadOnlyRow label="Display name" value={user?.display_name || '—'} />
          <ReadOnlyRow label="Account status" value="Active" />
          <ReadOnlyRow label="Plan" value={planLabel} />
          <ReadOnlyRow label="Member since" value={user?.created_at ? formatDate(user.created_at) : '—'} />
        </dl>
        <p className="mt-4 text-xs text-muted">
          Edit your name, username and picture in <Link to="/dashboard/settings/profile" className="font-medium text-ink underline underline-offset-2">Profile</Link>;
          manage your plan in <Link to="/dashboard/settings/plan-billing" className="font-medium text-ink underline underline-offset-2">Plan &amp; Billing</Link>.
        </p>
      </Card>

      <Card title="Sign out" description="End your session on this device. To end sessions on every device, use Security.">
        <Button variant="secondary" onClick={handleSignOut}>Sign out</Button>
      </Card>

      <Card title="Delete account">
        <p className="text-sm text-ink">Account deletion isn't available in the app yet.</p>
        <p className="mt-1 text-xs leading-relaxed text-muted">
          Deleting an account permanently removes its collections and files, so it needs a confirmed, server-enforced
          flow that doesn't exist yet. Nothing on this page can delete your account.
        </p>
      </Card>
    </div>
  )
}
