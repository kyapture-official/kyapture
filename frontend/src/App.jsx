// C:/Users/LENOVO/Desktop/kyapture/frontend/src/App.jsx
import React, { lazy, Suspense, useEffect } from "react";
import { BrowserRouter, Routes, Route, Navigate, useLocation } from "react-router-dom";
import { useAuthStore } from "./store/authStore";
import { ToastProvider } from "./components/ui/Toast";
import ProtectedRoute from "./components/shared/ProtectedRoute";
import DashboardLayout from "./components/layout/DashboardLayout";
import FeedbackWidget from "./components/shared/FeedbackWidget";
// Auth
const LoginPage = lazy(() => import("./pages/auth/LoginPage"));
const RegisterPage = lazy(() => import("./pages/auth/RegisterPage"));
const ForgotPasswordPage = lazy(() => import("./pages/auth/ForgotPasswordPage"));
const ResetPasswordConfirmPage = lazy(() => import("./pages/auth/ResetPasswordConfirmPage"));
// Dashboard
const HomePage = lazy(() => import("./pages/dashboard/HomePage"));
const GalleriesPage = lazy(() => import("./pages/dashboard/GalleriesPage"));
const FavoritesPage = lazy(() => import("./pages/dashboard/FavoritesPage"));
const SettingsPage = lazy(() => import("./pages/dashboard/SettingsPage"));
const BillingPage = lazy(() => import("./pages/subscription/BillingPage"));
const FeedbackInboxPage = lazy(() => import("./pages/dashboard/FeedbackInboxPage"));
const StaffUsersPage = lazy(() => import("./pages/dashboard/StaffUsersPage"));
const StaffAuditPage = lazy(() => import("./pages/dashboard/StaffAuditPage"));
const StaffPaymentsPage = lazy(() => import("./pages/dashboard/StaffPaymentsPage"));
// Gallery workspace (own shell — no DashboardLayout)
const GalleryWorkspaceLayout = lazy(() => import("./pages/dashboard/GalleryWorkspaceLayout"));
const GalleryPhotosPage = lazy(() => import("./pages/dashboard/GalleryPhotosPage"));
const GallerySettingsPage = lazy(() => import("./pages/dashboard/GallerySettingsPage"));
const GalleryDesignPage = lazy(() => import("./pages/dashboard/GalleryDesignPage"));
const ActivitiesWorkspace = lazy(() => import("./pages/dashboard/ActivitiesWorkspace"));
// Client portal
const ClientHomePage = lazy(() => import("./pages/client/ClientHomePage"));
const ClientGalleryPage = lazy(() => import("./pages/client/ClientGalleryPage"));
const DownloadPage = lazy(() => import("./pages/client/DownloadPage"));
const DownloadFilePage = lazy(() => import("./pages/client/DownloadFilePage"));
// Public
const PricingPage = lazy(() => import("./pages/subscription/PricingPage"));
const LandingPage = lazy(() => import("./pages/LandingPage"));

function RouteLoading() {
  return (
    <div className="flex min-h-screen items-center justify-center bg-[#FDFBF7] text-sm text-muted" role="status">
      Loading…
    </div>
  );
}

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
        <Suspense fallback={<RouteLoading />}>
          <Routes>
            {/* Public */}
            <Route path="/" element={<LandingPage />} />
          <Route path="/pricing" element={<PricingPage />} />
          <Route path="/login" element={<LoginPage />} />
          <Route path="/register" element={<RegisterPage />} />
          <Route path="/forgot-password" element={<ForgotPasswordPage />} />
          {/* 7-C: the emailed link is /reset-password#token=... (fragment, never sent to a server). */}
          <Route path="/reset-password" element={<ResetPasswordConfirmPage />} />
          {/* Links mailed before 7-C no longer work: show the "request a new link" state. */}
          <Route path="/auth/password/reset/confirm/*" element={<Navigate to="/reset-password" replace />} />

          {/* Protected photographer dashboard */}
          <Route path="/dashboard" element={<ProtectedRoute />}>
            {/* Standard pages — keep the persistent sidebar/topbar */}
            <Route element={<DashboardLayout />}>
              <Route index element={<HomePage />} />
              <Route path="galleries" element={<GalleriesPage />} />
              <Route path="favorites" element={<FavoritesPage />} />
              <Route path="settings/:section?" element={<SettingsPage />} />
              <Route path="billing" element={<BillingPage />} />
              {/* Staff inbox: the link is shown to staff only, the API enforces it (403) */}
              <Route path="feedback" element={<FeedbackInboxPage />} />
              {/* 7.5-A staff area: same rule, the API answers 403 to anyone who is not staff */}
              <Route path="staff/users" element={<StaffUsersPage />} />
              <Route path="staff/audit" element={<StaffAuditPage />} />
              <Route path="staff/payments" element={<StaffPaymentsPage />} />
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
        </Suspense>
        {/* After the routes so it is the LAST stop in tab order; signed-in photographer on /dashboard/* only */}
        <FeedbackWidget />
      </BrowserRouter>
    </ToastProvider>
  );
}
