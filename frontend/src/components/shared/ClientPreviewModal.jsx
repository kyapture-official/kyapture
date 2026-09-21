import { useState, useEffect, useRef, useCallback } from "react";
import { createPortal } from "react-dom";
import { motion, AnimatePresence } from "framer-motion";
import { formatDate } from "../../utils/formatters";

const MOCK_PHOTOS = [
  "https://images.unsplash.com/photo-1519741497674-611481863552?auto=format&fit=crop&w=600&q=80",
  "https://images.unsplash.com/photo-1511285560929-80b456fea0bc?auto=format&fit=crop&w=600&q=80",
  "https://images.unsplash.com/photo-1465495976277-4387d4b0b4c6?auto=format&fit=crop&w=600&q=80",
  "https://images.unsplash.com/photo-1583939003579-730e3918a45a?auto=format&fit=crop&w=600&q=80",
  "https://images.unsplash.com/photo-1606216794074-735e91aa2c92?auto=format&fit=crop&w=600&q=80",
  "https://images.unsplash.com/photo-1591604466107-ec97de577aff?auto=format&fit=crop&w=600&q=80",
];

export default function ClientPreviewModal({ open, onClose, gallery }) {
  const [showGrid, setShowGrid] = useState(false);
  const [scrolledPastHero, setScrolledPastHero] = useState(false);
  const [hoveredPhoto, setHoveredPhoto] = useState(null);
  const [favorites, setFavorites] = useState(new Set());
  const [viewMode, setViewMode] = useState("grid");
  const gridRef = useRef(null);
  const containerRef = useRef(null);
  const heroRef = useRef(null);

  useEffect(() => {
    if (!open) {
      setShowGrid(false);
      setScrolledPastHero(false);
      setHoveredPhoto(null);
      setFavorites(new Set());
    }
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => { document.body.style.overflow = prev; };
  }, [open]);

  const handleScroll = useCallback(() => {
    if (!containerRef.current || !heroRef.current) return;
    const { scrollTop } = containerRef.current;
    const heroHeight = heroRef.current.offsetHeight;
    const pastHero = scrollTop > heroHeight * 0.85;
    setScrolledPastHero(pastHero);
    if (pastHero && !showGrid) setShowGrid(true);
  }, [showGrid]);

  const handleViewGallery = () => {
    setShowGrid(true);
    requestAnimationFrame(() => {
      gridRef.current?.scrollIntoView({ behavior: "smooth" });
    });
  };

  const toggleFavorite = (idx) => {
    setFavorites((prev) => {
      const next = new Set(prev);
      if (next.has(idx)) next.delete(idx);
      else next.add(idx);
      return next;
    });
  };

  const handleDownload = (idx) => {
    const link = document.createElement("a");
    link.href = MOCK_PHOTOS[idx];
    link.download = `photo-${idx + 1}.jpg`;
    link.click();
  };

  const handleShare = async () => {
    try {
      await navigator.clipboard.writeText(window.location.href);
    } catch {
      // silent
    }
  };

  if (!open) return null;

  const title = gallery?.title || "Collection";
  const photographer = gallery?.photographer_name || "Photographer";
  const date = gallery?.event_date || gallery?.created_at;
  const coverSrc = gallery?.cover_url;

  return createPortal(
    <div className="fixed inset-0 z-[100] bg-white flex flex-col">
      {/* Close button — only visible over the hero */}
      <AnimatePresence>
        {!scrolledPastHero && (
          <motion.button
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={onClose}
            className="absolute top-5 right-5 z-50 p-2.5 rounded-full bg-black/20 backdrop-blur-md text-white hover:bg-black/40 transition-colors cursor-pointer"
            aria-label="Exit preview"
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </motion.button>
        )}
      </AnimatePresence>

      {/* Sticky Header Bar — locks when past hero */}
      <AnimatePresence>
        {scrolledPastHero && (
          <motion.header
            initial={{ opacity: 0, y: -8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -8 }}
            transition={{ duration: 0.2 }}
            className="sticky top-0 z-50 bg-white border-b border-gray-200 shadow-sm px-6 md:px-12 py-3 flex-shrink-0"
          >
            <div className="flex justify-between items-center">
              {/* Left: title + photographer */}
              <div className="min-w-0">
                <h2 className="font-serif text-sm md:text-base font-semibold text-ink tracking-wide truncate uppercase">
                  {title}
                </h2>
                <p className="text-[10px] md:text-[11px] text-muted font-sans tracking-wider uppercase">
                  {photographer}
                </p>
              </div>

              {/* Right: action icons */}
              <div className="flex items-center space-x-6 flex-shrink-0">
                <HeaderIconButton
                  active={favorites.size > 0}
                  activeClass="text-red-500"
                  onClick={() => {
                    const first = MOCK_PHOTOS.findIndex((_, i) => !favorites.has(i));
                    if (first !== -1) toggleFavorite(first);
                  }}
                  label="Favorite"
                >
                  <svg className="w-4 h-4" viewBox="0 0 24 24" fill={favorites.size > 0 ? "currentColor" : "none"} stroke="currentColor" strokeWidth="1.8">
                    <path strokeLinecap="round" strokeLinejoin="round" d="M21 8.25c0-2.485-2.099-4.5-4.688-4.5-1.935 0-3.597 1.126-4.312 2.733-.715-1.607-2.377-2.733-4.313-2.733C5.1 3.75 3 5.765 3 8.25c0 7.22 9 12 9 12s9-4.78 9-12z" />
                  </svg>
                </HeaderIconButton>
                <HeaderIconButton onClick={() => {}} label="Download">
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" strokeWidth="1.8" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" d="M3 16.5v2.25A2.25 2.25 0 005.25 21h13.5A2.25 2.25 0 0021 18.75V16.5M16.5 12L12 16.5m0 0L7.5 12m4.5 4.5V3" />
                  </svg>
                </HeaderIconButton>
                <HeaderIconButton onClick={handleShare} label="Share">
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" strokeWidth="1.8" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" d="M7.217 10.907a2.25 2.25 0 100 2.186m0-2.186c.18.324.283.696.283 1.093s-.103.77-.283 1.093m0-2.186l9.566-5.314m-9.566 7.5l9.566 5.314m0 0a2.25 2.25 0 103.935 2.186 2.25 2.25 0 00-3.935-2.186zm0-12.814a2.25 2.25 0 103.933-2.185 2.25 2.25 0 00-3.933 2.185z" />
                  </svg>
                </HeaderIconButton>
                <div className="w-px h-4 bg-gray-200 mx-1" />
                <HeaderIconButton
                  active={viewMode === "large"}
                  onClick={() => setViewMode((v) => (v === "grid" ? "large" : "grid"))}
                  label={viewMode === "grid" ? "Large view" : "Grid view"}
                >
                  {viewMode === "grid" ? (
                    <svg className="w-4 h-4" fill="none" stroke="currentColor" strokeWidth="1.8" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" d="M3.75 6A2.25 2.25 0 016 3.75h2.25A2.25 2.25 0 0110.5 6v2.25a2.25 2.25 0 01-2.25 2.25H6a2.25 2.25 0 01-2.25-2.25V6zM3.75 15.75A2.25 2.25 0 016 13.5h2.25a2.25 2.25 0 012.25 2.25V18a2.25 2.25 0 01-2.25 2.25H6A2.25 2.25 0 013.75 18v-2.25zM13.5 6a2.25 2.25 0 012.25-2.25H18A2.25 2.25 0 0120.25 6v2.25A2.25 2.25 0 0118 10.5h-2.25a2.25 2.25 0 01-2.25-2.25V6zM13.5 15.75a2.25 2.25 0 012.25-2.25H18a2.25 2.25 0 012.25 2.25V18A2.25 2.25 0 0118 20.25h-2.25A2.25 2.25 0 0113.5 18v-2.25z" />
                    </svg>
                  ) : (
                    <svg className="w-4 h-4" fill="none" stroke="currentColor" strokeWidth="1.8" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" d="M3.75 6h16.5M3.75 12h16.5m-16.5 6h16.5" />
                    </svg>
                  )}
                </HeaderIconButton>
                <button
                  onClick={onClose}
                  className="ml-2 p-2 rounded-lg text-gray-400 hover:text-gray-600 hover:bg-gray-100 transition-colors cursor-pointer"
                  aria-label="Close preview"
                >
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
                  </svg>
                </button>
              </div>
            </div>
          </motion.header>
        )}
      </AnimatePresence>

      {/* Scrollable content */}
      <div
        ref={containerRef}
        onScroll={handleScroll}
        className="flex-1 overflow-y-auto"
      >
        {/* HERO SECTION */}
        <section ref={heroRef} id="hero" className="relative h-[85vh] w-full overflow-hidden flex-shrink-0">
          <div className="absolute inset-0">
            {coverSrc ? (
              <img src={coverSrc} alt="" className="w-full h-full object-cover" />
            ) : (
              <div className="w-full h-full bg-gradient-to-br from-slate-900 via-slate-800 to-slate-700" />
            )}
            <div className="absolute inset-0 bg-gradient-to-t from-black/60 via-black/20 to-transparent" />
          </div>

          <div className="relative z-10 flex flex-col items-center justify-center h-full px-6 text-center">
            <motion.div
              initial={{ opacity: 0, y: 24 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.8, ease: "easeOut" }}
              className="flex flex-col items-center"
            >
              <p className="text-[10px] sm:text-xs uppercase tracking-[0.25em] text-white/50 font-light mb-5">
                {photographer}
              </p>
              <h1 className="font-serif text-4xl sm:text-5xl md:text-6xl lg:text-7xl text-white font-medium tracking-tight mb-4">
                {title}
              </h1>
              <div className="h-px w-12 my-5 bg-white/30" />
              {date && (
                <p className="text-xs sm:text-sm text-white/45 font-light tracking-widest uppercase mb-10">
                  {formatDate(date)}
                </p>
              )}
              <button
                onClick={handleViewGallery}
                className="group flex items-center gap-2.5 text-[11px] uppercase tracking-[0.25em] text-white/90 hover:text-white border border-white/25 hover:border-white/50 rounded-full px-8 py-3.5 transition-all duration-300 hover:bg-white/10 hover:shadow-[0_0_24px_rgba(255,255,255,0.08)] cursor-pointer"
              >
                View Gallery
                <svg className="w-3.5 h-3.5 group-hover:translate-y-0.5 transition-transform duration-300" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M19.5 8.25l-7.5 7.5-7.5-7.5" />
                </svg>
              </button>
            </motion.div>
          </div>

          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ delay: 1.2, duration: 0.6 }}
            className="absolute bottom-8 left-1/2 -translate-x-1/2"
          >
            <div className="w-5 h-8 rounded-full border border-white/20 flex items-start justify-center p-1.5">
              <motion.div
                animate={{ y: [0, 8, 0] }}
                transition={{ duration: 1.8, repeat: Infinity, ease: "easeInOut" }}
                className="w-1 h-1 rounded-full bg-white/50"
              />
            </div>
          </motion.div>
        </section>

        {/* PHOTO GRID SECTION */}
        <section ref={gridRef} className="min-h-screen bg-white px-4 sm:px-8 md:px-12 lg:px-20 py-16">
          <div className="max-w-6xl mx-auto mb-10">
            <h2 className="font-serif text-3xl text-ink mb-2">{title}</h2>
            <div className="h-px w-8 bg-ink/15" />
          </div>

          <div className={`max-w-6xl mx-auto gap-3 ${
            viewMode === "large"
              ? "grid grid-cols-1 sm:grid-cols-2"
              : "grid grid-cols-2 md:grid-cols-3"
          }`}>
            {MOCK_PHOTOS.map((src, i) => (
              <motion.div
                key={i}
                initial={{ opacity: 0, y: 12 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true, margin: "-40px" }}
                transition={{ duration: 0.4, delay: i * 0.06 }}
                className={`relative rounded-xl overflow-hidden bg-slate-100 group ${
                  viewMode === "large" ? "aspect-[4/3]" : "aspect-[3/2]"
                }`}
                onMouseEnter={() => setHoveredPhoto(i)}
                onMouseLeave={() => setHoveredPhoto(null)}
              >
                <img
                  src={src}
                  alt={`Photo ${i + 1}`}
                  className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-500"
                  loading="lazy"
                />
                <div className={`absolute inset-0 bg-gradient-to-t from-black/50 via-transparent to-transparent transition-opacity duration-300 ${
                  hoveredPhoto === i ? "opacity-100" : "opacity-0"
                }`} />
                <div className={`absolute top-3 right-3 flex items-center gap-1.5 transition-opacity duration-300 ${
                  hoveredPhoto === i ? "opacity-100" : "opacity-0"
                }`}>
                  <button
                    onClick={() => toggleFavorite(i)}
                    className={`p-2 rounded-full backdrop-blur-md transition-all cursor-pointer ${
                      favorites.has(i)
                        ? "bg-red-500/90 text-white"
                        : "bg-white/90 text-slate-600 hover:bg-white hover:text-red-500"
                    }`}
                    aria-label="Favorite"
                  >
                    <svg className="w-4 h-4" viewBox="0 0 24 24" fill={favorites.has(i) ? "currentColor" : "none"} stroke="currentColor" strokeWidth="1.8">
                      <path strokeLinecap="round" strokeLinejoin="round" d="M21 8.25c0-2.485-2.099-4.5-4.688-4.5-1.935 0-3.597 1.126-4.312 2.733-.715-1.607-2.377-2.733-4.313-2.733C5.1 3.75 3 5.765 3 8.25c0 7.22 9 12 9 12s9-4.78 9-12z" />
                    </svg>
                  </button>
                  <button
                    onClick={() => handleDownload(i)}
                    className="p-2 rounded-full bg-white/90 text-slate-600 hover:bg-white hover:text-ink backdrop-blur-md transition-all cursor-pointer"
                    aria-label="Download"
                  >
                    <svg className="w-4 h-4" fill="none" stroke="currentColor" strokeWidth="1.8" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" d="M3 16.5v2.25A2.25 2.25 0 005.25 21h13.5A2.25 2.25 0 0021 18.75V16.5M16.5 12L12 16.5m0 0L7.5 12m4.5 4.5V3" />
                    </svg>
                  </button>
                </div>
                <div className={`absolute bottom-3 left-3 transition-opacity duration-300 ${
                  hoveredPhoto === i ? "opacity-100" : "opacity-0"
                }`}>
                  <span className="text-[10px] text-white/80 font-medium bg-black/30 backdrop-blur-sm rounded-full px-2 py-0.5">
                    {i + 1} / {MOCK_PHOTOS.length}
                  </span>
                </div>
              </motion.div>
            ))}
          </div>

          {/* Back to Top */}
          <div className="max-w-6xl mx-auto mt-16 mb-8 text-center">
            <button
              onClick={() => {
                containerRef.current?.scrollTo({ top: 0, behavior: "smooth" });
              }}
              className="inline-flex items-center gap-2 text-[11px] uppercase tracking-[0.2em] text-gray-400 hover:text-ink transition-colors duration-300 cursor-pointer"
            >
              <svg className="w-3.5 h-3.5 rotate-180" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" d="M19.5 8.25l-7.5 7.5-7.5-7.5" />
              </svg>
              Back to Top
            </button>
          </div>
        </section>
      </div>
    </div>,
    document.body
  );
}

function HeaderIconButton({ children, active, activeClass, onClick, label }) {
  return (
    <button
      onClick={onClick}
      className={`p-2 rounded-lg transition-colors cursor-pointer ${
        active
          ? `${activeClass || "text-ink"} bg-gray-100`
          : "text-gray-400 hover:text-gray-600 hover:bg-gray-100"
      }`}
      aria-label={label}
      title={label}
    >
      {children}
    </button>
  );
}
