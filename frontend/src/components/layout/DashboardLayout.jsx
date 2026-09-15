// C:/Users/LENOVO/Desktop/kyapture/frontend/src/components/layout/DashboardLayout.jsx
import { useState, useEffect, useRef, useCallback } from 'react'
import { NavLink, useLocation, Outlet } from 'react-router-dom'
import { useAuthStore } from '../../store/authStore'

// ── ICONS (inline SVGs for zero-dependency, tree-shakeable rendering) ─────────
const Icons = {
  Home: (
    <svg className="w-5 h-5 shrink-0" fill="none" stroke="currentColor" strokeWidth="1.8" viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" d="M2.25 12l8.954-8.955c.44-.439 1.152-.439 1.591 0L21.75 12M4.5 9.75v10.125c0 .621.504 1.125 1.125 1.125H9.75v-4.875c0-.621.504-1.125 1.125-1.125h2.25c.621 0 1.125.504 1.125 1.125V21h4.125c.621 0 1.125-.504 1.125-1.125V9.75M8.25 21h8.25" />
    </svg>
  ),
  Galleries: (
    <svg className="w-5 h-5 shrink-0" fill="none" stroke="currentColor" strokeWidth="1.8" viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" d="M2.25 15.75l5.159-5.159a2.25 2.25 0 013.182 0l5.159 5.159m-1.5-1.5l1.409-1.409a2.25 2.25 0 013.182 0l2.909 2.909m-18 3.75h16.5a1.5 1.5 0 001.5-1.5V6a1.5 1.5 0 00-1.5-1.5H3.75A1.5 1.5 0 002.25 6v12a1.5 1.5 0 001.5 1.5zm10.5-11.25h.008v.008h-.008V8.25zm.375 0a.375 0 11-.75 0 .375 0 01.75 0z" />
    </svg>
  ),
  Settings: (
    <svg className="w-5 h-5 shrink-0" fill="none" stroke="currentColor" strokeWidth="1.8" viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" d="M9.594 3.94c.09-.542.56-.94 1.11-.94h2.593c.55 0 1.02.398 1.11.94l.213 1.281c.063.374.313.686.645.87.074.04.147.083.22.127.324.196.72.257 1.075.124l1.217-.456a1.125 1.125 0 011.37.49l1.296 2.247a1.125 1.125 0 01-.26 1.43l-1.003.828c-.293.241-.438.613-.43.992a7.723 7.723 0 010 .255c-.008.378.137.75.43.991l1.004.827c.424.35.534.954.26 1.43l-1.297 2.247a1.125 1.125 0 01-1.369.491l-1.217-.456c-.355-.133-.75-.072-1.076.124a6.47 6.47 0 01-.22.128c-.331.183-.581.495-.644.869l-.213 1.281c-.09.543-.56.94-1.11.94h-2.594c-.552 0-1.02-.398-1.11-.94l-.213-1.281c-.062-.374-.312-.686-.644-.87a6.52 6.52 0 01-.22-.127c-.325-.196-.72-.257-1.076-.124l-1.217.456a1.125 1.125 0 01-1.369-.49l-1.297-2.247a1.125 1.125 0 01.26-1.43l1.004-.827c.292-.24.437-.613.43-.991a6.932 6.932 0 010-.255c.007-.38-.138-.751-.43-.992l-1.004-.827a1.125 1.125 0 01-.26-1.43l1.297-2.247a1.125 1.125 0 011.37-.491l1.216.456c.356.133.751.072 1.076-.124.072-.044.146-.086.22-.128.332-.183.582-.495.644-.869l.214-1.28Z" />
      <path strokeLinecap="round" strokeLinejoin="round" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
    </svg>
  ),
  Billing: (
    <svg className="w-5 h-5 shrink-0" fill="none" stroke="currentColor" strokeWidth="1.8" viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" d="M2.25 8.25h19.5M2.25 9h19.5m-16.5 5.25h6m-6 2.25h3m-3.75 3h15a2.25 2.25 0 002.25-2.25V6.75A2.25 2.25 0 0019.5 4.5h-15a2.25 2.25 0 00-2.25 2.25v10.5A2.25 2.25 0 004.5 19.5z" />
    </svg>
  ),
  Search: (
    <svg className="w-4 h-4" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" d="M21 21l-4.35-4.35M11 19a8 8 0 100-16 8 8 0 000 16z" />
    </svg>
  ),
  Bell: (
    <svg className="w-5 h-5" fill="none" stroke="currentColor" strokeWidth="1.8" viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" d="M14.857 17.082a23.848 23.848 0 005.454-1.31A8.967 8.967 0 0118 9.75v-.7V9A6 6 0 006 9v.75a8.967 8.967 0 01-2.312 6.022c1.733.64 3.56 1.085 5.455 1.31m5.714 0a24.255 24.255 0 01-5.714 0m5.714 0a3 3 0 11-5.714 0" />
    </svg>
  ),
  Logout: (
    <svg className="w-5 h-5" fill="none" stroke="currentColor" strokeWidth="1.8" viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" d="M15.75 9V5.25A2.25 2.25 0 0013.5 3h-6a2.25 2.25 0 00-2.25 2.25v13.5A2.25 2.25 0 007.5 21h6a2.25 2.25 0 002.25-2.25V15M12 9l-3 3m0 0l3 3m-3-3h12.75" />
    </svg>
  ),
  Menu: (
    <svg className="w-5 h-5" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" d="M3.75 6.75h16.5M3.75 12h16.5m-16.5 5.25h16.5" />
    </svg>
  ),
  Close: (
    <svg className="w-5 h-5" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
    </svg>
  ),
  ChevronDown: (
    <svg className="w-4 h-4" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" d="M19.5 8.25l-7.5 7.5-7.5-7.5" />
    </svg>
  ),
  Collapse: (
    <svg className="w-4 h-4" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" d="M18.75 19.5l-7.5-7.5 7.5-7.5m-6 15L5.25 12l7.5-7.5" />
    </svg>
  ),
}

// Single source of truth for focusable elements
const FOCUSABLE = [
  'button:not([disabled])',
  'input:not([disabled])',
  'select:not([disabled])',
  'textarea:not([disabled])',
  'a[href]:not([aria-disabled="true"])',
  '[tabindex]:not([tabindex="-1"]):not([disabled])',
].join(', ')

// Navigation config — keeps structure declarative and easily extensible
const navigation = [
  {
    name: 'Home',
    path: '/dashboard',
    end: true,
    icon: Icons.Home,
    label: 'Overview',
  },
  {
    name: 'Galleries',
    path: '/dashboard/galleries',
    icon: Icons.Galleries,
    label: 'Collections',
  },
  {
    name: 'Settings',
    path: '/dashboard/settings',
    icon: Icons.Settings,
    label: 'Account',
  },
  {
    name: 'Billing',
    path: '/dashboard/billing',
    icon: Icons.Billing,
    label: 'Billing',
  },
]

// Grouped nav sections for sidebar labels
const navSections = [
  { label: 'Overview', items: ['Home', 'Galleries'] },
  { label: 'Account', items: ['Settings', 'Billing'] },
]

/**
 * WHAT: Photographer Dashboard Shell Layout
 * WHY:  Wraps all private routes inside a single stable DOM tree. Provides
 *       a modern sidebar with collapsible icon mode, a top header bar with
 *       search and user profile, and a clean content area.
 */
export default function DashboardLayout() {
  const location = useLocation()
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false)
  const [collapsed, setCollapsed] = useState(() => {
    try { return localStorage.getItem('kp_sidebar_collapsed') === 'true' } catch { return false }
  })
  const [searchFocused, setSearchFocused] = useState(false)
  const [userMenuOpen, setUserMenuOpen] = useState(false)

  const user = useAuthStore((state) => state.user)
  const logout = useAuthStore((state) => state.logout)

  const mobileNavRef = useRef(null)
  const toggleButtonRef = useRef(null)
  const closeButtonRef = useRef(null)
  const wasOpenRef = useRef(false)
  const userMenuRef = useRef(null)

  const displayName = user?.display_name || 'Photographer'
  const planLabel = user?.is_active_plan ? 'Pro Plan' : 'Free Plan'
  const initials = displayName.split(' ').map(n => n[0]).join('').toUpperCase().slice(0, 2)
  const studioUrl = user?.username ? `${user.username}.kyapture.com` : ''

  // Lock body scroll while the mobile drawer is open
  useEffect(() => {
    if (!mobileMenuOpen) return
    const previousOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => { document.body.style.overflow = previousOverflow }
  }, [mobileMenuOpen])

  // Close mobile drawer automatically on path navigation
  useEffect(() => {
    setMobileMenuOpen(false)
    setUserMenuOpen(false)
  }, [location.pathname])

  // Persist sidebar collapsed state to localStorage
  useEffect(() => {
    try { localStorage.setItem('kp_sidebar_collapsed', String(collapsed)) } catch {}
  }, [collapsed])

  // Modal accessibility: focus management
  useEffect(() => {
    if (mobileMenuOpen) {
      closeButtonRef.current?.focus()
    } else if (wasOpenRef.current) {
      toggleButtonRef.current?.focus()
    }
    wasOpenRef.current = mobileMenuOpen
  }, [mobileMenuOpen])

  // Keyboard controls for mobile drawer
  useEffect(() => {
    if (!mobileMenuOpen) return
    function handleKeyDown(e) {
      if (e.key === 'Escape') { setMobileMenuOpen(false); return }
      if (e.key !== 'Tab' || !mobileNavRef.current) return
      const focusable = mobileNavRef.current.querySelectorAll(FOCUSABLE)
      if (focusable.length === 0) return
      const first = focusable[0]
      const last = focusable[focusable.length - 1]
      if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus() }
      else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus() }
    }
    document.addEventListener('keydown', handleKeyDown)
    return () => document.removeEventListener('keydown', handleKeyDown)
  }, [mobileMenuOpen])

  // Close user menu on outside click
  useEffect(() => {
    if (!userMenuOpen) return
    function handleClick(e) {
      if (userMenuRef.current && !userMenuRef.current.contains(e.target)) {
        setUserMenuOpen(false)
      }
    }
    document.addEventListener('mousedown', handleClick)
    return () => document.removeEventListener('mousedown', handleClick)
  }, [userMenuOpen])

  // Get current page title from navigation
  const currentPageTitle = navigation.find(n =>
    n.end ? location.pathname === n.path : location.pathname.startsWith(n.path)
  )?.name || 'Dashboard'

  return (
    <div className="min-h-screen bg-slate-50 flex">

      {/* ── MOBILE NAV BAR ── */}
      <div className="md:hidden flex items-center justify-between px-4 py-3 bg-white border-b border-slate-200 z-30 w-full fixed top-0 left-0 right-0">
        <div className="flex items-center gap-2.5">
          <div className="w-8 h-8 rounded-lg bg-teal-500 flex items-center justify-center">
            <span className="text-white font-bold text-xs">K</span>
          </div>
          <span className="font-serif text-lg font-medium text-ink tracking-tight">Kyapture</span>
        </div>
        <button
          ref={toggleButtonRef}
          type="button"
          onClick={() => setMobileMenuOpen(true)}
          className="p-2 rounded-xl text-slate-500 hover:text-ink hover:bg-slate-100 transition-all cursor-pointer"
          aria-label="Open navigation menu"
          aria-haspopup="dialog"
          aria-expanded={mobileMenuOpen}
        >
          {Icons.Menu}
        </button>
      </div>

      {/* ── MOBILE SLIDE-OUT DRAWER ── */}
      {mobileMenuOpen && (
        <div className="md:hidden fixed inset-0 z-50 flex" role="dialog" aria-modal="true" aria-label="Navigation menu">
          <div className="absolute inset-0 bg-slate-900/30 backdrop-blur-sm" onClick={() => setMobileMenuOpen(false)} aria-hidden="true" />
          <div ref={mobileNavRef} className="relative w-full max-w-xs bg-slate-900 h-full shadow-2xl flex flex-col z-10 animate-slide-right">
            {/* Drawer Header */}
            <div className="flex items-center justify-between px-5 py-4 border-b border-white/10">
              <div className="flex items-center gap-2.5">
                <div className="w-8 h-8 rounded-lg bg-teal-500 flex items-center justify-center">
                  <span className="text-white font-bold text-xs">K</span>
                </div>
                <span className="font-serif text-lg font-medium text-white">Kyapture</span>
              </div>
              <button
                ref={closeButtonRef}
                type="button"
                onClick={() => setMobileMenuOpen(false)}
                className="p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-white/10 transition-colors cursor-pointer"
                aria-label="Close menu"
              >
                {Icons.Close}
              </button>
            </div>

            {/* Navigation Links */}
            <nav className="flex-1 overflow-y-auto px-3 py-4 space-y-1">
              {navigation.map((item) => (
                <NavLink
                  key={item.name}
                  to={item.path}
                  end={item.end}
                  className={({ isActive }) =>
                    `flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm font-medium transition-all duration-200 relative ${
                      isActive
                        ? 'bg-teal-500/10 text-teal-400 font-semibold'
                        : 'text-slate-400 hover:text-white hover:bg-white/5'
                    }`
                  }
                >
                  {({ isActive }) => (
                    <>
                      {isActive && (
                        <div className="absolute left-0 top-1/2 -translate-y-1/2 w-[3px] h-5 rounded-r-full bg-teal-400" />
                      )}
                      {item.icon}
                      <span>{item.name}</span>
                    </>
                  )}
                </NavLink>
              ))}
            </nav>

            {/* Profile & Logout */}
            <div className="px-3 py-4 border-t border-white/10">
              <div className="flex items-center justify-between gap-3 px-2">
                <div className="flex items-center gap-3 min-w-0">
                  <div className="w-9 h-9 rounded-full bg-teal-500 flex items-center justify-center flex-shrink-0">
                    <span className="text-white text-xs font-semibold">{initials}</span>
                  </div>
                  <div className="min-w-0">
                    <p className="text-sm font-semibold text-white leading-none truncate">{displayName}</p>
                    <span className="text-[10px] font-semibold text-slate-400 uppercase tracking-wider mt-1 block">{planLabel}</span>
                  </div>
                </div>
                <button
                  type="button"
                  onClick={() => logout()}
                  className="p-2 rounded-lg text-slate-400 hover:text-red-400 hover:bg-red-500/10 transition-all cursor-pointer shrink-0"
                  aria-label="Logout session"
                >
                  {Icons.Logout}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* ── DESKTOP SIDEBAR ── */}
      <aside
        className={`hidden md:flex flex-col justify-between bg-slate-900 h-screen sticky top-0 shrink-0 transition-all duration-300 ease-out ${
          collapsed ? 'w-[72px]' : 'w-[250px]'
        }`}
      >
        <div className="flex flex-col h-full">
          {/* Logo */}
          <div className={`px-4 py-4 border-b border-white/10 flex items-center ${collapsed ? 'justify-center' : 'gap-3'}`}>
            <div className="w-9 h-9 rounded-xl bg-teal-500 flex items-center justify-center flex-shrink-0">
              <span className="text-white font-bold text-sm">K</span>
            </div>
            {!collapsed && (
              <span className="font-serif text-lg font-medium text-white tracking-tight">Kyapture</span>
            )}
          </div>

          {/* Navigation */}
          <nav className="flex-1 overflow-y-auto px-3 py-4 space-y-5">
            {navSections.map((section) => (
              <div key={section.label}>
                {!collapsed && (
                  <p className="px-3 mb-2 text-[10px] font-semibold tracking-widest uppercase text-slate-500">
                    {section.label}
                  </p>
                )}
                <div className="space-y-0.5">
                  {section.items.map((itemName) => {
                    const item = navigation.find(n => n.name === itemName)
                    if (!item) return null
                    return (
                      <NavLink
                        key={item.name}
                        to={item.path}
                        end={item.end}
                        title={collapsed ? item.name : undefined}
                        className={({ isActive }) =>
                          `flex items-center gap-3 rounded-xl text-sm font-medium transition-all duration-200 relative group ${
                            collapsed ? 'justify-center px-2 py-2.5' : 'px-3 py-2.5'
                          } ${
                            isActive
                              ? 'bg-teal-500/10 text-teal-400 font-semibold'
                              : 'text-slate-400 hover:text-white hover:bg-white/5'
                          }`
                        }
                      >
                        {({ isActive }) => (
                          <>
                            {isActive && !collapsed && (
                              <div className="absolute left-0 top-1/2 -translate-y-1/2 w-[3px] h-5 rounded-r-full bg-teal-400" />
                            )}
                            {isActive && collapsed && (
                              <div className="absolute inset-x-0 -bottom-2.5 mx-auto w-5 h-[2px] rounded-full bg-teal-400" />
                            )}
                            {item.icon}
                            {!collapsed && <span>{item.name}</span>}
                          </>
                        )}
                      </NavLink>
                    )
                  })}
                </div>
              </div>
            ))}
          </nav>

          {/* Collapse Toggle */}
          <div className="px-3 pb-2">
            <button
              type="button"
              onClick={() => setCollapsed(c => !c)}
              className={`w-full flex items-center gap-3 px-3 py-2 rounded-xl text-xs font-medium text-slate-500 hover:text-white hover:bg-white/5 transition-all cursor-pointer ${
                collapsed ? 'justify-center' : ''
              }`}
              title={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
            >
              <span className={`transition-transform duration-300 ${collapsed ? 'rotate-180' : ''}`}>
                {Icons.Collapse}
              </span>
              {!collapsed && <span>Collapse</span>}
            </button>
          </div>

          {/* User Profile */}
          <div className={`px-3 py-3 border-t border-white/10 ${collapsed ? 'px-2' : ''}`}>
            {collapsed ? (
              <div className="flex justify-center py-1">
                <div className="w-9 h-9 rounded-full bg-teal-500 flex items-center justify-center cursor-pointer hover:ring-2 hover:ring-teal-400/30 transition-all" title={displayName}>
                  <span className="text-white text-xs font-semibold">{initials}</span>
                </div>
              </div>
            ) : (
              <div className="flex items-center gap-3 px-2">
                <div className="w-9 h-9 rounded-full bg-teal-500 flex items-center justify-center flex-shrink-0">
                  <span className="text-white text-xs font-semibold">{initials}</span>
                </div>
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-semibold text-white leading-none truncate">{displayName}</p>
                  <span className="text-[10px] font-semibold text-slate-500 uppercase tracking-wider mt-1 block">{planLabel}</span>
                </div>
                <button
                  type="button"
                  onClick={() => logout()}
                  className="p-1.5 rounded-lg text-slate-500 hover:text-red-400 hover:bg-red-500/10 transition-all cursor-pointer shrink-0"
                  aria-label="Logout session"
                  title="Logout"
                >
                  {Icons.Logout}
                </button>
              </div>
            )}
          </div>
        </div>
      </aside>

      {/* ── MAIN CONTENT AREA ── */}
      <div className="flex-1 w-full flex flex-col min-h-screen">
        {/* Top Header Bar */}
        <header className="h-[60px] bg-white/80 backdrop-blur-md border-b border-slate-200 flex items-center px-4 md:px-6 gap-4 sticky top-0 z-40">
          {/* Mobile burger */}
          <button
            type="button"
            onClick={() => setMobileMenuOpen(true)}
            className="md:hidden p-2 rounded-xl text-slate-500 hover:text-ink hover:bg-slate-100 transition-all cursor-pointer"
            aria-label="Open navigation"
          >
            {Icons.Menu}
          </button>

          {/* Page Title */}
          <h1 className="font-serif text-xl text-ink font-medium">{currentPageTitle}</h1>

          {/* Spacer */}
          <div className="flex-1" />

          {/* Search */}
          <div className={`hidden sm:flex items-center gap-2 px-3 py-2 rounded-xl border transition-all duration-200 w-64 ${
            searchFocused
              ? 'border-teal-400/40 bg-white shadow-glow-teal ring-2 ring-teal-500/10'
              : 'border-slate-200 bg-slate-50 hover:border-slate-300'
          }`}>
            <span className="text-slate-400">{Icons.Search}</span>
            <input
              type="text"
              placeholder="Search anything..."
              onFocus={() => setSearchFocused(true)}
              onBlur={() => setSearchFocused(false)}
              className="bg-transparent border-none outline-none text-sm text-ink placeholder:text-slate-400 w-full font-sans"
            />
          </div>

          {/* Notification Bell */}
          <button
            type="button"
            className="relative p-2 rounded-xl text-slate-500 hover:text-ink hover:bg-slate-100 transition-all cursor-pointer"
            aria-label="Notifications"
          >
            {Icons.Bell}
          </button>

          {/* User Avatar Dropdown (Desktop) */}
          <div className="hidden md:block relative" ref={userMenuRef}>
            <button
              type="button"
              onClick={() => setUserMenuOpen(o => !o)}
              className="flex items-center gap-2 p-1.5 rounded-xl hover:bg-slate-100 transition-all cursor-pointer"
              aria-label="User menu"
              aria-expanded={userMenuOpen}
            >
              <div className="w-8 h-8 rounded-full bg-teal-500 flex items-center justify-center">
                <span className="text-white text-[11px] font-semibold">{initials}</span>
              </div>
              <span className="text-sm font-medium text-ink max-w-[100px] truncate">{displayName}</span>
              <span className={`transition-transform duration-200 text-slate-400 ${userMenuOpen ? 'rotate-180' : ''}`}>
                {Icons.ChevronDown}
              </span>
            </button>

            {/* Dropdown Menu */}
            {userMenuOpen && (
              <div className="absolute right-0 top-full mt-2 w-56 bg-white rounded-xl border border-slate-200 shadow-card-hover py-2 z-50 animate-scale-in">
                <div className="px-4 py-3 border-b border-slate-100">
                  <p className="text-sm font-semibold text-ink truncate">{displayName}</p>
                  <p className="text-xs text-slate-500 mt-0.5 truncate">{user?.email}</p>
                </div>
                <div className="py-1">
                  <NavLink
                    to="/dashboard/settings"
                    onClick={() => setUserMenuOpen(false)}
                    className="flex items-center gap-2.5 px-4 py-2 text-sm text-slate-600 hover:text-ink hover:bg-slate-50 transition-colors"
                  >
                    {Icons.Settings}
                    <span>Settings</span>
                  </NavLink>
                  <button
                    type="button"
                    onClick={() => { setUserMenuOpen(false); logout(); }}
                    className="w-full flex items-center gap-2.5 px-4 py-2 text-sm text-slate-600 hover:text-red-600 hover:bg-red-50 transition-colors cursor-pointer"
                  >
                    {Icons.Logout}
                    <span>Sign Out</span>
                  </button>
                </div>
              </div>
            )}
          </div>
        </header>

        {/* Page Content */}
        <main className="flex-1 overflow-y-auto">
          <div className="p-4 md:p-6 lg:p-8">
            <Outlet />
          </div>
        </main>
      </div>
    </div>
  )
}
