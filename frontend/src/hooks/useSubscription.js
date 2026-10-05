// frontend/src/hooks/useSubscription.js

import { useState, useEffect, useCallback, useRef, useMemo } from 'react'
import { subscriptionsApi } from '../api/subscriptionsApi'
import { useAuthStore } from '../store/authStore'

// No numbers here: plan limits are owner-editable data served by the API
// (plans / my-subscription / dashboard stats). Without a live paid plan this
// reads as "no video"; the usage endpoint (hooks/usePlanUsage) is the
// authoritative answer for the Free plan's own allowance.
const FREE_PLAN_LIMITS = {
  max_galleries: null,
  storage_gb: null,
  allow_video: false,
}

// Paid, plan-gated features. The server is the source of truth: it computes
// these from the live subscription (active AND unexpired plan flagged for the
// feature) and sends them with /subscriptions/my-subscription/. Until that
// answer arrives — or if it fails — everything reads as locked, so the UI can
// never offer a feature the API would refuse. The API enforces regardless.
const NO_ENTITLEMENTS = { branding: false, watermark: false, original_download: false }


export function useSubscription() {
  const isMountedRef       = useRef(false)
  const abortControllerRef = useRef(null)

  const [subscription, setSubscription] = useState(null)
  const [loading, setLoading]           = useState(true)
  const [error, setError]               = useState(null)

  const user            = useAuthStore((s) => s.user)
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated)

  useEffect(() => {
    isMountedRef.current = true
    return () => {
      isMountedRef.current = false
      abortControllerRef.current?.abort()
    }
  }, [])

  // GUARD FIX: the previous version moved this check into a separate
  // useEffect wrapping fetchSubscriptionStatus, leaving the function itself
  // unconditional. That correctly stops the doomed 401 on MOUNT, but
  // fetchSubscriptionStatus is also returned as `refetch` — part of this
  // hook's public API. Any future caller invoking refetch() directly
  // (e.g. a manual "refresh" button, or a stale closure firing after
  // logout) would bypass the mount-effect guard entirely and fire the
  // request anyway, since the function itself has no awareness of auth
  // state.
  //
  // Putting the check inside fetchSubscriptionStatus itself makes it the
  // single source of truth: the mount effect, a manual refetch() call, and
  // any future consumer all inherit the same guarantee automatically,
  // instead of every call site needing to remember to check isAuthenticated
  // before calling refetch().
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

  const limits = useMemo(() => {
    return isSubscribed && plan
      ? {
          max_galleries:          plan.max_collections,
          storage_gb:             plan.storage_gb,
          // The plan row's video minutes: 0 = no video, empty = unlimited, N = N minutes.
          allow_video:            plan.video_minutes !== 0,
        }
      : FREE_PLAN_LIMITS
  }, [isSubscribed, plan])

  const entitlements = useMemo(
    () => ({ ...NO_ENTITLEMENTS, ...(subscription?.entitlements || {}) }),
    [subscription],
  )

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
    entitlements,
    usage,
    loading,
    error,
    refetch: fetchSubscriptionStatus,
  }
}
