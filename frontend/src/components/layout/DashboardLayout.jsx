import React, { useState } from 'react'
import { NavLink, useNavigate, useLocation } from 'react-router-dom'
import { useAuthStore } from '../../store/authStore'

const NAV_ITEMS = [
  { to: '/dashboard',           label: 'Home',      icon: '🏠', end: true },
  { to: '/dashboard/galleries', label: 'Galleries', icon: '🖼️' },
  { to: '/dashboard/upload',    label: 'Upload',    icon: '⬆️' },
  { to: '/dashboard/billing',   label: 'Billing',   icon: '💳' },
  { to: '/dashboard/settings',  label: 'Settings',  icon: '⚙️' },
]

const PAGE_TITLES = {
  '/dashboard':            'Home',
  '/dashboard/galleries':  'Galleries',
  '/dashboard/upload':     'Upload',
  '/dashboard/billing':    'Billing',
  '/dashboard/settings':   'Settings',
}

export default function DashboardLayout({ children }) {
  const { user, logout } = useAuthStore()
  const navigate = useNavigate()
  const location = useLocation()
  const [sidebarOpen, setSidebarOpen] = useState(false)

  const handleLogout = async () => {
    await logout()
    navigate('/login')
  }

  // Find page title
  const pageTitle = Object.entries(PAGE_TITLES)
    .sort((a, b) => b[0].length - a[0].length)
    .find(([path]) => location.pathname.startsWith(path))?.[1] || 'Dashboard'

  const avatarLetter = (user?.display_name || user?.username || '?')[0].toUpperCase()

  return (
    <div className="dash">
      {/* ===== SIDEBAR ===== */}
      <aside className={`dash__sidebar ${sidebarOpen ? 'dash__sidebar--open' : ''}`}>
        {/* Logo */}
        <div className="dash__logo">
          <div className="dash__logo-icon">📸</div>
          <span className="dash__logo-text">Kyapture</span>
        </div>

        {/* Nav */}
        <nav className="dash__nav">
          <div className="dash__nav-label">Menu</div>
          {NAV_ITEMS.map(item => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.end}
              onClick={() => setSidebarOpen(false)}
              className={({ isActive }) =>
                `dash__nav-item ${isActive ? 'dash__nav-item--active' : ''}`
              }
            >
              <span className="dash__nav-icon">{item.icon}</span>
              {item.label}
            </NavLink>
          ))}
        </nav>

        {/* User row */}
        <div className="dash__user">
          <div className="dash__avatar">
            {user?.avatar
              ? <img src={user.avatar} alt="" style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
              : avatarLetter
            }
          </div>
          <div className="dash__user-info">
            <div className="dash__user-name">{user?.display_name || user?.username}</div>
            <div className="dash__user-plan">{user?.is_active_plan ? 'Pro Plan' : 'Free Plan'}</div>
          </div>
          <button className="dash__logout-btn" onClick={handleLogout} title="Sign out">
            ↩
          </button>
        </div>
      </aside>

      {/* Mobile overlay */}
      {sidebarOpen && (
        <div className="dash__overlay" onClick={() => setSidebarOpen(false)} />
      )}

      {/* ===== MAIN ===== */}
      <div className="dash__main">
        {/* Topbar */}
        <header className="dash__topbar">
          <button className="dash__burger" onClick={() => setSidebarOpen(o => !o)}>
            ☰
          </button>
          <span className="dash__page-title">{pageTitle}</span>
          <div className="dash__topbar-right">
            <div className="dash__avatar" style={{ width: 34, height: 34, cursor: 'default' }}>
              {user?.avatar
                ? <img src={user.avatar} alt="" style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
                : avatarLetter
              }
            </div>
          </div>
        </header>

        {/* Content */}
        <div className="dash__content">
          {children}
        </div>
      </div>
    </div>
  )
}
