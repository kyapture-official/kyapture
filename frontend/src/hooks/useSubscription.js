// File Location: frontend/src/hooks/useSubscription.js
// VERSION: Gold-Standard Production — Week 11 (Audit Synced)
// Resolves Bug M-1 spec drifts, eliminates anonymous 401 exceptions, and preserves render performance.

import { useState, useEffect, useCallback, useRef, useMemo } from 'react'
import { subscriptionsApi } from '../api/subscriptionsApi'
import { useAuthStore } from '../store/authStore'

// ── FREE TIER FALLBACK LIMITS ────────────────────────────────────────────────
// BUG RESOLUTION (M-1): Mapped to Mausam's backend defaults to prevent plan spec drifts.
const FREE_PLAN_LIMITS = {
  max_galleries: 3,
  max_photos_per_gallery: 50, // Aligns perfectly with backend default metrics
  storage_gb: 2,
}

/**
 * WHAT: Performance-Guarded Subscription Gating Hook
 * WHY:  Abstracts plan verification. Encapsulates guards at the execution layer to 
 *       ensure both mounting and manual refetch() calls are secure [file and folder structure.txt].
 */
export function useSubscription() {
  const isMountedRef       = useRef(false)
  const abortControllerRef = useRef(null)

  const [subscription, setSubscription] = useState(null)
  const [loading, setLoading]           = useState(true)
  const [error, setError]               = useState(null)

  // Primitive stable selectors
  const user            = useAuthStore((s) => s.user)
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated)

  useEffect(() => {
    isMountedRef.current = true
    return () => {
      isMountedRef.current = false
      abortControllerRef.current?.abort()
    }
  }, [])

  // ── ENCAPSULATED ACTION-LAYER FETCH WORKER ─────────────────────────────────
  const fetchSubscriptionStatus = useCallback(async () => {
    if (!isAuthenticated) {
      abortControllerRef.current?.abort()
      if (isMountedRef.current) {
        setSubscription(null)
        setError(null)
        setLoading(false)
      }
      return
    }

    abortControllerRef.current?.abort()
    const controller = new AbortController()
    abortControllerRef.current = controller

    setLoading(true)
    setError(null)

    try {
      const data = await subscriptionsApi.getMyPlan(controller.signal)
      if (isMountedRef.current) setSubscription(data)
    } catch (err) {
      if (err.name === 'AbortError' || err.code === 'ERR_CANCELED') return
      if (isMountedRef.current) {
        setError(err.response?.data?.detail || 'Failed to retrieve active plan limits.')
      }
    } finally {
      if (isMountedRef.current) setLoading(false)
    }
  }, [isAuthenticated])

  useEffect(() => {
    fetchSubscriptionStatus()
  }, [fetchSubscriptionStatus])

  const isSubscribed = subscription?.status === 'active' || user?.is_active_plan === true
  const plan = subscription?.plan || null

  // Reference-stable plan limits
  const limits = useMemo(() => {
    return isSubscribed && plan
      ? {
          max_galleries:          plan.max_galleries,
          max_photos_per_gallery: plan.max_photos_per_gallery,
          storage_gb:             plan.storage_gb,
        }
      : FREE_PLAN_LIMITS
  }, [isSubscribed, plan])

  // Reference-stable consumption metrics
  const usage = useMemo(() => ({
    galleriesUsed:    subscription?.galleries_used     ?? 0,
    photosUsed:        subscription?.photos_used        ?? 0,
    storageUsedGb:      subscription?.storage_used_gb    ?? 0,
    storageUsedBytes:   subscription?.storage_used_bytes ?? 0,
    daysRemaining:      subscription?.days_remaining     ?? 0,
    isExpired:          subscription?.is_expired         ?? false,
  }), [subscription])

  return {
    subscription,
    plan,
    isSubscribed,
    limits,
    usage,
    loading,
    error,
    refetch: fetchSubscriptionStatus,
  }
}