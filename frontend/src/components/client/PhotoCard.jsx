import { useState } from "react";
import { useInView } from "react-intersection-observer";
import { Heart, Download, Share2, Play } from "lucide-react";
import { getBlurhashDataUrl } from "../../utils/blurhashDataUrl";
import { formatDuration } from "../../utils/formatters";
import { buildClientGalleryUrl } from "../../utils/formatters";
import { useToast } from "../ui/Toast";

function buildDownloadHref(downloadUrl, token) {
  if (!downloadUrl) return null;
  return token
    ? `${downloadUrl}?token=${encodeURIComponent(token)}`
    : downloadUrl;
}

export default function PhotoCard({
  photo,
  index,
  token,
  username,
  slug,
  onPhotoClick,
  isFavorited,
  onToggleFavorite,
}) {
  const [loadedSrc, setLoadedSrc] = useState(null);
  const [errorSrc, setErrorSrc] = useState(null);
  const toast = useToast();

  const isVideo = photo.media_type === "video";
  const imgSrc = isVideo ? photo.poster_url : photo.thumbnail_url || photo.display_url;
  const isLoaded = loadedSrc === imgSrc;
  const hasError = errorSrc === imgSrc && imgSrc != null;
  const blurDataUrl = getBlurhashDataUrl(photo.blurhash);

  const { ref, inView } = useInView({ triggerOnce: true, rootMargin: "200px 0px" });

  const aspectRatio =
    photo.width && photo.height ? `${photo.width} / ${photo.height}` : "3 / 2";

  const stillProcessing =
    !imgSrc &&
    (photo.processing_status === "pending" || photo.processing_status === "processing");

  const downloadHref = buildDownloadHref(photo.download_url, token);

  const handleShare = (e) => {
    e.stopPropagation();
    const url = buildClientGalleryUrl(username, slug);
    navigator.clipboard.writeText(url).then(() => {
      toast("Link copied", "success");
    });
  };

  const handleDownload = (e) => {
    e.stopPropagation();
    if (downloadHref) {
      const a = document.createElement("a");
      a.href = downloadHref;
      a.download = photo.original_name || "photo";
      a.click();
    }
  };

  const handleFavorite = (e) => {
    e.stopPropagation();
    onToggleFavorite?.(photo.id);
  };

  return (
    <div
      ref={ref}
      onClick={() => !stillProcessing && onPhotoClick?.(index)}
      className={`group relative w-full overflow-hidden rounded-lg bg-slate-100 mb-4 break-inside-avoid shadow-sm hover:shadow-card-hover transition-shadow duration-300 select-none ${
        stillProcessing ? "" : "cursor-pointer"
      }`}
      style={{
        aspectRatio,
        ...(blurDataUrl && !isLoaded && {
          backgroundImage: `url(${blurDataUrl})`,
          backgroundSize: "cover",
          backgroundPosition: "center",
        }),
      }}
    >
      {inView ? (
        <>
          {stillProcessing ? (
            <div className="absolute inset-0 bg-slate-100 animate-pulse flex items-center justify-center">
              <span className="text-slate-400 text-[10px] font-light select-none">
                Processing…
              </span>
            </div>
          ) : hasError ? (
            <div className="absolute inset-0 bg-slate-200 flex flex-col items-center justify-center p-4">
              <span className="text-slate-400 text-xs font-light select-none pointer-events-none">
                Unavailable
              </span>
            </div>
          ) : (
            <>
              <img
                src={imgSrc}
                alt={photo.alt || photo.original_name || "Gallery item"}
                loading="lazy"
                decoding="async"
                className={`
                  w-full h-full object-cover pointer-events-none
                  transition-[opacity,transform] duration-500 ease-out
                  group-hover:scale-[1.03]
                  ${isLoaded ? "opacity-100" : "opacity-0"}
                `}
                style={{ WebkitTouchCallout: "none", WebkitUserSelect: "none" }}
                onLoad={() => setLoadedSrc(imgSrc)}
                onError={() => setErrorSrc(imgSrc)}
              />

              {isVideo && (
                <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
                  <div className="w-11 h-11 rounded-full bg-black/50 flex items-center justify-center backdrop-blur-sm">
                    <Play className="w-5 h-5 text-white fill-white ml-0.5" />
                  </div>
                </div>
              )}

              {isVideo && photo.duration != null && (
                <span className="absolute bottom-2 right-2 px-1.5 py-0.5 rounded bg-black/70 text-white text-[10px] font-medium tabular-nums pointer-events-none">
                  {formatDuration(photo.duration)}
                </span>
              )}
            </>
          )}

          {/* Hover Gradient Overlay */}
          <div className="absolute inset-0 bg-gradient-to-t from-black/60 via-transparent to-transparent opacity-0 group-hover:opacity-100 transition-opacity duration-300 pointer-events-none" />

          {/* Hover Action Buttons */}
          <div className="absolute bottom-2 right-2 flex items-center gap-1.5 opacity-0 group-hover:opacity-100 translate-y-1 group-hover:translate-y-0 transition-all duration-300 z-10">
            <button
              onClick={handleFavorite}
              className={`p-1.5 rounded-full backdrop-blur-sm transition-all duration-200 ${
                isFavorited
                  ? "bg-red-500 text-white"
                  : "bg-black/40 text-white/80 hover:bg-black/60 hover:text-white"
              }`}
              aria-label={isFavorited ? "Remove from favorites" : "Add to favorites"}
              title={isFavorited ? "Remove from favorites" : "Add to favorites"}
            >
              <Heart className={`w-3.5 h-3.5 ${isFavorited ? "fill-current" : ""}`} />
            </button>

            {downloadHref && (
              <button
                onClick={handleDownload}
                className="p-1.5 rounded-full bg-black/40 text-white/80 hover:bg-black/60 hover:text-white backdrop-blur-sm transition-all duration-200"
                aria-label="Download photo"
                title="Download"
              >
                <Download className="w-3.5 h-3.5" />
              </button>
            )}

            <button
              onClick={handleShare}
              className="p-1.5 rounded-full bg-black/40 text-white/80 hover:bg-black/60 hover:text-white backdrop-blur-sm transition-all duration-200"
              aria-label="Share photo"
              title="Share"
            >
              <Share2 className="w-3.5 h-3.5" />
            </button>
          </div>
        </>
      ) : (
        <div className="w-full h-full bg-slate-100 animate-pulse" />
      )}
    </div>
  );
}
