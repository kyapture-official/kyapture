import { useState, useEffect, useRef } from "react";
import { useParams, useNavigate, Outlet } from "react-router-dom";
import { galleriesApi } from "../../api/galleriesApi";
import { mockGalleries } from "../../utils/mockGalleries";
import Spinner from "../../components/ui/Spinner";
import GallerySecondarySidebar from "../../components/layout/GallerySecondarySidebar";
import TopNavBar from "../../components/layout/TopNavBar";
import ClientPreviewModal from "../../components/shared/ClientPreviewModal";
import { PixiesetProvider, usePixieset } from "../../context/PixiesetContext";

const USE_MOCK_DATA = import.meta.env.VITE_USE_MOCK_DATA === "true";

function WorkspaceInner() {
  const { id } = useParams();
  const navigate = useNavigate();
  const { dispatch } = usePixieset();

  const [gallery, setGallery] = useState(null);
  const [loading, setLoading] = useState(true);
  const [errorMsg, setErrorMsg] = useState("");
  const [previewOpen, setPreviewOpen] = useState(false);

  const isMountedRef = useRef(false);
  const skipNextLoadRef = useRef(false);

  useEffect(() => {
    isMountedRef.current = true;
    return () => { isMountedRef.current = false; };
  }, []);

  useEffect(() => {
    async function loadGallery() {
      if (skipNextLoadRef.current) {
        skipNextLoadRef.current = false;
        setLoading(false);
        return;
      }
      setLoading(true);
      setErrorMsg("");

      if (USE_MOCK_DATA) {
        setTimeout(() => {
          const match = mockGalleries.find((g) => g.slug === id);
          if (!isMountedRef.current) return;
          if (!match) setErrorMsg("Collection not found.");
          else {
            setGallery(match);
            dispatch({
              type: "SET_COLLECTION",
              payload: {
                id: match.id,
                title: match.title,
                date: match.event_date || match.created_at,
                status: match.is_published ? "PUBLISHED" : "DRAFT",
                coverImage: match.cover_url,
                items: [],
              },
            });
          }
          setLoading(false);
        }, 300);
        return;
      }

      try {
        const data = await galleriesApi.getGallery(id);
        if (isMountedRef.current) {
          setGallery(data);
          dispatch({
            type: "SET_COLLECTION",
            payload: {
              id: data.id,
              title: data.title,
              date: data.event_date || data.created_at,
              status: data.is_published ? "PUBLISHED" : "DRAFT",
              coverImage: data.cover_url,
              items: [],
            },
          });
        }
      } catch (err) {
        if (isMountedRef.current) {
          setErrorMsg(err.response?.data?.detail || "Failed to retrieve collection.");
        }
      } finally {
        if (isMountedRef.current) setLoading(false);
      }
    }
    loadGallery();
  }, [id, dispatch]);

  // Listen for preview open event from TopNavBar
  useEffect(() => {
    const handler = () => setPreviewOpen(true);
    window.addEventListener("open-preview", handler);
    return () => window.removeEventListener("open-preview", handler);
  }, []);

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-slate-50">
        <Spinner size="lg" />
      </div>
    );
  }

  if (errorMsg && !gallery) {
    return (
      <div className="min-h-screen flex flex-col items-center justify-center bg-slate-50 px-6 text-center gap-4">
        <div className="w-14 h-14 rounded-full bg-red-50 flex items-center justify-center">
          <svg className="w-7 h-7 text-red-400" fill="none" stroke="currentColor" strokeWidth="1.5" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v3.75m9-.75a9 9 0 11-18 0 9 9 0 0118 0zm-9 3.75h.008v.008H12v-.008z" />
          </svg>
        </div>
        <p className="text-sm text-red-600">{errorMsg}</p>
        <button onClick={() => navigate("/dashboard/galleries")} className="text-sm font-semibold text-ink hover:underline">
          &larr; Back to Collections
        </button>
      </div>
    );
  }

  return (
    <div className="min-h-screen flex bg-slate-50">
      <GallerySecondarySidebar basePath={`/dashboard/galleries/${id}`} gallery={gallery} />

      <div className="flex-1 min-w-0 flex flex-col min-h-screen">
        <TopNavBar />

        {errorMsg && (
          <div className="max-w-5xl mx-auto px-4 md:px-6 pt-4 w-full">
            <div role="alert" className="p-4 rounded-xl bg-red-50 border border-red-200 text-sm text-red-700 flex items-center gap-2.5">
              <svg className="w-4 h-4 flex-shrink-0" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
              </svg>
              {errorMsg}
            </div>
          </div>
        )}

        <div className="flex-1 max-w-5xl mx-auto px-4 md:px-6 pt-6 pb-24 md:py-8 w-full">
          <Outlet context={{ gallery, setGallery, slug: id, skipNextLoadRef, navigate, isMountedRef }} />
        </div>
      </div>

      <ClientPreviewModal open={previewOpen} onClose={() => setPreviewOpen(false)} gallery={gallery} />
    </div>
  );
}

export default function GalleryWorkspaceLayout() {
  return (
    <PixiesetProvider>
      <WorkspaceInner />
    </PixiesetProvider>
  );
}
