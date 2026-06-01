import React from 'react'
import { Link } from 'react-router-dom'
import { useAuthStore } from '../../store/authStore'

/**
 * Wraps dashboard features that require an active subscription.
 * If user has no active plan, shows a prompt to subscribe.
 */
export default function SubscriptionGuard({ children, feature = 'this feature' }) {
  const { user } = useAuthStore()

  if (user?.is_active_plan) return children

  return (
    <div className="py-20 text-center max-w-md mx-auto animate-fade-up">
      <div className="w-16 h-16 bg-amber-50 border border-amber-100 rounded-full flex items-center justify-center mx-auto mb-6">
        <svg className="w-7 h-7 text-amber-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
            d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
        </svg>
      </div>
      <h2 className="font-serif text-3xl text-ink mb-3">Subscription Required</h2>
      <p className="text-muted text-sm leading-relaxed mb-8">
        You need an active subscription plan to access {feature}.
        Choose a plan that fits your workflow.
      </p>
      <div className="flex gap-3 justify-center">
        <Link
          to="/dashboard/billing"
          className="bg-ink text-cream-50 px-6 py-2.5 rounded-xl text-sm font-medium hover:bg-stone-700 transition-colors"
        >
          View Plans
        </Link>
        <Link
          to="/dashboard"
          className="border border-cream-300 text-ink px-6 py-2.5 rounded-xl text-sm hover:border-cream-400 transition-colors"
        >
          Go to Dashboard
        </Link>
      </div>
    </div>
  )
}
