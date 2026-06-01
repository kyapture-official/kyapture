import React, { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { clientsApi } from '../../api/clientsApi'
import ClientLayout from '../../components/layout/ClientLayout'
import PhotoGrid from '../../components/shared/PhotoGrid'
import PasswordModal from '../../components/shared/PasswordModal'
import Button from '../../components/ui/Button'
import Spinner from '../../components/ui/Spinner'
import { useClientStore } from '../../store/clientStore'

export default function ClientGalleryPage() {
  const { username, slug } = useParams()
  const { sessions, setSession } = useClientStore()
  const token = sessions[slug]

  const [gallery, setGallery] = useState(null)
  const [photos, setPhotos] = useState([])
  const [loading, setLoading] = useState(true)
  const [locked, setLocked] = useState(false)
  const [pwLoading, setPwLoading] = useState(false)
  const [pwError, setPwError] = useState(null)

  useEffect(() => {
    clientsApi.getGallery(username, slug)
      .then((r) => {
        setGallery(r.data.gallery)
        setPhotos(r.data.photos || [])
        setLocked(false)
      })
      .catch((err) => {
        if (err.response?.status === 403) setLocked(true)
      })
      .finally(() => setLoading(false))
  }, [username, slug, token])

  const handleUnlock = async (password) => {
    setPwLoading(true)
    setPwError(null)
    try {
      const { data } = await clientsApi.unlock(username, slug, password)
      setSession(slug, data.access_token)
      setGallery(data.gallery)
      setPhotos(data.photos || [])
      setLocked(false)
    } catch {
      setPwError('Incorrect password. Please try again.')
    } finally {
      setPwLoading(false)
    }
  }

  if (loading) return (
    <div className="min-h-screen bg-cream-50 flex items-center justify-center">
      <Spinner size="lg" />
    </div>
  )

  return (
    <ClientLayout photographer={gallery?.photographer}>
      <PasswordModal
        open={locked}
        onSubmit={handleUnlock}
        error={pwError}
        loading={pwLoading}
      />

      {gallery && (
        <>
          {/* Gallery header */}
          <div className="mb-10 animate-fade-up">
            <div className="flex items-start justify-between">
              <div>
                <h1 className="font-serif text-4xl text-ink mb-2">{gallery.title}</h1>
                {gallery.description && (
                  <p className="text-muted text-sm leading-relaxed max-w-lg">{gallery.description}</p>
                )}
              </div>
              {gallery.allow_download && (
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => alert('Download will be available after photographer enables it for your session.')}
                >
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
                      d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4"/>
                  </svg>
                  Download All
                </Button>
              )}
            </div>
            <div className="mt-3 h-1 w-16 rounded-full" style={{ backgroundColor: gallery.branding_color }} />
          </div>

          {/* Photos */}
          <div className="animate-fade-up delay-200">
            <PhotoGrid photos={photos} />
          </div>

          {photos.length > 0 && (
            <p className="text-center text-xs text-muted mt-8">
              {photos.length} photos in this gallery
            </p>
          )}
        </>
      )}
    </ClientLayout>
  )
}
