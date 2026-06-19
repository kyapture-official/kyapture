import { useState, useEffect, useRef } from 'react'
import { NavLink, useLocation, Outlet } from 'react-router-dom'
import { useAuthStore } from '../../store/authStore'

// Single source of truth for focusable elements — keeps mobile drawer focus-traps secure
const FOCUSABLE = [
  'button:not([disabled])',
  'input:not([disabled])',
  'select:not([disabled])',
  'textarea:not([disabled])',
  'a[href]:not([aria-disabled="true"])',
  '[tabindex]:not([tabindex="-1"]):not([disabled])',
].join(', ')

// Hoisted list prevents redundant re-evaluation on layout state changes
const navigation = [
  {
    name: 'Home',
    path: '/dashboard',
    end: true, // Prevents "Home" from matching every nested /dashboard/* sub-path
    icon: (
      <svg className="w-5 h-5 shrink-0" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" d="M2.25 12l8.954-8.955c.44-.439 1.152-.439 1.591 0L21.75 12M4.5 9.75v10.125c0 .621.504 1.125 1.125 1.125H9.75v-4.875c0-.621.504-1.125 1.125-1.125h2.25c.621 0 1.125.504 1.125 1.125V21h4.125c.621 0 1.125-.504 1.125-1.125V9.75M8.25 21h8.25" />
      </svg>
    )
  },
  {
    name: 'Galleries',
    path: '/dashboard/galleries',
    icon: (
      <svg className="w-5 h-5 shrink-0" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" d="M2.25 15.75l5.159-5.159a2.25 2.25 0 013.182 0l5.159 5.159m-1.5-1.5l1.409-1.409a2.25 2.25 0 013.182 0l2.909 2.909m-18 3.75h16.5a1.5 1.5 0 001.5-1.5V6a1.5 1.5 0 00-1.5-1.5H3.75A1.5 1.5 0 002.25 6v12a1.5 1.5 0 001.5 1.5zm10.5-11.25h.008v.008h-.008V8.25zm.375 0a.375 0 11-.75 0 .375 0 01.75 0z" />
      </svg>
    )
  },
  {
    name: 'Upload',
    path: '/dashboard/upload',
    icon: (
      <svg className="w-5 h-5 shrink-0" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" d="M12 16.5V9.75m0 0l3 3m-3-3l-3 3M6.75 19.5a4.5 4.5 0 01-1.41-8.775 5.25 5.25 0 0110.233-2.33 3 3 0 013.758 3.848A3.752 3.752 0 0118 19.5H6.75z" />
      </svg>
    )
  },
  {
    name: 'Settings',
    path: '/dashboard/settings',
    icon: (
      <svg className="w-5 h-5 shrink-0" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" d="M9.594 3.94c.09-.542.56-.94 1.11-.94h2.593c.55 0 1.02.398 1.11.94l.213 1.281c.063.374.313.686.645.87.074.04.147.083.22.127.324.196.72.257 1.075.124l1.217-.456a1.125 1.125 0 011.37.49l1.296 2.247a1.125 1.125 0 01-.26 1.43l-1.003.828c-.293.241-.438.613-.43.992a7.723 7.723 0 010 .255c-.008.378.137.75.43.991l1.004.827c.424.35.534.954.26 1.43l-1.297 2.247a1.125 1.125 0 01-1.369.491l-1.217-.456c-.355-.133-.75-.072-1.076.124a6.47 6.47 0 01-.22.128c-.331.183-.581.495-.644.869l-.213 1.281c-.09.543-.56.94-1.11.94h-2.594c-.552 0-1.02-.398-1.11-.94l-.213-1.281c-.062-.374-.312-.686-.644-.87a6.52 6.52 0 01-.22-.127c-.325-.196-.72-.257-1.076-.124l-1.217.456a1.125 1.125 0 01-1.369-.49l-1.297-2.247a1.125 1.125 0 01.26-1.43l1.004-.827c.292-.24.437-.613.43-.991a6.932 6.932 0 010-.255c.007-.38-.138-.751-.43-.992l-1.004-.827a1.125 1.125 0 01-.26-1.43l1.297-2.247a1.125 1.125 0 011.37-.491l1.216.456c.356.133.751.072 1.076-.124.072-.044.146-.086.22-.128.332-.183.582-.495.644-.869l.214-1.28Z" />
        <path strokeLinecap="round" strokeLinejoin="round" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
      </svg>
    )
  }
]

// Shared design classes prevent styling drift across mobile and desktop sidebars
const navLinkClassName = ({ isActive }) =>
  `flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm font-semibold transition-all ${
    isActive
      ? 'bg-gray-900 text-white shadow-sm'
      : 'text-gray-600 hover:text-gray-900 hover:bg-gray-50'
  }`

/**
 * WHAT: Photographer Dashboard Shell Layout
 * WHY:  Wraps all private routes inside a single stable DOM tree. Prevents
 *       the sidebar and header from unmounting/remounting on every page change,
 *       while managing mobile drawer toggles and active session terminations safely.
 */
export default function DashboardLayout() {
  const location = useLocation()
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false)

  // Selective store subscriptions to prevent redundant re-renders
  const user = useAuthStore((state) => state.user)
  const logout = useAuthStore((state) => state.logout)

  const mobileNavRef = useRef(null)     // Drawer panel container
  const toggleButtonRef = useRef(null) // Hamburger button; focus returns here on close
  const closeButtonRef = useRef(null)   // Drawer close button; focused on open
  const wasOpenRef = useRef(false)      // Tracks open/close transitions vs. initial mount

  const displayName = user?.display_name || 'Photographer'
  const planLabel = user?.is_active_plan ? 'Pro Plan' : 'Free Plan'

  // Lock body scroll while the mobile drawer is open. Captures and restores
  // whatever overflow value was already there instead of hardcoding '', so this
  // doesn't clobber an overflow value some other part of the app may have set.
  useEffect(() => {
    if (!mobileMenuOpen) return

    const previousOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'

    return () => {
      document.body.style.overflow = previousOverflow
    }
  }, [mobileMenuOpen])

  // Close mobile drawer automatically on path navigation
  useEffect(() => {
    setMobileMenuOpen(false)
  }, [location.pathname])

  // Modal accessibility: move focus into the drawer when it opens, return it to the
  // trigger button when it closes.
  useEffect(() => {
    if (mobileMenuOpen) {
      closeButtonRef.current?.focus()
    } else if (wasOpenRef.current) {
      toggleButtonRef.current?.focus()
    }
    wasOpenRef.current = mobileMenuOpen
  }, [mobileMenuOpen])

  // Keyboard controls: trap focus inside the drawer and close it on Escape.
  useEffect(() => {
    if (!mobileMenuOpen) return

    function handleKeyDown(e) {
      if (e.key === 'Escape') {
        setMobileMenuOpen(false)
        return
      }

      if (e.key !== 'Tab' || !mobileNavRef.current) return

      const focusable = mobileNavRef.current.querySelectorAll(FOCUSABLE)
      if (focusable.length === 0) return

      const first = focusable[0]
      const last = focusable[focusable.length - 1]

      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault()
        last.focus()
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault()
        first.focus()
      }
    }

    document.addEventListener('keydown', handleKeyDown)
    return () => document.removeEventListener('keydown', handleKeyDown)
  }, [mobileMenuOpen])

  return (
    <div className="min-h-screen bg-gray-50 flex flex-col md:flex-row">

      {/* ── MOBILE NAV BAR (Visible strictly on smaller viewports) ── */}
      <div className="md:hidden flex items-center justify-between px-4 py-3 bg-white border-b border-gray-200 z-30 w-full">
        <div className="flex items-center gap-2">
          <span className="text-xl" aria-hidden="true">📸</span>
          <span className="font-semibold text-gray-900 tracking-tight font-sans">Kyapture</span>
        </div>

        {/* Hamburger Menu Toggle Button */}
        <button
          ref={toggleButtonRef}
          type="button"
          onClick={() => setMobileMenuOpen(true)}
          className="p-2 rounded-lg text-gray-500 hover:text-gray-900 hover:bg-gray-100 transition-colors cursor-pointer"
          aria-label="Open navigation menu"
          aria-haspopup="dialog"
          aria-expanded={mobileMenuOpen}
        >
          <svg className="w-6 h-6" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" d="M3.75 6.75h16.5M3.75 12h16.5m-16.5 5.25h16.5" />
          </svg>
        </button>
      </div>

      {/* ── MOBILE SLIDE-OUT DRAWER OVERLAY ── */}
      {mobileMenuOpen && (
        <div className="md:hidden fixed inset-0 z-50 flex" role="dialog" aria-modal="true" aria-label="Navigation menu">
          {/* Glassmorphism Backdrop */}
          <div className="absolute inset-0 bg-gray-900/40 backdrop-blur-sm" onClick={() => setMobileMenuOpen(false)} aria-hidden="true" />

          {/* Slide-out Sidebar Panel */}
          <div ref={mobileNavRef} className="relative w-full max-w-xs bg-white h-full shadow-2xl p-6 flex flex-col justify-between z-10 animate-slideRight">
            <div>
              {/* Header */}
              <div className="flex items-center justify-between pb-6 border-b border-gray-100 mb-6">
                <div className="flex items-center gap-2">
                  <span className="text-xl" aria-hidden="true">📸</span>
                  <span className="font-semibold text-gray-900 tracking-tight">Kyapture</span>
                </div>
                <button
                  ref={closeButtonRef}
                  type="button"
                  onClick={() => setMobileMenuOpen(false)}
                  className="p-1.5 rounded-lg text-gray-400 hover:text-gray-600 transition-colors cursor-pointer"
                  aria-label="Close menu"
                >
                  <svg className="w-5 h-5" fill="none" stroke="currentColor" strokeWidth="2.5" viewBox="0 0 24 24">
                    <line x1="18" y1="6" x2="6" y2="18" />
                    <line x1="6" y1="6" x2="18" y2="18" />
                  </svg>
                </button>
              </div>

              {/* Navigation Links */}
              <nav className="space-y-1">
                {navigation.map((item) => (
                  <NavLink key={item.name} to={item.path} end={item.end} className={navLinkClassName}>
                    {item.icon}
                    {item.name}
                  </NavLink>
                ))}
              </nav>
            </div>

            {/* Profile & Logout Action */}
            <div className="pt-6 border-t border-gray-100">
              <div className="flex items-center justify-between gap-3">
                <div className="min-w-0">
                  <p className="text-sm font-bold text-gray-900 leading-none truncate">{displayName}</p>
                  <span className="text-[10px] font-semibold text-gray-400 uppercase tracking-wider mt-1 block">{planLabel}</span>
                </div>
                <button
                  type="button"
                  onClick={() => logout()}
                  className="p-2 rounded-lg text-gray-400 hover:text-red-600 hover:bg-red-50 transition-colors cursor-pointer shrink-0"
                  aria-label="Logout session"
                >
                  <svg className="w-5 h-5" fill="none" stroke="currentColor" strokeWidth="2.5" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" d="M15.75 9V5.25A2.25 2.25 0 0013.5 3h-6a2.25 2.25 0 00-2.25 2.25v13.5A2.25 2.25 0 007.5 21h6a2.25 2.25 0 002.25-2.25V15M12 9l-3 3m0 0l3 3m-3-3h12.75" />
                  </svg>
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* ── DESKTOP PERSISTENT SIDEBAR (Visible strictly on larger viewports) ── */}
      <aside className="hidden md:flex flex-col justify-between w-64 bg-white border-r border-gray-200 p-6 h-screen sticky top-0 shrink-0">
        <div>
          {/* Logo Brand Header */}
          <div className="flex items-center gap-2 pb-6 border-b border-gray-100 mb-6">
            <span className="text-2xl" aria-hidden="true">📸</span>
            <span className="font-semibold text-gray-900 tracking-tight font-sans">Kyapture</span>
          </div>

          {/* Navigation Links */}
          <nav className="space-y-1">
            {navigation.map((item) => (
              <NavLink key={item.name} to={item.path} end={item.end} className={navLinkClassName}>
                {item.icon}
                {item.name}
              </NavLink>
            ))}
          </nav>
        </div>

        {/* Profile Card Footer */}
        <div className="pt-6 border-t border-gray-100">
          <div className="flex items-center justify-between gap-3">
            <div className="min-w-0">
              <p className="text-sm font-bold text-gray-900 leading-none truncate max-w-[120px]">{displayName}</p>
              <span className="text-[10px] font-semibold text-gray-400 uppercase tracking-wider mt-1 block">{planLabel}</span>
            </div>
            {/* Symmetrical Logout Action Button */}
            <button
              type="button"
              onClick={() => logout()}
              className="p-2 rounded-lg text-gray-400 hover:text-red-600 hover:bg-red-50 transition-colors cursor-pointer shrink-0"
              aria-label="Logout session"
            >
              <svg className="w-5 h-5" fill="none" stroke="currentColor" strokeWidth="2.5" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" d="M15.75 9V5.25A2.25 2.25 0 0013.5 3h-6a2.25 2.25 0 00-2.25 2.25v13.5A2.25 2.25 0 007.5 21h6a2.25 2.25 0 002.25-2.25V15M12 9l-3 3m0 0l3 3m-3-3h12.75" />
              </svg>
            </button>
          </div>
        </div>
      </aside>

      {/* ── PORTAL VIEW CONTENT AREA (Renders the child page route) ── */}
      <div className="flex-1 w-full overflow-y-auto">
        <Outlet />
      </div>
    </div>
  )
}