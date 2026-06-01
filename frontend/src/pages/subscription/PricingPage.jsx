import React, { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { subscriptionsApi } from '../../api/subscriptionsApi'
import { formatCurrency } from '../../utils/formatters'
import Spinner from '../../components/ui/Spinner'

export default function PricingPage() {
  const [plans, setPlans] = useState([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    subscriptionsApi.plans()
      .then((r) => setPlans(r.data.results || r.data))
      .finally(() => setLoading(false))
  }, [])

  return (
    <div className="min-h-screen" style={{ background: '#F0EBE3' }}>
      {/* Nav */}
      <header style={{ borderBottom: '1px solid #E8DECE', background: 'rgba(253,250,245,0.9)', backdropFilter: 'blur(12px)' }}
        className="sticky top-0 z-50 px-8 py-4 flex items-center justify-between">
        <Link to="/" className="flex items-center gap-2.5">
          <div className="w-8 h-8 rounded-xl flex items-center justify-center text-base" style={{ background: '#8C6B35' }}>📷</div>
          <span className="font-serif text-xl" style={{ color: '#2C2825' }}>Kyapture</span>
        </Link>
        <div className="flex items-center gap-4 text-sm">
          <Link to="/login" className="transition-colors" style={{ color: '#8C847A' }}
            onMouseEnter={e => e.target.style.color = '#2C2825'}
            onMouseLeave={e => e.target.style.color = '#8C847A'}>
            Sign in
          </Link>
          <Link to="/register"
            className="px-5 py-2 rounded-full text-sm font-medium transition-all"
            style={{ background: '#2C2825', color: '#FDFAF5' }}
            onMouseEnter={e => e.currentTarget.style.background = '#3d3530'}
            onMouseLeave={e => e.currentTarget.style.background = '#2C2825'}>
            Get started free →
          </Link>
        </div>
      </header>

      <main className="max-w-5xl mx-auto px-6 py-20">
        <div className="text-center mb-16 animate-fade-up">
          <p className="text-xs font-semibold tracking-[0.2em] mb-4" style={{ color: '#C09A55' }}>PRICING</p>
          <h1 className="font-serif mb-4" style={{ fontSize: 'clamp(40px, 6vw, 64px)', color: '#2C2825' }}>Simple pricing</h1>
          <p className="text-lg" style={{ color: '#8C847A' }}>
            Pay via eSewa, Khalti, or bank transfer. Manual review within 24 hours.
          </p>
        </div>

        {loading ? (
          <div className="flex justify-center py-20"><Spinner size="lg" /></div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6 animate-fade-up delay-200">
            {plans.map((plan, i) => (
              <div
                key={plan.id}
                className="rounded-3xl p-8 flex flex-col transition-all"
                style={{
                  background: i === 1 ? '#2C2825' : 'white',
                  border: i === 1 ? '1px solid #2C2825' : '1px solid #F4E8CC',
                  transform: i === 1 ? 'scale(1.04)' : 'scale(1)',
                  boxShadow: i === 1 ? '0 20px 40px rgba(44,40,37,0.2)' : 'none',
                }}
              >
                {i === 1 && (
                  <span className="text-xs px-3 py-1 rounded-full w-fit mb-4 font-medium"
                    style={{ background: '#C09A55', color: 'white' }}>
                    Most Popular
                  </span>
                )}
                <h2 className="font-serif text-2xl mb-2" style={{ color: i === 1 ? '#FDFAF5' : '#2C2825' }}>
                  {plan.name}
                </h2>
                <p className="font-serif text-5xl mb-6" style={{ color: i === 1 ? '#EDD9AA' : '#2C2825' }}>
                  {formatCurrency(plan.price)}
                  <span className="text-sm font-sans" style={{ color: i === 1 ? '#8C847A' : '#8C847A' }}>/mo</span>
                </p>
                <ul className="flex flex-col gap-3 text-sm mb-8 flex-1" style={{ color: i === 1 ? '#D9BB80' : '#8C847A' }}>
                  <li className="flex items-center gap-2">
                    <span style={{ color: '#C09A55' }}>✓</span>
                    {plan.max_galleries} galleries
                  </li>
                  <li className="flex items-center gap-2">
                    <span style={{ color: '#C09A55' }}>✓</span>
                    {plan.max_photos_per_gallery} photos per gallery
                  </li>
                  <li className="flex items-center gap-2">
                    <span style={{ color: '#C09A55' }}>✓</span>
                    {plan.storage_gb} GB storage
                  </li>
                  <li className="flex items-center gap-2">
                    <span style={{ color: '#C09A55' }}>✓</span>
                    Password-protected galleries
                  </li>
                  <li className="flex items-center gap-2">
                    <span style={{ color: '#C09A55' }}>✓</span>
                    Client download controls
                  </li>
                </ul>
                <Link
                  to="/register"
                  className="text-center py-3 rounded-full text-sm font-semibold transition-all"
                  style={i === 1
                    ? { background: '#C09A55', color: 'white' }
                    : { border: '1px solid #2C2825', color: '#2C2825' }
                  }
                >
                  Get started
                </Link>
              </div>
            ))}
          </div>
        )}

        {/* Footer note */}
        <p className="text-center text-sm mt-16" style={{ color: '#8C847A' }}>
          All plans include your own subdomain at{' '}
          <code className="px-1.5 py-0.5 rounded text-xs" style={{ background: '#F4E8CC', color: '#2C2825' }}>
            username.kyapture.com
          </code>
        </p>
      </main>
    </div>
  )
}
