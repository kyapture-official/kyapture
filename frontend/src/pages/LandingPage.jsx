import React, { useState, useEffect } from 'react'
import { Link } from 'react-router-dom'

const FEATURES = [
  { icon: '🖼️', title: 'Beautiful galleries', desc: 'Masonry layout, lightbox view, lazy loading — your photos always shine.' },
  { icon: '🔒', title: 'Password protection', desc: 'Lock any gallery so only your clients can access their photos.' },
  { icon: '⬇️', title: 'Smart downloads', desc: 'Clients download full-resolution ZIPs. Capture their email automatically.' },
  { icon: '🎨', title: 'Your brand', desc: 'Custom logo, accent color, watermark. Every gallery screams you.' },
  { icon: '🔗', title: 'Shareable links', desc: 'username.kyapture.com/your-slug — send it and forget.' },
  { icon: '📊', title: 'Analytics', desc: 'Track views, downloads, and client activity in real time.' },
]

export default function LandingPage() {
  const [scrolled, setScrolled] = useState(false)
  const [menuOpen, setMenuOpen] = useState(false)
  const [displayCount, setDisplayCount] = useState(0)
  const [recentUsers, setRecentUsers] = useState([])

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 20)
    window.addEventListener('scroll', onScroll)
    return () => window.removeEventListener('scroll', onScroll)
  }, [])

  useEffect(() => {
    const fetchUsers = async () => {
      try {
        const response = await fetch('/api/total-users')
        if (response.ok) {
          const data = await response.json()
          setDisplayCount(data.total_count)
          setRecentUsers(data.latest_users)
        }
      } catch {
        setDisplayCount(0)
        setRecentUsers([
          { initial: 'A', color: '#8c6d4f' },
          { initial: 'S', color: '#4a7c6f' },
        ])
      }
    }
    fetchUsers()
  }, [])

  return (
    <div className="landing">
      {/* ===== NAVBAR ===== */}
      <nav className={`navbar ${scrolled ? 'navbar--scrolled' : ''}`}>
        <Link to="/" className="navbar__logo">
          <div className="navbar__logo-icon">📸</div>
          <span>Kyapture</span>
        </Link>

        <div className="navbar__links">
          <a href="#features" className="navbar__link">Features</a>
          <a href="#pricing" className="navbar__link">Pricing</a>
          <a href="#about" className="navbar__link">About</a>
          <Link to="/login" className="navbar__link">Sign in</Link>
          <Link to="/register" className="navbar__cta">Get started free →</Link>
        </div>

        <button className="navbar__burger" onClick={() => setMenuOpen(o => !o)}>
          {menuOpen ? '✕' : '☰'}
        </button>

        {menuOpen && (
          <div className="navbar__mobile">
            <a href="#features" onClick={() => setMenuOpen(false)}>Features</a>
            <a href="#pricing" onClick={() => setMenuOpen(false)}>Pricing</a>
            <Link to="/login" onClick={() => setMenuOpen(false)}>Sign in</Link>
            <Link to="/register" onClick={() => setMenuOpen(false)}>Create account</Link>
          </div>
        )}
      </nav>

      {/* ===== HERO ===== */}
      <section className="hero">
        <div className="hero__bg" />
        <div className="hero__grid" />

        <div className="hero__content animate-fadeUp">
          <div className="hero__eyebrow">✦ Built for photographers</div>

          <h1 className="hero__title">
            Share your work<br />with <em>elegance</em>
          </h1>

          <p className="hero__sub">
            Beautiful client galleries, password‑protected delivery, and seamless downloads — all from one clean dashboard.
          </p>

          <div className="hero__actions">
            <Link to="/register" className="btn btn-primary">
              ✨ Start free today
            </Link>
            <Link to="/login" className="btn btn-ghost">
              Sign in →
            </Link>
          </div>

          <div className="hero__proof">
            {displayCount > 0 && (
              <div className="hero__avatars">
                {recentUsers.map((user, i) => (
                  <div key={i} className="hero__avatar" style={{ background: user.color || '#8c6d4f' }}>
                    {user.initial}
                  </div>
                ))}
              </div>
            )}
            <span>
              {displayCount === 0
                ? 'Be the first photographer to join Kyapture!'
                : `Trusted by ${displayCount} ${displayCount === 1 ? 'photographer' : 'photographers'} in Nepal & beyond`
              }
            </span>
          </div>
        </div>

        {/* decorative photo tiles */}
        <div className="hero__visual">
          {['🌄', '💒', '🎭', '🏔️'].map((emoji, i) => (
            <div key={i} className="photo-tile">
              <div className="photo-tile__inner">{emoji}</div>
            </div>
          ))}
        </div>

        <div
          className="hero__scroll"
          onClick={() => document.getElementById('features')?.scrollIntoView({ behavior: 'smooth' })}
        >
          <span>Scroll</span>
          <span>↓</span>
        </div>
      </section>

      {/* ===== FEATURES ===== */}
      <section className="section section--alt" id="features">
        <div className="section__label">Everything you need</div>
        <h2 className="section__title">One platform. Infinite galleries.</h2>
        <div className="features-grid">
          {FEATURES.map(f => (
            <div className="feature-card" key={f.title}>
              <div className="feature-card__icon">{f.icon}</div>
              <div className="feature-card__title">{f.title}</div>
              <div className="feature-card__desc">{f.desc}</div>
            </div>
          ))}
        </div>
      </section>

      {/* ===== CTA BAND ===== */}
      <section className="cta-band">
        <div className="cta-band__glow" />
        <div className="cta-band__content">
          <h2 className="cta-band__title">
            Ready to deliver <em>beautifully?</em>
          </h2>
          <p className="cta-band__sub">Join photographers who trust Kyapture for every delivery.</p>
          <Link to="/register" className="btn btn-accent" style={{ fontSize: 15, padding: '13px 30px' }}>
            Create your free account →
          </Link>
        </div>
      </section>

      {/* ===== FOOTER ===== */}
      <footer className="footer">
        <div className="footer__logo">📸 Kyapture</div>
        <div className="footer__links">
          <a href="#features">Features</a>
          <Link to="/pricing">Pricing</Link>
          <a href="#">Privacy</a>
          <a href="#">Terms</a>
          <a href="#">Contact</a>
        </div>
        <div className="footer__copy">© {new Date().getFullYear()} Kyapture. Made with ♥ in Nepal</div>
      </footer>
    </div>
  )
}
