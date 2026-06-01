import React, { useState } from 'react'
import { useParams, Link } from 'react-router-dom'
import { clientsApi } from '../../api/clientsApi'
import ClientLayout from '../../components/layout/ClientLayout'
import Button from '../../components/ui/Button'
import { useClientStore } from '../../store/clientStore'

export default function DownloadPage() {
  const { username, slug } = useParams()
  const { sessions } = useClientStore()
  const token = sessions[slug]

  const [status, setStatus] = useState('idle') // idle | loading | success | error
  const [downloadUrl, setDownloadUrl] = useState(null)

  const handleRequest = async () => {
    if (!token) {
      setStatus('error')
      return
    }
    setStatus('loading')
    try {
      const { data } = await clientsApi.requestDownload(token, slug)
      setDownloadUrl(data.download_url)
      setStatus('success')
    } catch (err) {
      setStatus(err.response?.status === 403 ? 'forbidden' : 'error')
    }
  }

  return (
    <ClientLayout>
      <div className="max-w-md mx-auto py-24 text-center animate-fade-up">
        {/* Icon */}
        <div className="w-20 h-20 bg-cream-100 rounded-full flex items-center justify-center mx-auto mb-8">
          <svg className="w-9 h-9 text-cream-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
              d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
          </svg>
        </div>

        {status === 'idle' && (
          <>
            <h1 className="font-serif text-4xl text-ink mb-3">Download Gallery</h1>
            <p className="text-muted text-sm mb-8 leading-relaxed">
              Your photographer has enabled downloads for this gallery.
              Click below to request your download package.
            </p>
            <Button onClick={handleRequest} size="lg" className="mx-auto">
              Request Download
            </Button>
            <p className="mt-4 text-xs text-muted">
              All original resolution photos will be packaged for you.
            </p>
          </>
        )}

        {status === 'loading' && (
          <>
            <h1 className="font-serif text-4xl text-ink mb-3">Preparing…</h1>
            <p className="text-muted text-sm mb-6">
              We're packaging your photos. This may take a moment.
            </p>
            <div className="flex justify-center">
              <svg className="animate-spin h-8 w-8 text-cream-400" viewBox="0 0 24 24" fill="none">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="3" />
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8z" />
              </svg>
            </div>
          </>
        )}

        {status === 'success' && (
          <>
            <h1 className="font-serif text-4xl text-ink mb-3">Ready!</h1>
            <p className="text-muted text-sm mb-8">
              Your photos are ready to download. The link will expire after use.
            </p>
            <a
              href={downloadUrl}
              download
              className="inline-flex items-center gap-2 bg-ink text-cream-50 px-8 py-3.5 rounded-xl text-sm font-medium hover:bg-stone-700 transition-colors"
            >
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                  d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
              </svg>
              Download Now
            </a>
          </>
        )}

        {status === 'forbidden' && (
          <>
            <h1 className="font-serif text-4xl text-ink mb-3">Not Available</h1>
            <p className="text-muted text-sm mb-6">
              Downloads are not enabled for this gallery, or your session has expired.
              Please contact your photographer.
            </p>
            <Link
              to={`/p/${username}/${slug}`}
              className="text-sm text-ink underline underline-offset-2"
            >
              ← Back to gallery
            </Link>
          </>
        )}

        {status === 'error' && (
          <>
            <h1 className="font-serif text-4xl text-ink mb-3">Something went wrong</h1>
            <p className="text-muted text-sm mb-6">
              We couldn't process your download request. Please try again or contact your photographer.
            </p>
            <div className="flex gap-3 justify-center">
              <Button onClick={() => setStatus('idle')} variant="secondary">
                Try again
              </Button>
              <Link
                to={`/p/${username}/${slug}`}
                className="inline-flex items-center px-5 py-2.5 text-sm text-ink border border-cream-300 rounded-lg hover:border-cream-400"
              >
                Back to gallery
              </Link>
            </div>
          </>
        )}
      </div>
    </ClientLayout>
  )
}
