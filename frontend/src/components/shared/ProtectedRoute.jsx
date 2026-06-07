import React from 'react'
import { Navigate, useLocation, Outlet } from 'react-router-dom'
import { useAuthStore } from '../../store/authStore'
import Spinner from '../ui/Spinner'

export default function ProtectedRoute({ children }) {
  // Targeted selectors — this component re-renders only when these two values change
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated)
  const loading         = useAuthStore((s) => s.loading)
  const location = useLocation()

  // Phase 1: Hold rendering until App.jsx's init() resolves the session
  if (loading) {
    return (
      <div
        className="min-h-screen flex items-center justify-center bg-cream-50"
        role="status"
        aria-live="polite"
        aria-busy="true"
      >
        <div className="flex flex-col items-center gap-4">
          <Spinner size="lg" />
          <span className="sr-only">Validating session, please wait…</span>
        </div>
      </div>
    )
  }

  // Phase 2: Redirect unauthenticated users, preserving the intended destination
  if (!isAuthenticated) {
    return <Navigate to="/login" state={{ from: location }} replace />
  }

  // Phase 3: Render children (wrap pattern) or nested Outlet (layout pattern)
  return children ?? <Outlet />
}