// File Location: frontend/src/pages/subscription/PricingPage.jsx
// VERSION: Gold-Standard Production — Week 11
// Fixes primitive Zustand selectors and prevents redundant background re-renders.

import { useState, useEffect, useRef } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { subscriptionsApi } from '../../api/subscriptionsApi'
import { useSubscription } from '../../hooks/useSubscription'
import { useAuthStore } from '../../store/authStore'
import { useToast } from '../../components/ui/Toast'
import { formatCurrency } from '../../utils/formatters'
import Spinner from '../../components/ui/Spinner'

export default function PricingPage() {
  const toast = useToast()
  const navigate = useNavigate()

  const { plan: activePlan, isSubscribed, loading: subLoading } = useSubscription()

  // BUG RESOLUTION: Splitting the Zustand object selector into two individual selectors
  // returns stable primitive/function references. This prevents the component from
  // re-rendering on unrelated store updates, dramatically improving performance.
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated)
  const logout           = useAuthStore((s) => s.logout)

  const [plans, setPlans]     = useState([])
  const [loading, setLoading] = useState(true)
  const isMountedRef = useRef(false)

  // 1. Fetch available plan configurations on mount
  useEffect(() => {
    isMountedRef.current = true

    subscriptionsApi.getPlans()
      .then((data) => {
        if (isMountedRef.current) {
          // getPlans() already unwraps res.data internally. We default to a flat
          // array in case the unpaginated view structure changes.
          setPlans(data.results || data || [])
        }
      })
      .catch(() => {
        if (isMountedRef.current) {
          toast('Failed to load active plan configurations.', 'error')
        }
      })
      .finally(() => {
        if (isMountedRef.current) setLoading(false)
      })

    return () => {
      isMountedRef.current = false
    }
  }, [toast])

  // 2. Select Plan and Route with Handshake parameters
  const handleSelectPlan = (planId) => {
    if (isAuthenticated) {
      navigate(`/dashboard/billing?plan_id=${planId}`)
    } else {
      navigate(`/register?plan_id=${planId}`)
    }
  }

  if (loading || subLoading) {
    return (
      <div className="min-h-screen bg-[#F0EBE3] flex items-center justify-center">
        <Spinner size="lg" className="text-[#2C2825]" />
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-[#F0EBE3] text-[#2C2825] font-sans pb-20">

      {/* Sticky Top Glass Header */}
      <header className="sticky top-0 z-50 px-8 py-4 flex items-center justify-between border-b border-[#E8DECE] backdrop-blur-md bg-[#FDFAF5]/90 transition-all duration-300">
        <Link to="/" className="flex items-center gap-2.5 group">
          <div className="w-8 h-8 rounded-xl flex items-center justify-center text-base bg-[#8C6B35] group-hover:scale-105 transition-transform">
            📷
          </div>
          <span className="font-serif text-xl text-[#2C2825] tracking-tight">Kyapture</span>
        </Link>

        <nav className="flex items-center gap-6 text-sm" role="navigation">
          {isAuthenticated ? (
            <>
              <Link to="/dashboard" className="text-[#8C847A] hover:text-[#2C2825] transition-colors font-medium">
                Dashboard
              </Link>
              <button
                type="button"
                onClick={logout}
                className="text-[#8C847A] hover:text-[#2C2825] transition-colors font-medium cursor-pointer focus:outline-none"
              >
                Sign out
              </button>
            </>
          ) : (
            <>
              <Link to="/login" className="text-[#8C847A] hover:text-[#2C2825] transition-colors font-medium">
                Sign in
              </Link>
              <Link
                to="/register"
                className="px-5 py-2.5 rounded-full text-xs uppercase tracking-widest font-semibold bg-[#2C2825] text-[#FDFAF5] hover:bg-[#3d3530] transition-all shadow-sm"
              >
                Get Started Free
              </Link>
            </>
          )}
        </nav>
      </header>

      {/* Pricing comparison section */}
      <main className="max-w-5xl mx-auto px-6 pt-20">
        <div className="text-center mb-16 animate-fadeUp">
          <p className="text-[10px] font-bold tracking-[0.2em] mb-4 text-[#C09A55] uppercase font-sans">PRICING</p>
          <h1 className="font-serif mb-4 text-4xl sm:text-5xl lg:text-6xl text-[#2C2825] tracking-tight">Simple Pricing</h1>
          <p className="text-base text-[#8C847A] leading-relaxed max-w-md mx-auto font-light">
            Pay via eSewa, Khalti, or bank transfer [weekly tasks.txt]. Manual verification within 24 hours.
          </p>
        </div>

        {/* Pricing Cards Grid */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6 animate-fadeUp [animation-delay:0.1s]">
          {plans.map((plan) => {
            const isCurrentPlan = activePlan?.id === plan.id
            const isPopular = plan.name?.toLowerCase() === 'pro'

            return (
              <section
                key={plan.id}
                aria-describedby={`plan-desc-${plan.id}`}
                className={`rounded-3xl p-8 flex flex-col justify-between border transition-all duration-300 ${
                  isPopular
                    ? 'bg-[#2C2825] border-[#2C2825] shadow-2xl scale-[1.04] z-10 text-[#FDFAF5]'
                    : 'bg-white border-[#F4E8CC] hover:border-[#E8DECE] text-[#2C2825]'
                }`}
              >
                <div className="space-y-6">
                  {isPopular && (
                    <span className="text-[10px] px-3.5 py-1 rounded-full w-fit font-bold bg-[#C09A55] text-white uppercase tracking-widest block shadow-sm">
                      Most Popular
                    </span>
                  )}
                  <h2 className="font-serif text-2xl font-medium">
                    {plan.name}
                  </h2>
                  <p className="font-serif text-5xl tracking-tight flex items-baseline gap-1" style={{ color: isPopular ? '#EDD9AA' : '#2C2825' }}>
                    {formatCurrency(plan.price)}
                    <span className="text-xs font-sans text-[#8C847A]">/30 days</span>
                  </p>

                  <div className={`h-px w-full ${isPopular ? 'bg-cream-100/10' : 'bg-cream-200'}`} />

                  <ul id={`plan-desc-${plan.id}`} className="flex flex-col gap-3.5 text-xs font-light" style={{ color: isPopular ? '#D9BB80' : '#8C847A' }}>
                    <li className="flex items-center gap-2">
                      <span className="text-[#C09A55] font-bold">✓</span>
                      <span>Max Collections: <strong className="font-semibold">{plan.max_galleries}</strong></span>
                    </li>
                    <li className="flex items-center gap-2">
                      <span className="text-[#C09A55] font-bold">✓</span>
                      <span>Photos per Gallery: <strong className="font-semibold">{plan.max_photos_per_gallery}</strong></span>
                    </li>
                    <li className="flex items-center gap-2">
                      <span className="text-[#C09A55] font-bold">✓</span>
                      <span>Cloud Storage: <strong className="font-semibold">{plan.storage_gb} GB</strong></span>
                    </li>
                    <li className="flex items-center gap-2">
                      <span className="text-[#C09A55] font-bold">✓</span>
                      Password-protected galleries
                    </li>
                    <li className="flex items-center gap-2">
                      <span className="text-[#C09A55] font-bold">✓</span>
                      Client download controls
                    </li>
                  </ul>
                </div>

                {/* Checkout Trigger button */}
                <div className="pt-8">
                  {isCurrentPlan ? (
                    <div className="w-full text-center py-3 bg-[#C09A55]/10 border border-[#C09A55]/30 text-[#C09A55] rounded-full text-xs uppercase tracking-widest font-semibold flex items-center justify-center gap-1.5 select-none">
                      <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5} aria-hidden="true">
                        <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                      </svg>
                      Your Active Plan
                    </div>
                  ) : (
                    <button
                      type="button"
                      onClick={() => handleSelectPlan(plan.id)}
                      className="w-full text-center py-3 rounded-full text-xs uppercase tracking-widest font-bold transition-all active:scale-[0.98] cursor-pointer"
                      style={isPopular
                        ? { background: '#C09A55', color: 'white' }
                        : { border: '1px solid #2C2825', color: '#2C2825' }
                      }
                    >
                      {isAuthenticated ? 'Upgrade Plan' : 'Get Started'}
                    </button>
                  )}
                </div>
              </section>
            )
          })}
        </div>

        {/* Dynamic subdomain badge */}
        <p className="text-center text-xs mt-16 text-[#8C847A] font-light">
          All plans include your own multi-tenant subdomain at{' '}
          <code className="px-2 py-0.5 rounded text-xs font-mono font-bold bg-[#F4E8CC] text-[#2C2825]">
            username.kyapture.com
          </code>
        </p>
      </main>
    </div>
  )
}