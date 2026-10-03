// C:\Users\David\Desktop\kyapture\frontend\src\components\layout\TopNavBar.jsx
import { useState, useRef, useEffect } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { usePixieset } from "../../context/PixiesetContext";
import { useAuthStore } from "../../store/authStore";
import { galleriesApi } from "../../api/galleriesApi";
import ShareMenu from "../shared/ShareMenu";
import { copyText, resolveShareUrl } from "../../utils/share";

export default function TopNavBar({ gallery = null }) {
  const navigate = useNavigate();
  const { id } = useParams();
  const { user } = useAuthStore();
  const { collection, publishCollection, unpublishCollection, addToast } = usePixieset();
  const [moreOpen, setMoreOpen] = useState(false);
  const [statusOpen, setStatusOpen] = useState(false);
  const [loading, setLoading] = useState(false); 
  const moreRef = useRef(null);
  const statusRef = useRef(null);

  useEffect(() => {
    const close = (e) => {
      if (moreRef.current && !moreRef.current.contains(e.target)) setMoreOpen(false);
      if (statusRef.current && !statusRef.current.contains(e.target)) setStatusOpen(false);
    };
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, []);

  const handleStatusToggle = async () => {
    const isCurrentlyPublished = collection.status === "PUBLISHED";
    const shouldPublish = !isCurrentlyPublished;

    setLoading(true);
    setStatusOpen(false);

    try {
      // Backend Database ma POST request hanne
      await galleriesApi.publishGallery(id, shouldPublish);

      // Backend success vae pachi matra local UI update
      if (isCurrentlyPublished) {
        unpublishCollection();
        addToast({ message: "Collection set to Draft", type: "info" });
      } else {
        publishCollection();
        addToast({ message: "Collection published!", type: "success" });
      }
    } catch (error) {
      console.error("Status update error:", error);
      addToast({ message: "Failed to update status on server", type: "error" });
    } finally {
      setLoading(false);
    }
  };

  // The canonical, credential-free client link for this collection (server-built).
  const shareUrl = resolveShareUrl(gallery?.share_url, user?.username, id);
  const isDraft = gallery ? gallery.is_published === false : collection?.status !== "PUBLISHED";

  const handleCopyDirectLink = async () => {
    const ok = await copyText(shareUrl);
    addToast({ message: ok ? "Direct link copied!" : "Failed to copy link", type: ok ? "success" : "error" });
    setMoreOpen(false);
  };

  const handleDelete = async () => {
    if (!window.confirm("Delete this collection? This cannot be undone.")) {
      setMoreOpen(false);
      return;
    }
    setMoreOpen(false);
    try {
      await galleriesApi.deleteGallery(id);
      addToast({ message: "Collection deleted", type: "info" });
      navigate("/dashboard/galleries");
    } catch (error) {
      console.error("Delete gallery error:", error);
      addToast({ message: "Failed to delete collection", type: "error" });
    }
  };

  const isPublished = collection.status === "PUBLISHED";

  return (
    <div className="sticky top-0 z-20 bg-white/80 backdrop-blur-md border-b border-cream-200">
      <div className="flex items-center justify-between gap-4 px-4 md:px-6 py-3">
        {/* Left: Breadcrumbs + Status */}
        <div className="flex items-center gap-2 min-w-0">
          <button
            onClick={() => navigate("/dashboard/galleries")}
            className="text-xs text-muted hover:text-ink hover:underline transition-colors cursor-pointer flex-shrink-0"
          >
            Collections
          </button>
          <svg className="w-3 h-3 text-muted flex-shrink-0" fill="none" stroke="currentColor" strokeWidth="2.5" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" d="M8.25 4.5l7.5 7.5-7.5 7.5" />
          </svg>
          <span className="text-xs font-semibold text-ink truncate max-w-[200px]">
            {collection.title || "Untitled"}
          </span>

          {/* Status Badge Dropdown */}
          <div className="relative" ref={statusRef}>
            <button
              onClick={() => !loading && setStatusOpen(!statusOpen)}
              disabled={loading}
              className={`inline-flex items-center px-2.5 py-1 rounded-full text-[10px] font-medium border cursor-pointer transition-all ${
                loading ? "opacity-50 cursor-not-allowed" : ""
              } ${
                isPublished
                  ? "bg-brand-green-50 text-brand-green-700 border-brand-green-200 hover:bg-brand-green-100"
                  : "bg-cream-100 text-muted border-cream-200 hover:bg-cream-300"
              }`}
            >
              {loading ? "Saving..." : isPublished ? "Published" : "Draft"}
              <svg className="w-2.5 h-2.5 ml-1" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" d="M19.5 8.25l-7.5 7.5-7.5-7.5" />
              </svg>
            </button>
            {statusOpen && (
              <div className="absolute top-full mt-1 left-0 bg-surface-light border border-cream-200 rounded-xl shadow-lg py-1 w-40 animate-scale-in z-50">
                <button
                  onClick={handleStatusToggle}
                  className="w-full text-left px-3 py-2 text-xs text-ink hover:bg-cream-100 transition-colors cursor-pointer"
                >
                  {isPublished ? "Set to Draft" : "Publish Collection"}
                </button>
              </div>
            )}
          </div>
        </div>

        {/* Right: Actions */}
        <div className="flex items-center gap-2 flex-shrink-0">
          {/* Preview Button */}
          <button
            onClick={() => {
              const evt = new CustomEvent("open-preview");
              window.dispatchEvent(evt);
            }}
            className="hidden sm:flex items-center gap-1.5 px-3 py-2 border border-cream-200 text-ink/80 hover:text-ink bg-surface-light hover:bg-cream-100 text-xs font-medium rounded-xl transition-all cursor-pointer shadow-sm hover:shadow"
          >
            <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" strokeWidth="1.8" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" d="M2.036 12.322a1.012 1.012 0 010-.639C3.423 7.51 7.36 4.5 12 4.5c4.638 0 8.573 3.007 9.963 7.178.07.207.07.431 0 .639C20.577 16.49 16.64 19.5 12 19.5c-4.638 0-8.573-3.007-9.963-7.178z" />
              <path strokeLinecap="round" strokeLinejoin="round" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
            </svg>
            Preview
          </button>

          {/* Share: Copy Link / WhatsApp / Facebook / Messenger / Email / native share */}
          <ShareMenu
            url={shareUrl}
            title={gallery?.title || collection?.title}
            variant="button"
            note={isDraft ? "This collection is a draft — clients can't open the link until you publish it." : null}
          />

          {/* More Dropdown */}
          <div className="relative" ref={moreRef}>
            <button
              onClick={() => { setMoreOpen(!moreOpen); }}
              className="p-2 border border-cream-200 text-ink/60 hover:text-ink bg-surface-light hover:bg-cream-100 rounded-xl transition-all cursor-pointer shadow-sm"
            >
              <svg className="w-4 h-4" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" d="M6.75 12a.75.75 0 11-1.5 0 .75.75 0 011.5 0zM12.75 12a.75.75 0 11-1.5 0 .75.75 0 011.5 0zM18.75 12a.75.75 0 11-1.5 0 .75.75 0 011.5 0z" />
              </svg>
            </button>
            {moreOpen && (
              <div className="absolute top-full mt-1 right-0 bg-surface-light border border-cream-200 rounded-xl shadow-lg py-1 w-52 animate-scale-in z-50">
                <button onClick={handleCopyDirectLink} className="w-full text-left px-3 py-2 text-xs text-ink hover:bg-cream-100 transition-colors cursor-pointer">
                  Get direct link
                </button>
                <div className="border-t border-cream-200 my-1" />
                <button onClick={handleDelete} className="w-full text-left px-3 py-2 text-xs text-red-600 hover:bg-red-50 transition-colors cursor-pointer">
                  Delete collection
                </button>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
