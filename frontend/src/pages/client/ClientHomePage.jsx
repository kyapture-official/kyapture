import React, { useEffect, useState } from 'react'
import { useParams, Link } from 'react-router-dom'
import { clientsApi } from '../../api/clientsApi'
import ClientLayout from '../../components/layout/ClientLayout'
import Spinner from '../../components/ui/Spinner'
import Badge from '../../components/ui/Badge'

export default function ClientHomePage() {
  const { username } = useParams()
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    clientsApi.listGalleries(username)
      .then((r) => setData(r.data))
      .catch(() => setError('Photographer not found.'))
      .finally(() => setLoading(false))
  }, [username])

  if (loading) return (
    <div className="min-h-screen bg-cream-50 flex items-center justify-center">
      <Spinner size="lg" />
    </div>
  )

  if (error) return (
    <div className="min-h-screen bg-cream-50 flex items-center justify-center">
      <p className="text-muted">{error}</p>
    </div>
  )

  const { photographer, galleries } = data || {}

  return (
    <ClientLayout photographer={photographer}>
      {/* Hero */}
      <div className="text-center py-16 animate-fade-up">
        {photographer?.avatar && (
          <img
            src={photographer.avatar}
            alt=""
            className="w-20 h-20 rounded-full object-cover mx-auto mb-5 ring-4 ring-cream-200"
          />
        )}
        <h1 className="font-serif text-5xl text-ink mb-3">
          {photographer?.display_name || photographer?.username}
        </h1>
        {photographer?.bio && (
          <p className="text-muted text-sm max-w-md mx-auto leading-relaxed">{photographer.bio}</p>
        )}
      </div>

      {/* Galleries */}
      {galleries?.length === 0 ? (
        <p className="text-center text-muted py-12">No galleries available yet.</p>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-5 animate-fade-up delay-200">
          {galleries?.map((gallery, i) => (
            <Link
              key={gallery.id}
              to={`/${username}/${gallery.slug}`}
              className="group bg-white rounded-2xl border border-cream-200 overflow-hidden hover:shadow-md hover:border-cream-300 transition-all duration-300"
              style={{ animationDelay: `${i * 0.06}s` }}
            >
              <div className="h-48 bg-cream-100 overflow-hidden relative">
                {gallery.cover_photo ? (
                  <img
                    src={gallery.cover_photo.thumbnail || gallery.cover_photo.image}
                    alt=""
                    className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-700"
                  />
                ) : (
                  <div className="w-full h-full" style={{ background: gallery.branding_color + '20' }} />
                )}
                <div
                  className="absolute bottom-0 left-0 right-0 h-1"
                  style={{ backgroundColor: gallery.branding_color }}
                />
                {gallery.is_password_protected && (
                  <div className="absolute top-3 right-3 bg-white/90 rounded-lg p-1.5">
                    <svg className="w-4 h-4 text-ink" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                        d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z"/>
                    </svg>
                  </div>
                )}
              </div>
              <div className="p-4">
                <p className="font-medium text-ink group-hover:text-stone-700">{gallery.title}</p>
                {gallery.description && (
                  <p className="text-xs text-muted mt-1 line-clamp-2">{gallery.description}</p>
                )}
              </div>
            </Link>
          ))}
        </div>
      )}
    </ClientLayout>
  )
}
