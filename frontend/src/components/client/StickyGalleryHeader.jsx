import { useState, useEffect, useRef, useCallback } from "react";
import { Heart, Download, Share2, Play, Pause } from "lucide-react";
import { buildClientGalleryUrl } from "../../utils/formatters";
import { useToast } from "../ui/Toast";
import Modal from "../ui/Modal";

export default function StickyGalleryHeader({
  galleryTitle,
  username,
  slug,
  photos,
  favorites,
  onToggleFavorite,
  onOpenLightbox,
  token,
  brandingColor,
}) {
  const [scrolled, setScrolled] = useState(false);
  const [showSharePopover, setShowSharePopover] = useState(false);
  const [showDownloadModal, setShowDownloadModal] = useState(false);
  const [slideshowActive, setSlideshowActive] = useState(false);
  const shareRef = useRef(null);
  const toast = useToast();
  const slideshowRef = useRef(null);

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 100);
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  // Close share popover on outside click
  useEffect(() => {
    if (!showSharePopover) return;
    const handleClick = (e) => {
      if (shareRef.current && !shareRef.current.contains(e.target)) {
        setShowSharePopover(false);
      }
    };
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, [showSharePopover]);

  // Slideshow auto-advance
  useEffect(() => {
    if (!slideshowActive) {
      if (slideshowRef.current) clearInterval(slideshowRef.current);
      return;
    }
    onOpenLightbox(0);
    slideshowRef.current = setInterval(() => {
      window.dispatchEvent(new CustomEvent("slideshow-next"));
    }, 4000);
    return () => clearInterval(slideshowRef.current);
  }, [slideshowActive, onOpenLightbox]);

  const handleCopyLink = useCallback(() => {
    const url = buildClientGalleryUrl(username, slug);
    navigator.clipboard.writeText(url).then(() => {
      toast("Link copied to clipboard", "success");
      setShowSharePopover(false);
    });
  }, [username, slug, toast]);

  const handleEmailShare = useCallback(() => {
    const url = buildClientGalleryUrl(username, slug);
    const subject = encodeURIComponent(`Check out this gallery: ${galleryTitle || ""}`);
    const body = encodeURIComponent(`View the gallery here: ${url}`);
    window.open(`mailto:?subject=${subject}&body=${body}`);
    setShowSharePopover(false);
  }, [username, slug, galleryTitle]);

  const handleQRShare = useCallback(() => {
    const url = buildClientGalleryUrl(username, slug);
    window.open(`https://api.qrserver.com/v1/create-qr-code/?size=200x200&data=${encodeURIComponent(url)}`, "_blank");
    setShowSharePopover(false);
  }, [username, slug]);

  const favCount = favorites?.size || 0;

  return (
    <header
      className={`fixed top-0 left-0 right-0 z-30 transition-all duration-300 ${
        scrolled
          ? "bg-white/80 backdrop-blur-md border-b border-slate-200/50 shadow-topbar"
          : "bg-transparent"
      }`}
    >
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-14 flex items-center justify-between">
        {/* Brand */}
        <span
          className={`font-serif text-lg transition-colors duration-300 ${
            scrolled ? "text-ink" : "text-white"
          }`}
        >
          Kyapture
        </span>

        {/* Actions */}
        <div className="flex items-center gap-1">
          {/* Favorites */}
          <button
            onClick={() => {
              if (favCount > 0) {
                toast(`${favCount} photo${favCount !== 1 ? "s" : ""} in favorites`, "info");
              } else {
                toast("Heart photos to add them to favorites", "info");
              }
            }}
            className={`relative p-2 rounded-lg transition-colors duration-200 ${
              scrolled
                ? "text-ink hover:bg-slate-100"
                : "text-white/80 hover:text-white hover:bg-white/10"
            }`}
            aria-label={`Favorites${favCount > 0 ? `, ${favCount} items` : ""}`}
          >
            <Heart className="w-4.5 h-4.5" />
            {favCount > 0 && (
              <span
                className="absolute -top-0.5 -right-0.5 w-4 h-4 rounded-full text-[9px] font-medium flex items-center justify-center text-white"
                style={{ backgroundColor: brandingColor || "#0D9488" }}
              >
                {favCount}
              </span>
            )}
          </button>

          {/* Download */}
          <button
            onClick={() => setShowDownloadModal(true)}
            className={`p-2 rounded-lg transition-colors duration-200 ${
              scrolled
                ? "text-ink hover:bg-slate-100"
                : "text-white/80 hover:text-white hover:bg-white/10"
            }`}
            aria-label="Download options"
          >
            <Download className="w-4.5 h-4.5" />
          </button>

          {/* Share */}
          <div className="relative" ref={shareRef}>
            <button
              onClick={() => setShowSharePopover(!showSharePopover)}
              className={`p-2 rounded-lg transition-colors duration-200 ${
                scrolled
                  ? "text-ink hover:bg-slate-100"
                  : "text-white/80 hover:text-white hover:bg-white/10"
              }`}
              aria-label="Share gallery"
            >
              <Share2 className="w-4.5 h-4.5" />
            </button>

            {showSharePopover && (
              <div className="absolute right-0 top-full mt-2 w-48 bg-white rounded-xl shadow-lg border border-slate-200 py-1.5 animate-scale-in">
                <button
                  onClick={handleCopyLink}
                  className="w-full text-left px-4 py-2 text-sm text-ink hover:bg-slate-50 transition-colors"
                >
                  Copy Link
                </button>
                <button
                  onClick={handleEmailShare}
                  className="w-full text-left px-4 py-2 text-sm text-ink hover:bg-slate-50 transition-colors"
                >
                  Share via Email
                </button>
                <button
                  onClick={handleQRShare}
                  className="w-full text-left px-4 py-2 text-sm text-ink hover:bg-slate-50 transition-colors"
                >
                  QR Code
                </button>
              </div>
            )}
          </div>

          {/* Slideshow */}
          <button
            onClick={() => setSlideshowActive(!slideshowActive)}
            className={`p-2 rounded-lg transition-colors duration-200 ${
              scrolled
                ? slideshowActive
                  ? "text-primary bg-primary/10"
                  : "text-ink hover:bg-slate-100"
                : slideshowActive
                  ? "text-white bg-white/20"
                  : "text-white/80 hover:text-white hover:bg-white/10"
            }`}
            aria-label={slideshowActive ? "Stop slideshow" : "Start slideshow"}
          >
            {slideshowActive ? <Pause className="w-4.5 h-4.5" /> : <Play className="w-4.5 h-4.5" />}
          </button>
        </div>
      </div>

      {/* Download Modal */}
      <Modal
        open={showDownloadModal}
        onClose={() => setShowDownloadModal(false)}
        title="Download Gallery"
        size="sm"
      >
        <div className="space-y-3">
          <p className="text-sm text-muted font-light">
            Choose a download option for this gallery.
          </p>
          <a
            href={`/g/${username}/${slug}/download`}
            className="block w-full text-center text-sm font-medium text-ink border border-slate-200 rounded-lg px-4 py-3 hover:bg-slate-50 transition-colors"
          >
            Download Full Gallery
          </a>
          <p className="text-xs text-muted text-center">
            {photos?.length || 0} photo{(photos?.length || 0) !== 1 ? "s" : ""} total
          </p>
        </div>
      </Modal>
    </header>
  );
}
