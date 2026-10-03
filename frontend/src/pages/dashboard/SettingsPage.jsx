// C:/Users/LENOVO/Desktop/kyapture/frontend/src/pages/dashboard/SettingsPage.jsx
import { Navigate, NavLink, useParams } from 'react-router-dom'
import ProfileSection from '../../components/settings/ProfileSection'
import AccountSection from '../../components/settings/AccountSection'
import SecuritySection from '../../components/settings/SecuritySection'
import BrandingSection from '../../components/settings/BrandingSection'
import NotificationsSection from '../../components/settings/NotificationsSection'
import PlanBillingSection from '../../components/settings/PlanBillingSection'
import CollectionDefaultsSection from '../../components/settings/CollectionDefaultsSection'
import PrivacySection from '../../components/settings/PrivacySection'

/**
 * The Settings structure. Each section is its own URL
 * (/dashboard/settings/<id>), so a refresh, a shared link and the browser's
 * back button all land on the same section. Every section is backed by real
 * persistence — see the section components for what each one saves and where.
 */
const SECTIONS = [
  { id: 'profile', label: 'Profile', Component: ProfileSection },
  { id: 'account', label: 'Account', Component: AccountSection },
  { id: 'security', label: 'Security', Component: SecuritySection },
  { id: 'branding', label: 'Branding', Component: BrandingSection },
  { id: 'notifications', label: 'Notifications', Component: NotificationsSection },
  { id: 'plan-billing', label: 'Plan & Billing', Component: PlanBillingSection },
  { id: 'collection-defaults', label: 'Collection Defaults', Component: CollectionDefaultsSection },
  { id: 'privacy', label: 'Privacy', Component: PrivacySection },
]

const linkClass = ({ isActive }) =>
  `block whitespace-nowrap rounded-lg px-3.5 py-2.5 text-sm transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-green-500 ${
    isActive ? 'bg-surface-light font-medium text-ink shadow-sm' : 'text-muted hover:bg-cream-100 hover:text-ink'
  }`

export default function SettingsPage() {
  const { section } = useParams()
  const active = SECTIONS.find((s) => s.id === section)

  if (!active) return <Navigate to="/dashboard/settings/profile" replace />
  const { Component } = active

  return (
    <div className="mx-auto max-w-5xl animate-fade-up">
      <div className="mb-6">
        <h1 className="mb-1 font-serif text-3xl text-ink md:text-4xl">Settings</h1>
        <p className="text-sm text-muted">Manage your profile, account, notifications and collection defaults.</p>
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-[220px_minmax(0,1fr)] lg:gap-8">
        {/* Section navigation: a tab strip on small screens, a sticky list on desktop */}
        <nav aria-label="Settings sections" className="lg:sticky lg:top-6 lg:self-start">
          <ul className="-mx-4 flex gap-1 overflow-x-auto rounded-xl bg-cream-100 p-1 px-4 sm:mx-0 sm:px-1 lg:mx-0 lg:flex-col lg:overflow-visible lg:bg-transparent lg:p-0">
            {SECTIONS.map(({ id, label }) => (
              <li key={id} className="flex-none lg:flex-auto">
                <NavLink to={`/dashboard/settings/${id}`} className={linkClass}>
                  {label}
                </NavLink>
              </li>
            ))}
          </ul>
        </nav>

        <div className="min-w-0">
          <Component />
        </div>
      </div>
    </div>
  )
}
