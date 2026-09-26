import { useState, useEffect, useRef, useCallback } from "react";
import { createPortal } from "react-dom";
import { motion, AnimatePresence } from "framer-motion";
import { formatDate } from "../../utils/formatters";

export default function ClientPreviewModal({ open, onClose, gallery }) {
  const [showGrid, setShowGrid] = useState(false);
  const [scrolledPastHero, setScrolledPastHero] = useState(false);
  const [favorites, setFavorites] = useState(new Set());
  const [viewMode, setViewMode] = useState("grid");
  const gridRef = useRef(null);
  const containerRef = useRef(null);
  const heroRef = useRef(null);

  useEffect(() => {
    if (!open) {
      setShowGrid(false);
      setScrolledPastHero(false);
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

  const handleShare = async () => {
    try {
      await navigator.clipboard.writeText(window.location.href);
    } catch {
      // silent
    }
  };

  if (!open) return null;

  const title = gallery?.title || "Collection";
  const photographer = gallery?.photographer_name || gallery?.user?.full_name || "Photographer";
  const date = gallery?.event_date || gallery?.created_at;
  
  // Extract photos list safely
  const photos = gallery?.photos || [];

  // Dynamic Cover Image logic (matching Client Page)
  const coverSrc = gallery?.cover_url || gallery?.cover_photo_url || gallery?.cover_photo?.url || (
    photos.length > 0
      ? (photos.find(p => p.is_cover)?.display_url || photos.find(p => p.is_cover)?.url || photos[0]?.display_url || photos[0]?.url || photos[0]?.file || photos[0]?.thumbnail_url)
      : null
  );

  return createPortal(
    <div className="fixed inset-0 z-[100] bg-white flex flex-col">
      {/* Close button — top right */}
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

      {/* Sticky Header Bar */}
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

              {/* Right: view modes & close */}
              <div className="flex items-center space-x-4 flex-shrink-0">
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
        {/* HERO COVER SECTION */}
        <section ref={heroRef} id="hero" className="relative h-screen min-h-screen w-full overflow-hidden flex-shrink-0">
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

          {photos.length > 0 ? (
            <div className={`max-w-6xl mx-auto gap-4 ${
              viewMode === "large"
                ? "grid grid-cols-1 sm:grid-cols-2"
                : "grid grid-cols-2 md:grid-cols-3"
            }`}>
              {photos.map((photo, i) => {
                const src = typeof photo === "string" 
                  ? photo 
                  : (photo.display_url || photo.url || photo.file || photo.original_url || photo.thumbnail_url);

                if (!src) return null;

                return (
                  <motion.div
                    key={photo.id || i}
                    initial={{ opacity: 0, y: 12 }}
                    whileInView={{ opacity: 1, y: 0 }}
                    viewport={{ once: true, margin: "-40px" }}
                    transition={{ duration: 0.4, delay: i * 0.05 }}
                    className="relative rounded-xl overflow-hidden bg-slate-100 group aspect-[3/2] shadow-sm hover:shadow-md transition-shadow"
                  >
                    <img
                      src={src}
                      alt={`Photo ${i + 1}`}
                      className="w-full h-full object-cover transition-transform duration-500 group-hover:scale-105"
                      loading="lazy"
                    />
                  </motion.div>
                );
              })}
            </div>
          ) : (
            <div className="max-w-6xl mx-auto py-20 text-center bg-slate-50 rounded-2xl border border-dashed border-slate-200">
              <p className="text-sm text-slate-500 font-sans">
                No photos uploaded yet in this gallery.
              </p>
            </div>
          )}

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