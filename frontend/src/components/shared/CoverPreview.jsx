// C:\Users\David\Desktop\kyapture\frontend\src\components\shared\CoverPreview.jsx
import { formatDate } from "../../utils/formatters";

/**
 * WHAT: Live cover page preview — renders a scaled-down representation of
 *       the client-facing gallery cover based on the current design settings.
 * WHY:  Instant visual feedback as the photographer adjusts layout, typography,
 *       colors, and grid options in the design builder.
 */

const LAYOUT_CLASSES = {
  center: "items-center text-center",
  left: "items-start text-left pl-10",
  novel: "items-center text-center",
  vintage: "items-center text-center",
  frame: "items-center text-center",
  stripe: "items-center text-center",
};

const TYPOGRAPHY_CLASSES = {
  sans: "font-sans",
  serif: "font-serif",
  modern: "font-sans tracking-tight",
  timeless: "font-serif italic",
  bold: "font-sans font-bold",
  subtle: "font-sans font-light tracking-wide",
};

const COLOR_THEMES = {
  light: { bg: "bg-white", text: "text-ink", sub: "text-muted", accent: "bg-ink" },
  gold: { bg: "bg-amber-50", text: "text-amber-900", sub: "text-amber-700/60", accent: "bg-amber-600" },
  rose: { bg: "bg-rose-50", text: "text-rose-900", sub: "text-rose-700/60", accent: "bg-rose-500" },
  terracotta: { bg: "bg-orange-50", text: "text-orange-900", sub: "text-orange-700/60", accent: "bg-orange-600" },
  sand: { bg: "bg-stone-100", text: "text-stone-900", sub: "text-stone-600", accent: "bg-stone-500" },
  olive: { bg: "bg-lime-50", text: "text-lime-900", sub: "text-lime-700/60", accent: "bg-lime-700" },
  agave: { bg: "bg-teal-50", text: "text-teal-900", sub: "text-teal-700/60", accent: "bg-teal-600" },
  sea: { bg: "bg-sky-50", text: "text-sky-900", sub: "text-sky-700/60", accent: "bg-sky-600" },
  dark: { bg: "bg-slate-900", text: "text-white", sub: "text-white/50", accent: "bg-white/20" },
};

export default function CoverPreview({ settings, gallery }) {
  const layout = LAYOUT_CLASSES[settings.layout] || LAYOUT_CLASSES.center;
  const typo = TYPOGRAPHY_CLASSES[settings.typography] || TYPOGRAPHY_CLASSES.serif;
  const theme = COLOR_THEMES[settings.colorPalette] || COLOR_THEMES.light;

  const title = gallery?.title || "Collection Title";
  const date = gallery?.event_date || gallery?.created_at;
  const photos = gallery?.photos || [];

  // Find explicit selected photo from design settings or default active cover
  const selectedCoverPhoto = settings?.coverPhoto 
    ? photos.find(p => p.id === settings.coverPhoto) 
    : photos.find(p => p.is_cover);

  const fallbackPhoto = selectedCoverPhoto || photos[0];

  const coverSrc = gallery?.cover_url || (
    fallbackPhoto
      ? (fallbackPhoto.display_url || fallbackPhoto.thumbnail_url || fallbackPhoto.url || fallbackPhoto.original_url)
      : null
  );

  return (
    <div className={`relative w-full aspect-[4/3] rounded-2xl overflow-hidden border border-slate-200 ${theme.bg} transition-all duration-300`}>
      {/* Background image / blur overlay */}
      {coverSrc && (
        <>
          <img
            src={coverSrc}
            alt=""
            className="absolute inset-0 w-full h-full object-cover"
          />
          <div className="absolute inset-0 bg-black/40 backdrop-blur-sm" />
        </>
      )}

      {/* Content */}
      <div className={`relative z-10 flex flex-col justify-center h-full ${layout} gap-3 px-6`}>
        {/* Accent bar (stripe layout) */}
        {settings.layout === "stripe" && (
          <div className={`w-8 h-1 rounded-full ${theme.accent} mb-2`} />
        )}

        {/* Title */}
        <h2
          className={`text-2xl font-semibold ${typo} ${
            coverSrc ? "text-white" : theme.text
          } transition-all duration-300`}
        >
          {title}
        </h2>

        {/* Divider */}
        <div
          className={`h-px w-8 ${coverSrc ? "bg-white/30" : theme.accent} transition-all duration-300`}
        />

        {/* Date */}
        {date && (
          <p
            className={`text-[10px] uppercase tracking-[0.2em] font-light ${
              coverSrc ? "text-white/60" : theme.sub
            }`}
          >
            {formatDate(date)}
          </p>
        )}

        {/* CTA */}
        <div
          className={`mt-2 px-5 py-1.5 rounded-full text-[10px] uppercase tracking-[0.2em] font-medium border ${
            coverSrc
              ? "border-white/25 text-white/90"
              : `border-current ${theme.sub}`
          }`}
        >
          View Gallery
        </div>
      </div>

      {/* Frame overlay for 'frame' layout */}
      {settings.layout === "frame" && (
        <div className="absolute inset-4 border-2 border-white/15 rounded-xl pointer-events-none z-20" />
      )}

      {/* Vintage grain overlay */}
      {settings.layout === "vintage" && (
        <div className="absolute inset-0 bg-amber-900/10 mix-blend-multiply pointer-events-none z-20" />
      )}

      {/* Novel layout — corner flourish lines */}
      {settings.layout === "novel" && (
        <>
          <div className="absolute top-4 left-4 w-8 h-8 border-t-2 border-l-2 border-white/20 rounded-tl-lg pointer-events-none z-20" />
          <div className="absolute bottom-4 right-4 w-8 h-8 border-b-2 border-r-2 border-white/20 rounded-br-lg pointer-events-none z-20" />
        </>
      )}
    </div>
  );
}
