import React, { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { useAuthStore } from '../../store/authStore'
import { galleriesApi } from '../../api/galleriesApi'
import { subscriptionsApi } from '../../api/subscriptionsApi'
import Badge from '../../components/ui/Badge'
import { formatDate } from '../../utils/formatters'
import { SUBSCRIPTION_STATUS_COLORS } from '../../utils/constants'

export default function HomePage() {
  const { user } = useAuthStore()
  const [galleries, setGalleries] = useState([])
  const [sub, setSub] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    Promise.all([
      galleriesApi.list().then((r) => setGalleries(r.data.results || r.data)),
      subscriptionsApi.mySubscription().then((r) => setSub(r.data)).catch(() => {}),
    ]).finally(() => setLoading(false))
  }, [])

  const stats = [
    { label: 'Total Galleries', value: galleries.length },
    { label: 'Published', value: galleries.filter((g) => g.is_published).length },
    { label: 'Protected', value: galleries.filter((g) => g.is_password_protected).length },
    { label: 'Plan', value: sub ? sub.plan?.name : 'Free' },
  ]

  return (
    <div>
      {/* Greeting */}
      <div className="mb-10 animate-fade-up">
        <h1 className="font-serif text-4xl text-ink mb-1">
          Good morning, {user?.display_name?.split(' ')[0] || user?.username} ✦
        </h1>
        <p className="text-muted text-sm">
          Your studio at{' '}
          <code className="bg-cream-200 px-1.5 py-0.5 rounded text-xs text-ink">
            {user?.username}.kyapture.com
          </code>
        </p>
      </div>

      {/* Stats */}
      {!loading && (
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-10 animate-fade-up delay-100">
          {stats.map((s) => (
            <div key={s.label} className="bg-white rounded-2xl border border-cream-200 p-5">
              <p className="text-xs text-muted mb-1">{s.label}</p>
              <p className="font-serif text-3xl text-ink">{s.value}</p>
            </div>
          ))}
        </div>
      )}

      {/* Subscription status */}
      {sub && (
        <div className="mb-10 animate-fade-up delay-200 bg-white rounded-2xl border border-cream-200 p-5 flex items-center justify-between">
          <div>
            <p className="text-sm font-medium text-ink mb-1">{sub.plan?.name} Plan</p>
            <p className="text-xs text-muted">
              Expires {formatDate(sub.expires_at)} · via {sub.payment_method}
            </p>
          </div>
          <Badge
            variant={sub.status === 'active' ? 'success' : sub.status === 'pending' ? 'warning' : 'danger'}
          >
            {sub.status}
          </Badge>
        </div>
      )}

      {/* Recent galleries */}
      <div className="animate-fade-up delay-300">
        <div className="flex items-center justify-between mb-5">
          <h2 className="font-serif text-2xl text-ink">Recent Galleries</h2>
          <Link to="/dashboard/galleries" className="text-sm text-muted hover:text-ink underline underline-offset-2">
            View all
          </Link>
        </div>

        {loading ? (
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            {[1,2,3].map(i => (
              <div key={i} className="skeleton h-40 rounded-2xl" />
            ))}
          </div>
        ) : galleries.length === 0 ? (
          <div className="py-16 text-center bg-white rounded-2xl border border-cream-200 border-dashed">
            <p className="text-muted text-sm mb-4">No galleries yet. Create your first one.</p>
            <Link
              to="/dashboard/galleries"
              className="inline-flex items-center gap-2 bg-ink text-cream-50 px-5 py-2.5 rounded-xl text-sm font-medium hover:bg-stone-700 transition-colors"
            >
              Create Gallery
            </Link>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            {galleries.slice(0, 6).map((gallery) => (
              <Link
                key={gallery.id}
                to={`/dashboard/galleries/${gallery.id}`}
                className="group bg-white rounded-2xl border border-cream-200 overflow-hidden hover:border-cream-400 hover:shadow-sm transition-all duration-200"
              >
                <div className="h-36 bg-cream-100 relative overflow-hidden">
                  {gallery.cover_photo ? (
                    <img
                      src={gallery.cover_photo.thumbnail || gallery.cover_photo.image}
                      alt=""
                      className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-500"
                    />
                  ) : (
                    <div className="w-full h-full flex items-center justify-center text-cream-300">
                      <svg className="w-10 h-10" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1}
                          d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z"/>
                      </svg>
                    </div>
                  )}
                  <div
                    className="absolute top-2 right-2 w-3 h-3 rounded-full"
                    style={{ backgroundColor: gallery.branding_color }}
                  />
                </div>
                <div className="p-4">
                  <p className="font-medium text-ink text-sm truncate mb-1">{gallery.title}</p>
                  <div className="flex items-center gap-2">
                    <Badge variant={gallery.is_published ? 'success' : 'default'}>
                      {gallery.is_published ? 'Published' : 'Draft'}
                    </Badge>
                    {gallery.is_password_protected && (
                      <Badge variant="warning">Protected</Badge>
                    )}
                  </div>
                </div>
              </Link>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
