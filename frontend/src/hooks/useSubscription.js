import { useState, useEffect } from 'react'
import { subscriptionsApi } from '../api/subscriptionsApi'

export function useSubscription() {
  const [subscription, setSubscription] = useState(null)
  const [loading, setLoading]           = useState(true)

  useEffect(() => {
    subscriptionsApi.mySubscription()
      .then((r) => setSubscription(r.data))
      .catch(() => setSubscription(null))
      .finally(() => setLoading(false))
  }, [])

  const isActive = subscription?.status === 'active'

  return { subscription, loading, isActive }
}
