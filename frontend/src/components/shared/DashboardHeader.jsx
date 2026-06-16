/**
 * DashboardHeader — used on GalleriesPage as:
 *   <DashboardHeader onCreateClick={openModal} />
 *
 * Shows: page title, subtitle, gallery count badge, and the primary CTA.
 * Designed to sit at the top of a page that already has its own content area.
 */
export default function DashboardHeader({ onCreateClick, galleryCount }) {
  return (
    <div
      className="flex flex-col sm:flex-row sm:items-end sm:justify-between gap-4 mb-8"
      style={{ animation: 'fadeUp 0.5s ease both' }}
    >
      {/* Title block */}
      <div>
        <div className="flex items-center gap-3 mb-1">
          <h1
            style={{
              fontFamily: 'Cormorant Garamond, serif',
              fontSize: 'clamp(26px, 4vw, 36px)',
              fontWeight: 400,
              color: 'var(--ink)',
              letterSpacing: '-0.5px',
              lineHeight: 1.1,
            }}
          >
            My Galleries
          </h1>

          {/* Count badge — only renders when we actually know the count */}
          {galleryCount != null && (
            <span
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                padding: '2px 10px',
                borderRadius: 20,
                fontSize: 12,
                fontWeight: 600,
                background: 'rgba(193,127,62,0.10)',
                color: 'var(--accent)',
                border: '1px solid rgba(193,127,62,0.20)',
                fontFamily: 'Outfit, sans-serif',
                marginBottom: 2,
              }}
            >
              {galleryCount}
            </span>
          )}
        </div>

        <p style={{ fontSize: 13, color: 'var(--muted)', fontFamily: 'Outfit, sans-serif' }}>
          Create, manage, and share your photo collections with clients.
        </p>
      </div>

      {/* Primary CTA */}
      {onCreateClick && (
        <button
          type="button"
          onClick={onCreateClick}
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: 8,
            padding: '10px 20px',
            background: 'var(--ink)',
            color: 'var(--cream)',
            border: 'none',
            borderRadius: 10,
            fontSize: 14,
            fontWeight: 500,
            fontFamily: 'Outfit, sans-serif',
            cursor: 'pointer',
            transition: 'all 0.18s ease',
            whiteSpace: 'nowrap',
            flexShrink: 0,
          }}
          onMouseEnter={e => {
            e.currentTarget.style.background = 'var(--ink2)'
            e.currentTarget.style.transform = 'translateY(-1px)'
            e.currentTarget.style.boxShadow = '0 6px 20px rgba(30,26,22,0.20)'
          }}
          onMouseLeave={e => {
            e.currentTarget.style.background = 'var(--ink)'
            e.currentTarget.style.transform = 'translateY(0)'
            e.currentTarget.style.boxShadow = 'none'
          }}
        >
          {/* Plus icon */}
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none"
            stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"
            aria-hidden="true">
            <line x1="12" y1="5" x2="12" y2="19"/>
            <line x1="5" y1="12" x2="19" y2="12"/>
          </svg>
          New Gallery
        </button>
      )}
    </div>
  )
}