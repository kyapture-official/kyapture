import React from 'react'
import { Navigate } from 'react-router-dom'
import { useAuthStore } from '../../store/authStore'
import Spinner from '../ui/Spinner'

export default function ProtectedRoute({ children }) {
  const { isAuthenticated, loading } = useAuthStore()
  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-cream-50">
        <Spinner size="lg" />
      </div>
    )
  }
  return isAuthenticated ? children : <Navigate to="/login" replace />
}
