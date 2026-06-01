import React from 'react'

export default function ClientLayout({ children, photographer }) {
  return (
    <div className="min-h-screen bg-cream-50">
      {/* Minimal header */}
      <header className="border-b border-cream-200 bg-white/80 backdrop-blur-sm sticky top-0 z-10">
        <div className="max-w-5xl mx-auto px-6 py-4 flex items-center justify-between">
          <div>
            {photographer && (
              <span className="font-serif text-xl text-ink">
                {photographer.display_name || photographer.username}
              </span>
            )}
          </div>
          <div className="text-xs text-muted">Delivered via Kyapture</div>
        </div>
      </header>
      <main className="max-w-5xl mx-auto px-4 py-8">
        {children}
      </main>
      <footer className="text-center py-8 text-xs text-muted border-t border-cream-200 mt-12">
        Powered by <span className="font-serif text-sm text-ink">Kyapture</span>
      </footer>
    </div>
  )
}
