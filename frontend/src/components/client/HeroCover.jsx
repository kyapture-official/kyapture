import { motion } from "framer-motion";
import { ChevronDown } from "lucide-react";
import { formatDate } from "../../utils/formatters";

export default function HeroCover({
  coverPhoto,
  galleryTitle,
  brandHeader,
  photographerName,
  eventDate,
  brandingColor,
}) {
  const scrollToGrid = () => {
    const grid = document.getElementById("gallery-grid");
    if (grid) {
      grid.scrollIntoView({ behavior: "smooth" });
    }
  };

  return (
    <section className="relative h-screen w-full overflow-hidden">
      {/* Cover Photo Background */}
      <div className="absolute inset-0">
        {coverPhoto ? (
          <img
            src={coverPhoto}
            alt=""
            className="w-full h-full object-cover"
          />
        ) : (
          <div className="w-full h-full bg-gradient-to-br from-charcoal via-charcoal-light to-slate-800" />
        )}
        <div className="absolute inset-0 bg-black/55" />
      </div>

      {/* Content */}
      <div className="relative z-10 flex flex-col items-center justify-center h-full px-6 text-center">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.7, ease: "easeOut" }}
          className="flex flex-col items-center"
        >
          {/* Brand Header (photographer name / studio branding) */}
          {brandHeader && (
            <p className="text-[10px] sm:text-xs uppercase tracking-[0.25em] text-white/60 font-light mb-4">
              {brandHeader}
            </p>
          )}

          {/* Collection Title */}
          <h1 className="font-serif text-4xl sm:text-5xl md:text-6xl lg:text-7xl text-white font-medium tracking-tight mb-4">
            {galleryTitle || "Collection"}
          </h1>

          {/* Divider */}
          <div
            className="h-px w-12 my-5"
            style={{ backgroundColor: brandingColor || "rgba(255,255,255,0.3)" }}
          />

          {/* Event Date */}
          {eventDate && (
            <p className="text-xs sm:text-sm text-white/50 font-light tracking-widest uppercase mb-10">
              {formatDate(eventDate)}
            </p>
          )}

          {/* View Gallery CTA */}
          <button
            onClick={scrollToGrid}
            className="group flex items-center gap-2.5 text-[11px] uppercase tracking-[0.25em] text-white/90 hover:text-white border border-white/25 hover:border-white/50 rounded-full px-8 py-3.5 transition-all duration-300 hover:bg-white/10 hover:shadow-[0_0_24px_rgba(255,255,255,0.08)]"
          >
            View Gallery
            <ChevronDown className="w-3.5 h-3.5 group-hover:translate-y-0.5 transition-transform duration-300" />
          </button>
        </motion.div>
      </div>

      {/* Scroll Indicator */}
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
  );
}
