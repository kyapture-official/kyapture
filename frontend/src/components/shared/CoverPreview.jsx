// C:\Users\David\Desktop\kyapture\frontend\src\components\shared\CoverPreview.jsx
import { formatDate } from "../../utils/formatters";
import { resolveDesignSettings } from "../../utils/designSettings";

/**
 * WHAT: Live cover page preview — renders a scaled-down representation of
 *       the client-facing gallery cover based on the current design settings.
 * WHY:  Instant visual feedback as the photographer adjusts layout, typography,
 *       colors, and grid options in the design builder.
 *
 * The layout/typography/color option → class mapping lives in
 * ../../utils/designSettings.js, shared with the real public client
 * gallery (ClientGalleryPage.jsx) so this preview and what a guest
 * actually sees stay in lockstep.
 */

export default function CoverPreview({ settings, gallery }) {
  const { layoutClass: layout, typographyClass: typo, theme } = resolveDesignSettings(settings);

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
    <div className={`relative w-full aspect-[4/3] rounded-2xl overflow-hidden border border-cream-200 ${theme.bg} transition-all duration-300`}>
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
