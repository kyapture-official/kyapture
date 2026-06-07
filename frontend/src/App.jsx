import React, { useEffect } from 'react'
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { useAuthStore } from './store/authStore'
import { ToastProvider } from './components/ui/Toast'
import ProtectedRoute     from './components/shared/ProtectedRoute'
import DashboardLayout    from './components/layout/DashboardLayout'
// Auth
import LoginPage          from './pages/auth/LoginPage'
import RegisterPage       from './pages/auth/RegisterPage'
import ForgotPasswordPage from './pages/auth/ForgotPasswordPage'
// Dashboard
import HomePage           from './pages/dashboard/HomePage'
import GalleriesPage      from './pages/dashboard/GalleriesPage'
import GalleryDetailPage  from './pages/dashboard/GalleryDetailPage'
import UploadPage         from './pages/dashboard/UploadPage'
import SettingsPage       from './pages/dashboard/SettingsPage'
import BillingPage        from './pages/dashboard/BillingPage'
// Client portal
import ClientHomePage     from './pages/client/ClientHomePage'
import ClientGalleryPage  from './pages/client/ClientGalleryPage'
import DownloadPage       from './pages/client/DownloadPage'
// Public
import PricingPage        from './pages/subscription/PricingPage'
import LandingPage        from './pages/LandingPage'

export default function App() {
  // Selector pattern: subscribes only to `init`, not the entire store
  const init = useAuthStore((s) => s.init)

  // Single owner of session re-hydration — never call init() anywhere else
  useEffect(() => {
    init()
  }, [init])

  return (
    <ToastProvider>
      <BrowserRouter>
        <Routes>
          {/* Public */}
          <Route path="/"                element={<LandingPage />} />
          <Route path="/pricing"         element={<PricingPage />} />
          <Route path="/login"           element={<LoginPage />} />
          <Route path="/register"        element={<RegisterPage />} />
          <Route path="/forgot-password" element={<ForgotPasswordPage />} />

          {/* Protected photographer dashboard */}
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

          {/* Client portal */}
          <Route path="/g/:username"                element={<ClientHomePage />} />
          <Route path="/g/:username/:slug"          element={<ClientGalleryPage />} />
          <Route path="/g/:username/:slug/download" element={<DownloadPage />} />

          {/* Catch-all */}
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </BrowserRouter>
    </ToastProvider>
  )
}