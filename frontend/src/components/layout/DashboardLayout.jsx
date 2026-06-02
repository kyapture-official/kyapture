import React, { useState } from 'react'
import { NavLink, useNavigate, useLocation, Outlet } from 'react-router-dom'
import { useAuthStore } from '../../store/authStore'

const NAV_ITEMS = [
  { to: '/dashboard',           label: 'Home',      icon: '🏠', end: true },
  { to: '/dashboard/galleries', label: 'Galleries', icon: '🖼️' },
  { to: '/dashboard/settings',  label: 'Settings',  icon: '⚙️' },
]

const PAGE_TITLES = {
  '/dashboard':            'Home',
  '/dashboard/galleries':  'Galleries',
  '/dashboard/settings':   'Settings',
}

/**
 * WHAT: Aligned and Optimized Administrative Sidebar Shell
 * WHY: Enforces React Router v6 layout nesting rules and provides secure session exit structures [7].
 * HOW: Employs React Router's <Outlet /> node to render nested views [7].
 * WHERE: frontend/src/components/layout/DashboardLayout.jsx
 */
export default function DashboardLayout() {
  const navigate = useNavigate()
  const location = useLocation()
  const { user, logout } = useAuthStore()
  const [sidebarOpen, setSidebarOpen] = useState(false)

  /**
   * WHAT: Defensive Logout Pattern
   * WHY: Prevents network or backend failures from trapping a user's session.
   * HOW: Traps network exceptions but always forces local token cleanup and redirects.
   */
  const handleLogout = async () => {
    try {
      await logout()
    } catch (err) {
      // Log trace internally but do not block the UI redirect
      console.warn('Backend session termination failed, forcing local client logout clearance.');
    } finally {
      navigate('/login')
    }
  }

  // Find page title safely by checking the active location path match
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
            {user?.avatar ? (
              <img src={user.avatar} alt="" style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
            ) : (
              avatarLetter
            )}
          </div>
          <div className="dash__user-info">
            <div className="dash__user-name">{user?.display_name || user?.username}</div>
            <div className="dash__user-plan">{user?.is_active_plan ? 'Pro Plan' : 'Free Plan'}</div>
          </div>
          <button className="dash__logout-btn" onClick={handleLogout} title="Sign out" type="button">
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
          <button className="dash__burger" onClick={() => setSidebarOpen(o => !o)} type="button">
            ☰
          </button>
          <span className="dash__page-title">{pageTitle}</span>
          <div className="dash__topbar-right">
            <div className="dash__avatar" style={{ width: 34, height: 34, cursor: 'default' }}>
              {user?.avatar ? (
                <img src={user.avatar} alt="" style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
              ) : (
                avatarLetter
              )}
            </div>
          </div>
        </header>

        {/* 
          WHAT: React Router Outlet Node
          WHY: Allows React Router to mount nested sub-views inside our layout [7].
        */}
        <div className="dash__content">
          <Outlet />
        </div>
      </div>
    </div>
  )
}