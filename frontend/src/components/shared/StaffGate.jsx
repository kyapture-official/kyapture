// File Location: frontend/src/components/shared/StaffGate.jsx
import { Link } from 'react-router-dom'
import { useAuthStore } from '../../store/authStore'

/**
 * Presentation only: shows the page to staff accounts (user.is_staff from /auth/me/) and a short
 * "staff only" note to everyone else, without making a single request. The server is the
 * authority: every staff endpoint answers 403 to anyone who is not staff.
 */
export default function StaffGate({ area, children }) {
  const isStaff = useAuthStore((s) => s.user?.is_staff === true)
  if (isStaff) return children
  return (
    <div className="mx-auto max-w-xl py-16 text-center" data-testid="staff-denied">
      <h2 className="font-serif text-2xl text-ink">Staff only</h2>
      <p className="mt-2 text-sm text-muted">{area} is only available to KYAPTURE staff accounts.</p>
      <Link
        to="/dashboard"
        className="mt-5 inline-block rounded-lg bg-brand-green-600 px-4 py-2 text-sm font-medium text-white hover:bg-brand-green-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-green-500 focus-visible:ring-offset-2"
      >
        Back to overview
      </Link>
    </div>
  )
}
