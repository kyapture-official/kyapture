// C:/Users/LENOVO/Desktop/kyapture/frontend/src/App.jsx
import React, { useEffect } from "react";
import { BrowserRouter, Routes, Route, Navigate, useLocation } from "react-router-dom";
import { useAuthStore } from "./store/authStore";
import { ToastProvider } from "./components/ui/Toast";
import ProtectedRoute from "./components/shared/ProtectedRoute";
import DashboardLayout from "./components/layout/DashboardLayout";
// Auth
import LoginPage from "./pages/auth/LoginPage";
import RegisterPage from "./pages/auth/RegisterPage";
import ForgotPasswordPage from "./pages/auth/ForgotPasswordPage";
import ResetPasswordConfirmPage from "./pages/auth/ResetPasswordConfirmPage";
// Dashboard
import HomePage from "./pages/dashboard/HomePage";
import GalleriesPage from "./pages/dashboard/GalleriesPage";
import FavoritesPage from "./pages/dashboard/FavoritesPage";
import SettingsPage from "./pages/dashboard/SettingsPage";
import BillingPage from "./pages/subscription/BillingPage";
// Gallery workspace (own shell — no DashboardLayout)
import GalleryWorkspaceLayout from "./pages/dashboard/GalleryWorkspaceLayout";
import GalleryPhotosPage from "./pages/dashboard/GalleryPhotosPage";
import GallerySettingsPage from "./pages/dashboard/GallerySettingsPage";
import GalleryDesignPage from "./pages/dashboard/GalleryDesignPage";
import ActivitiesWorkspace from "./pages/dashboard/ActivitiesWorkspace";
// Client portal
import ClientHomePage from "./pages/client/ClientHomePage";
import ClientGalleryPage from "./pages/client/ClientGalleryPage";
import DownloadPage from "./pages/client/DownloadPage";
import DownloadFilePage from "./pages/client/DownloadFilePage";
// Public
import PricingPage from "./pages/subscription/PricingPage";
import LandingPage from "./pages/LandingPage";

/**
 * Restores the photographer's session on page load — except on the public
 * client-gallery routes (/g/...). Those visitors are guests by definition and
 * never need a session; asking anyway cost every client two requests that
 * always failed (GET /auth/me/ -> 401, then a token refresh -> 401) and a pair
 * of console errors. init() is idempotent, so if the visitor later navigates
 * (in-app) to a page that does need the session, it simply runs then.
 */
function AuthBootstrap() {
  const init = useAuthStore((s) => s.init);
  const isGuestGalleryRoute = useLocation().pathname.startsWith("/g/");

  useEffect(() => {
    if (!isGuestGalleryRoute) init();
  }, [init, isGuestGalleryRoute]);

  return null;
}

export default function App() {

  return (
    <ToastProvider>
      <BrowserRouter
        future={{
          v7_startTransition: true,
          v7_relativeSplatPath: true,
        }}
      >
        <AuthBootstrap />
        <Routes>
          {/* Public */}
          <Route path="/" element={<LandingPage />} />
          <Route path="/pricing" element={<PricingPage />} />
          <Route path="/login" element={<LoginPage />} />
          <Route path="/register" element={<RegisterPage />} />
          <Route path="/forgot-password" element={<ForgotPasswordPage />} />
          <Route
            path="/auth/password/reset/confirm/:uidb64/:token"
            element={<ResetPasswordConfirmPage />}
          />

          {/* Protected photographer dashboard */}
          <Route path="/dashboard" element={<ProtectedRoute />}>
            {/* Standard pages — keep the persistent sidebar/topbar */}
            <Route element={<DashboardLayout />}>
              <Route index element={<HomePage />} />
              <Route path="galleries" element={<GalleriesPage />} />
              <Route path="favorites" element={<FavoritesPage />} />
              <Route path="settings/:section?" element={<SettingsPage />} />
              <Route path="billing" element={<BillingPage />} />
            </Route>

            {/* Gallery workspace — full takeover, its own sidebar/chrome.
                Deliberately a SIBLING of the block above, not nested inside
                it, so DashboardLayout's global nav never renders here. */}
            <Route path="galleries/:id" element={<GalleryWorkspaceLayout />}>
              <Route index element={<GalleryPhotosPage />} />
              <Route path="design" element={<GalleryDesignPage />} />
              <Route path="settings" element={<GallerySettingsPage />} />
              <Route path="activities" element={<ActivitiesWorkspace />} />
            </Route>
          </Route>

          {/* Client portal */}
          <Route path="/g/:username" element={<ClientHomePage />} />
          <Route path="/g/:username/:slug" element={<ClientGalleryPage />} />
          <Route
            path="/g/:username/:slug/download"
            element={<DownloadPage />}
          />
          <Route
            path="/g/:username/:slug/download/file/:jobId"
            element={<DownloadFilePage />}
          />

          {/* Catch-all */}
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </BrowserRouter>
    </ToastProvider>
  );
}
