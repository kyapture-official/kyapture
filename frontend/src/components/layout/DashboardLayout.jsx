import React, { useState } from 'react'
import { NavLink, useNavigate, useLocation, Outlet } from 'react-router-dom'
import { useAuthStore } from '../../store/authStore'

const NAV_ITEMS = [
  { to: '/dashboard',           label: 'Home',      icon: HomeIcon,     end: true },
  { to: '/dashboard/galleries', label: 'Galleries', icon: GalleriesIcon },
  { to: '/dashboard/upload',    label: 'Upload',    icon: UploadIcon },
  { to: '/dashboard/settings',  label: 'Settings',  icon: SettingsIcon },
  { to: '/dashboard/billing',   label: 'Billing',   icon: BillingIcon },
]

// Longest match wins (gallery detail resolves before /galleries)
const PAGE_TITLE_MAP = [
  { prefix: '/dashboard/galleries/',  title: 'Gallery Detail' },
  { prefix: '/dashboard/galleries',   title: 'Galleries' },
  { prefix: '/dashboard/upload',      title: 'Upload Photos' },
  { prefix: '/dashboard/settings',    title: 'Settings' },
  { prefix: '/dashboard/billing',     title: 'Billing' },
  { prefix: '/dashboard',             title: 'Dashboard' },
]

function resolvePageTitle(pathname) {
  for (const entry of PAGE_TITLE_MAP) {
    if (pathname.startsWith(entry.prefix)) return entry.title
  }
  return 'Dashboard'
}

export default function DashboardLayout() {
  const navigate     = useNavigate()
  const location     = useLocation()
  const { user, logout } = useAuthStore()
  const [sidebarOpen, setSidebarOpen] = useState(false)

  const handleLogout = async () => {
    try { await logout() } catch { /* proceed regardless */ }
    finally { navigate('/login', { replace: true }) }
  }

  const pageTitle   = resolvePageTitle(location.pathname)
  const initials    = (user?.display_name || user?.username || '?').slice(0, 2).toUpperCase()

  return (
    <div className="dash">

      {/* ── SIDEBAR ─────────────────────────────────────────────────────────── */}
      <aside className={`dash__sidebar ${sidebarOpen ? 'dash__sidebar--open' : ''}`}>
        {/* Brand */}
        <div className="dash__logo">
          <div className="dash__logo-icon">📸</div>
          <span className="dash__logo-text">Kyapture</span>
        </div>

        {/* Navigation */}
        <nav className="dash__nav" aria-label="Dashboard navigation">
          <div className="dash__nav-label">Navigation</div>
          {NAV_ITEMS.map(({ to, label, icon: Icon, end }) => (
            <NavLink
              key={to}
              to={to}
              end={end}
              onClick={() => setSidebarOpen(false)}
              className={({ isActive }) =>
                `dash__nav-item ${isActive ? 'dash__nav-item--active' : ''}`
              }
            >
              <span className="dash__nav-icon" aria-hidden="true">
                <Icon />
              </span>
              {label}
            </NavLink>
          ))}
        </nav>

        {/* User strip */}
        <div className="dash__user">
          <div className="dash__avatar" aria-hidden="true">
            {user?.avatar
              ? <img src={user.avatar} alt="" style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
              : initials
            }
          </div>
          <div className="dash__user-info">
            <div className="dash__user-name">{user?.display_name || user?.username}</div>
            <div className="dash__user-plan">
              {user?.is_active_plan ? '✦ Active plan' : 'Free plan'}
            </div>
          </div>
          <button
            className="dash__logout-btn"
            onClick={handleLogout}
            title="Sign out"
            type="button"
            aria-label="Sign out of Kyapture"
          >
            <LogoutIcon />
          </button>
        </div>
      </aside>

      {/* Mobile backdrop */}
      {sidebarOpen && (
        <div
          className="dash__overlay"
          onClick={() => setSidebarOpen(false)}
          aria-hidden="true"
        />
      )}

      {/* ── MAIN AREA ───────────────────────────────────────────────────────── */}
      <div className="dash__main">
        <header className="dash__topbar">
          <button
            className="dash__burger"
            onClick={() => setSidebarOpen(o => !o)}
            type="button"
            aria-label="Open navigation"
            aria-expanded={sidebarOpen}
          >
            <BurgerIcon />
          </button>

          <span className="dash__page-title">{pageTitle}</span>

          <div className="dash__topbar-right">
            {/* Avatar in topbar (mobile shows here) */}
            <div
              className="dash__avatar"
              style={{ width: 34, height: 34 }}
              aria-hidden="true"
            >
              {user?.avatar
                ? <img src={user.avatar} alt="" style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
                : initials
              }
            </div>
          </div>
        </header>

        <div className="dash__content">
          <Outlet />
        </div>
      </div>
    </div>
  )
}

// ── INLINE SVG ICONS ──────────────────────────────────────────────────────────
// Inline keeps the bundle trim (no icon lib dependency) and
// matches the 15px size slot in .dash__nav-icon.

function HomeIcon() {
  return (
    <svg width="15" height="15" viewBox="0 0 24 24" fill="none"
      stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>
      <polyline points="9 22 9 12 15 12 15 22"/>
    </svg>
  )
}
function GalleriesIcon() {
  return (
    <svg width="15" height="15" viewBox="0 0 24 24" fill="none"
      stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/>
      <rect x="14" y="14" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/>
    </svg>
  )
}
function UploadIcon() {
  return (
    <svg width="15" height="15" viewBox="0 0 24 24" fill="none"
      stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
      <polyline points="17 8 12 3 7 8"/>
      <line x1="12" y1="3" x2="12" y2="15"/>
    </svg>
  )
}
function SettingsIcon() {
  return (
    <svg width="15" height="15" viewBox="0 0 24 24" fill="none"
      stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="12" r="3"/>
      <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/>
    </svg>
  )
}
function BillingIcon() {
  return (
    <svg width="15" height="15" viewBox="0 0 24 24" fill="none"
      stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <rect x="1" y="4" width="22" height="16" rx="2" ry="2"/>
      <line x1="1" y1="10" x2="23" y2="10"/>
    </svg>
  )
}
function LogoutIcon() {
  return (
    <svg width="15" height="15" viewBox="0 0 24 24" fill="none"
      stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/>
      <polyline points="16 17 21 12 16 7"/>
      <line x1="21" y1="12" x2="9" y2="12"/>
    </svg>
  )
}
function BurgerIcon() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none"
      stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <line x1="3" y1="12" x2="21" y2="12"/>
      <line x1="3" y1="6"  x2="21" y2="6"/>
      <line x1="3" y1="18" x2="21" y2="18"/>
    </svg>
  )
}