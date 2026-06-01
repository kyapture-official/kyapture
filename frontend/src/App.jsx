import React, { useEffect } from 'react'
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { useAuthStore } from './store/authStore'
import { ToastProvider } from './components/ui/Toast'
import ProtectedRoute from './components/shared/ProtectedRoute'
import DashboardLayout from './components/layout/DashboardLayout'

// Auth pages
import LoginPage    from './pages/auth/LoginPage'
import RegisterPage from './pages/auth/RegisterPage'

// Dashboard pages
import HomePage          from './pages/dashboard/HomePage'
import GalleriesPage     from './pages/dashboard/GalleriesPage'
import GalleryDetailPage from './pages/dashboard/GalleryDetailPage'
import UploadPage        from './pages/dashboard/UploadPage'
import SettingsPage      from './pages/dashboard/SettingsPage'
import BillingPage       from './pages/dashboard/BillingPage'

// Client portal pages
import ClientHomePage    from './pages/client/ClientHomePage'
import ClientGalleryPage from './pages/client/ClientGalleryPage'
import DownloadPage      from './pages/client/DownloadPage'

// Public pages
import PricingPage from './pages/subscription/PricingPage'
import LandingPage from './pages/LandingPage'

export default function App() {
  const { init } = useAuthStore()

  useEffect(() => {
    init()
  }, [init])

  return (
    <ToastProvider>
      <BrowserRouter>
        <Routes>
          {/* Public routes */}
          <Route path="/"        element={<LandingPage />} />
          <Route path="/pricing" element={<PricingPage />} />
          <Route path="/login"   element={<LoginPage />} />
          <Route path="/register" element={<RegisterPage />} />

          {/* Dashboard (protected) */}
          <Route
            path="/dashboard"
            element={
              <ProtectedRoute>
                <DashboardLayout>
                  <HomePage />
                </DashboardLayout>
              </ProtectedRoute>
            }
          />
          <Route
            path="/dashboard/galleries"
            element={
              <ProtectedRoute>
                <DashboardLayout>
                  <GalleriesPage />
                </DashboardLayout>
              </ProtectedRoute>
            }
          />
          <Route
            path="/dashboard/galleries/:id"
            element={
              <ProtectedRoute>
                <DashboardLayout>
                  <GalleryDetailPage />
                </DashboardLayout>
              </ProtectedRoute>
            }
          />
          <Route
            path="/dashboard/upload"
            element={
              <ProtectedRoute>
                <DashboardLayout>
                  <UploadPage />
                </DashboardLayout>
              </ProtectedRoute>
            }
          />
          <Route
            path="/dashboard/settings"
            element={
              <ProtectedRoute>
                <DashboardLayout>
                  <SettingsPage />
                </DashboardLayout>
              </ProtectedRoute>
            }
          />
          <Route
            path="/dashboard/billing"
            element={
              <ProtectedRoute>
                <DashboardLayout>
                  <BillingPage />
                </DashboardLayout>
              </ProtectedRoute>
            }
          />

          {/* Client portal — public subdomain-style routes */}
          {/* e.g. /p/johndoe or johndoe.kyapture.com */}
          <Route path="/p/:username"             element={<ClientHomePage />} />
          <Route path="/p/:username/:slug"        element={<ClientGalleryPage />} />
          <Route path="/p/:username/:slug/download" element={<DownloadPage />} />

          {/* Fallback */}
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </BrowserRouter>
    </ToastProvider>
  )
}
