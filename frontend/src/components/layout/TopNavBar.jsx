import { useState, useRef, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { usePixieset } from "../../context/PixiesetContext";

export default function TopNavBar() {
  const navigate = useNavigate();
  const { collection, publishCollection, unpublishCollection, addToast } = usePixieset();
  const [moreOpen, setMoreOpen] = useState(false);
  const [shareOpen, setShareOpen] = useState(false);
  const [statusOpen, setStatusOpen] = useState(false);
  const moreRef = useRef(null);
  const shareRef = useRef(null);
  const statusRef = useRef(null);

  useEffect(() => {
    const close = (e) => {
      if (moreRef.current && !moreRef.current.contains(e.target)) setMoreOpen(false);
      if (shareRef.current && !shareRef.current.contains(e.target)) setShareOpen(false);
      if (statusRef.current && !statusRef.current.contains(e.target)) setStatusOpen(false);
    };
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, []);

  const handleStatusToggle = () => {
    if (collection.status === "PUBLISHED") {
      unpublishCollection();
      addToast({ message: "Collection set to Draft", type: "info" });
    } else {
      publishCollection();
      addToast({ message: "Collection published!", type: "success" });
    }
    setStatusOpen(false);
  };

  const handleCopyLink = async () => {
    try {
      await navigator.clipboard.writeText(window.location.href);
      addToast({ message: "Link copied!", type: "success" });
    } catch {
      addToast({ message: "Failed to copy link", type: "error" });
    }
    setShareOpen(false);
  };

  const handleCopyDirectLink = async () => {
    try {
      await navigator.clipboard.writeText(window.location.href);
      addToast({ message: "Direct link copied!", type: "success" });
    } catch {
      addToast({ message: "Failed to copy link", type: "error" });
    }
    setMoreOpen(false);
  };

  const handleDelete = () => {
    if (window.confirm("Delete this collection? This cannot be undone.")) {
      addToast({ message: "Collection deleted", type: "info" });
      navigate("/dashboard/galleries");
    }
    setMoreOpen(false);
  };

  const isPublished = collection.status === "PUBLISHED";

  return (
    <div className="sticky top-0 z-20 bg-white/80 backdrop-blur-md border-b border-slate-200">
      <div className="flex items-center justify-between gap-4 px-4 md:px-6 py-3">
        {/* Left: Breadcrumbs + Status */}
        <div className="flex items-center gap-2 min-w-0">
          <button
            onClick={() => navigate("/dashboard/galleries")}
            className="text-xs text-muted hover:text-ink hover:underline transition-colors cursor-pointer flex-shrink-0"
          >
            Collections
          </button>
          <svg className="w-3 h-3 text-slate-400 flex-shrink-0" fill="none" stroke="currentColor" strokeWidth="2.5" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" d="M8.25 4.5l7.5 7.5-7.5 7.5" />
          </svg>
          <span className="text-xs font-semibold text-ink truncate max-w-[200px]">
            {collection.title || "Untitled"}
          </span>

          {/* Status Badge Dropdown */}
          <div className="relative" ref={statusRef}>
            <button
              onClick={() => setStatusOpen(!statusOpen)}
              className={`inline-flex items-center px-2.5 py-1 rounded-full text-[10px] font-medium border cursor-pointer transition-all ${
                isPublished
                  ? "bg-emerald-50 text-emerald-700 border-emerald-200 hover:bg-emerald-100"
                  : "bg-slate-100 text-slate-600 border-slate-200 hover:bg-slate-200"
              }`}
            >
              {isPublished ? "Published" : "Draft"}
              <svg className="w-2.5 h-2.5 ml-1" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" d="M19.5 8.25l-7.5 7.5-7.5-7.5" />
              </svg>
            </button>
            {statusOpen && (
              <div className="absolute top-full mt-1 left-0 bg-white border border-slate-200 rounded-xl shadow-lg py-1 w-40 animate-scale-in z-50">
                <button
                  onClick={handleStatusToggle}
                  className="w-full text-left px-3 py-2 text-xs text-ink hover:bg-slate-50 transition-colors cursor-pointer"
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
            className="hidden sm:flex items-center gap-1.5 px-3 py-2 border border-slate-200 text-ink/80 hover:text-ink bg-white hover:bg-slate-50 text-xs font-medium rounded-xl transition-all cursor-pointer shadow-sm hover:shadow"
          >
            <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" strokeWidth="1.8" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" d="M2.036 12.322a1.012 1.012 0 010-.639C3.423 7.51 7.36 4.5 12 4.5c4.638 0 8.573 3.007 9.963 7.178.07.207.07.431 0 .639C20.577 16.49 16.64 19.5 12 19.5c-4.638 0-8.573-3.007-9.963-7.178z" />
              <path strokeLinecap="round" strokeLinejoin="round" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
            </svg>
            Preview
          </button>

          {/* Share Dropdown */}
          <div className="relative" ref={shareRef}>
            <button
              onClick={() => { setShareOpen(!shareOpen); setMoreOpen(false); }}
              className="flex items-center gap-1.5 px-3 py-2 border border-slate-200 text-ink/80 hover:text-ink bg-white hover:bg-slate-50 text-xs font-medium rounded-xl transition-all cursor-pointer shadow-sm hover:shadow"
            >
              <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" strokeWidth="1.8" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" d="M7.217 10.907a2.25 2.25 0 100 2.186m0-2.186c.18.324.283.696.283 1.093s-.103.77-.283 1.093m0-2.186l9.566-5.314m-9.566 7.5l9.566 5.314m0 0a2.25 2.25 0 103.935 2.186 2.25 2.25 0 00-3.935-2.186zm0-12.814a2.25 2.25 0 103.933-2.185 2.25 2.25 0 00-3.933 2.185z" />
              </svg>
              Share
            </button>
            {shareOpen && (
              <div className="absolute top-full mt-1 right-0 bg-white border border-slate-200 rounded-xl shadow-lg py-1 w-48 animate-scale-in z-50">
                <button
                  onClick={() => { addToast({ message: "Share by email coming soon", type: "info" }); setShareOpen(false); }}
                  className="w-full text-left px-3 py-2 text-xs text-ink hover:bg-slate-50 transition-colors cursor-pointer flex items-center gap-2"
                >
                  <svg className="w-3.5 h-3.5 text-muted" fill="none" stroke="currentColor" strokeWidth="1.8" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" d="M21.75 6.75v10.5a2.25 2.25 0 01-2.25 2.25h-15a2.25 2.25 0 01-2.25-2.25V6.75m19.5 0A2.25 2.25 0 0019.5 4.5h-15a2.25 2.25 0 00-2.25 2.25m19.5 0v.243a2.25 2.25 0 01-1.07 1.916l-7.5 4.615a2.25 2.25 0 01-2.36 0L3.32 8.91a2.25 2.25 0 01-1.07-1.916V6.75" />
                  </svg>
                  Share by email
                </button>
                <button
                  onClick={handleCopyDirectLink}
                  className="w-full text-left px-3 py-2 text-xs text-ink hover:bg-slate-50 transition-colors cursor-pointer flex items-center gap-2"
                >
                  <svg className="w-3.5 h-3.5 text-muted" fill="none" stroke="currentColor" strokeWidth="1.8" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" d="M13.19 8.688a4.5 4.5 0 011.242 7.244l-4.5 4.5a4.5 4.5 0 01-6.364-6.364l1.757-1.757m13.35-.622l1.757-1.757a4.5 4.5 0 00-6.364-6.364l-4.5 4.5a4.5 4.5 0 001.242 7.244" />
                  </svg>
                  Get direct link
                </button>
                <button
                  onClick={() => { addToast({ message: "QR code coming soon", type: "info" }); setShareOpen(false); }}
                  className="w-full text-left px-3 py-2 text-xs text-ink hover:bg-slate-50 transition-colors cursor-pointer flex items-center gap-2"
                >
                  <svg className="w-3.5 h-3.5 text-muted" fill="none" stroke="currentColor" strokeWidth="1.8" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" d="M3.75 4.875c0-.621.504-1.125 1.125-1.125h4.5c.621 0 1.125.504 1.125 1.125v4.5c0 .621-.504 1.125-1.125 1.125h-4.5A1.125 1.125 0 013.75 9.375v-4.5zM3.75 14.625c0-.621.504-1.125 1.125-1.125h4.5c.621 0 1.125.504 1.125 1.125v4.5c0 .621-.504 1.125-1.125 1.125h-4.5a1.125 1.125 0 01-1.125-1.125v-4.5zM13.5 4.875c0-.621.504-1.125 1.125-1.125h4.5c.621 0 1.125.504 1.125 1.125v4.5c0 .621-.504 1.125-1.125 1.125h-4.5a1.125 1.125 0 01-1.125-1.125v-4.5zM13.5 14.625c0-.621.504-1.125 1.125-1.125h4.5c.621 0 1.125.504 1.125 1.125v4.5c0 .621-.504 1.125-1.125 1.125h-4.5a1.125 1.125 0 01-1.125-1.125v-4.5z" />
                  </svg>
                  Get QR code
                </button>
              </div>
            )}
          </div>

          {/* More Dropdown */}
          <div className="relative" ref={moreRef}>
            <button
              onClick={() => { setMoreOpen(!moreOpen); setShareOpen(false); }}
              className="p-2 border border-slate-200 text-ink/60 hover:text-ink bg-white hover:bg-slate-50 rounded-xl transition-all cursor-pointer shadow-sm"
            >
              <svg className="w-4 h-4" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" d="M6.75 12a.75.75 0 11-1.5 0 .75.75 0 011.5 0zM12.75 12a.75.75 0 11-1.5 0 .75.75 0 011.5 0zM18.75 12a.75.75 0 11-1.5 0 .75.75 0 011.5 0z" />
              </svg>
            </button>
            {moreOpen && (
              <div className="absolute top-full mt-1 right-0 bg-white border border-slate-200 rounded-xl shadow-lg py-1 w-52 animate-scale-in z-50">
                <button onClick={handleCopyDirectLink} className="w-full text-left px-3 py-2 text-xs text-ink hover:bg-slate-50 transition-colors cursor-pointer">
                  Get direct link
                </button>
                <button onClick={() => { addToast({ message: "Email history coming soon", type: "info" }); setMoreOpen(false); }} className="w-full text-left px-3 py-2 text-xs text-ink hover:bg-slate-50 transition-colors cursor-pointer">
                  View email history
                </button>
                <button onClick={() => { addToast({ message: "Presets coming soon", type: "info" }); setMoreOpen(false); }} className="w-full text-left px-3 py-2 text-xs text-ink hover:bg-slate-50 transition-colors cursor-pointer">
                  Manage presets
                </button>
                <button onClick={() => { addToast({ message: "Move coming soon", type: "info" }); setMoreOpen(false); }} className="w-full text-left px-3 py-2 text-xs text-ink hover:bg-slate-50 transition-colors cursor-pointer">
                  Move to...
                </button>
                <button onClick={() => { addToast({ message: "Duplicate coming soon", type: "info" }); setMoreOpen(false); }} className="w-full text-left px-3 py-2 text-xs text-ink hover:bg-slate-50 transition-colors cursor-pointer">
                  Duplicate
                </button>
                <div className="border-t border-slate-100 my-1" />
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
