// frontend/src/App.jsx

import { useEffect, lazy, Suspense } from 'react'
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { useAuthStore } from './store/authStore'
import { ToastProvider } from './components/ui/Toast'
import ErrorBoundary      from './components/shared/ErrorBoundary'
import ProtectedRoute     from './components/shared/ProtectedRoute'
import DashboardLayout    from './components/layout/DashboardLayout'
import Spinner            from './components/ui/Spinner'

// ── SYNCHRONOUS INITIAL VIEW IMPORTS ─────────────────────────────────────────
import LandingPage        from './pages/LandingPage'
import LoginPage          from './pages/auth/LoginPage'
import RegisterPage       from './pages/auth/RegisterPage'
import ForgotPasswordPage from './pages/auth/ForgotPasswordPage'

// ── LAZY-LOADED DASHBOARD CHUNKS ──────────────────────────────────────────────
const HomePage           = lazy(() => import('./pages/dashboard/HomePage'))
const GalleriesPage      = lazy(() => import('./pages/dashboard/GalleriesPage'))
const GalleryDetailPage  = lazy(() => import('./pages/dashboard/GalleryDetailPage'))
const UploadPage         = lazy(() => import('./pages/dashboard/UploadPage'))
const SettingsPage       = lazy(() => import('./pages/dashboard/SettingsPage'))

// C-1: correct import — pages/subscription/BillingPage, not the dead
// pages/dashboard/BillingPage (which calls subscriptionsApi.plans() /
// .mySubscription() / .submitPayment() — methods that no longer exist).
const BillingPage        = lazy(() => import('./pages/subscription/BillingPage'))

// ── LAZY-LOADED CLIENT PORTAL CHUNKS ──────────────────────────────────────────
const ClientHomePage     = lazy(() => import('./pages/client/ClientHomePage'))
const ClientGalleryPage  = lazy(() => import('./pages/client/ClientGalleryPage'))
const DownloadPage       = lazy(() => import('./pages/client/DownloadPage'))
const PricingPage        = lazy(() => import('./pages/subscription/PricingPage'))

export default function App() {
  const init    = useAuthStore((s) => s.init)
  const logout  = useAuthStore((s) => s.logout)
  const loading = useAuthStore((s) => s.loading)

  useEffect(() => {
    init()
  }, [init])

  useEffect(() => {
    const handleSessionExpiry = () => { logout() }
    window.addEventListener('auth-session-expired', handleSessionExpiry)
    return () => window.removeEventListener('auth-session-expired', handleSessionExpiry)
  }, [logout])

  if (loading) {
    return (
      <div className="flex h-screen w-screen items-center justify-center bg-[#fdfbf7]">
        <Spinner size="lg" className="text-[#2C2825]" />
      </div>
    )
  }

  return (
    // BUG FIX (repeat regression — same as last submission): ErrorBoundary
    // was missing again. Suspense only handles the PENDING state of a
    // lazy() import; a REJECTED one (network failure mid-download, or a
    // client with a stale tab open after you redeploy and Vite's hashed
    // chunk filenames change) throws as a render-time error that only an
    // ErrorBoundary catches. Without it, a failed chunk load white-screens
    // the app with zero recovery path.
    <ErrorBoundary>
      <ToastProvider>
        <BrowserRouter
          future={{
            v7_startTransition: true,
            v7_relativeSplatPath: true,
          }}
        >
          <Suspense
            fallback={
              <div className="flex h-screen w-screen items-center justify-center bg-[#fdfbf7]">
                <Spinner size="md" className="text-[#2C2825]" />
              </div>
            }
          >
            <Routes>
              <Route path="/"                element={<LandingPage />} />
              <Route path="/pricing"         element={<PricingPage />} />
              <Route path="/login"           element={<LoginPage />} />
              <Route path="/register"        element={<RegisterPage />} />
              <Route path="/forgot-password" element={<ForgotPasswordPage />} />

              <Route path="/dashboard" element={<ProtectedRoute />}>
                <Route element={<DashboardLayout />}>
                  <Route index                  element={<HomePage />} />
                  <Route path="galleries"       element={<GalleriesPage />} />
                  <Route path="galleries/:id"   element={<GalleryDetailPage />} />
                  <Route path="upload"          element={<UploadPage />} />
                  <Route path="settings"        element={<SettingsPage />} />
                  <Route path="billing"         element={<BillingPage />} />
                </Route>
              </Route>

              <Route path="/g/:username"                element={<ClientHomePage />} />
              <Route path="/g/:username/:slug"          element={<ClientGalleryPage />} />
              <Route path="/g/:username/:slug/download" element={<DownloadPage />} />

              <Route path="*" element={<Navigate to="/" replace />} />
            </Routes>
          </Suspense>
        </BrowserRouter>
      </ToastProvider>
    </ErrorBoundary>
  )
}