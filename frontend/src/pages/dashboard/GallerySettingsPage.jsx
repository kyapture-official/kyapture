// frontend/src/pages/dashboard/GallerySettingsPage.jsx
import { useState } from "react";
import { useOutletContext } from "react-router-dom";
import { galleriesApi } from "../../api/galleriesApi";
import { toDateInputValue } from "../../utils/formatters";

const USE_MOCK_DATA = import.meta.env.VITE_USE_MOCK_DATA === "true";

/**
 * WHAT: The "Settings" child view of the collection workspace.
 * WHY:  Same context pattern as GalleryPhotosPage — reads gallery/slug
 *       from the parent layout instead of fetching its own copy.
 */
export default function GallerySettingsPage() {
  const { gallery, setGallery, slug, skipNextLoadRef, navigate, isMountedRef } =
    useOutletContext();

  const [title, setTitle] = useState(gallery.title);
  const [brandingColor, setBrandingColor] = useState(gallery.branding_color);
  const [isDownloadable, setIsDownloadable] = useState(gallery.is_downloadable);
  const [password, setPassword] = useState("");

  // BUG FIX: was gallery.event_date ? gallery.event_date.split("T")[0] : "".
  // toDateInputValue() handles the same "has a T" case but also validates
  // the result, so null/''/any unexpected backend shape safely becomes ''
  // instead of a value that LOOKS non-empty but still silently blanks the
  // <input type="date">.
  const [eventDate, setEventDate] = useState(toDateInputValue(gallery.event_date));
  const [expiresAt, setExpiresAt] = useState(toDateInputValue(gallery.expires_at));

  const [hasPassword, setHasPassword] = useState(gallery.has_password);
  const [watermarkEnabled, setWatermarkEnabled] = useState(
    gallery.watermark_enabled ?? false,
  );

  const [updating, setUpdating] = useState(false);
  const [errorMsg, setErrorMsg] = useState("");

  // ── SAVE COLLECTION CONFIG ───────────────────────────────────────────────
  const handleSaveSettings = async (e) => {
    e.preventDefault();
    if (!title.trim() || updating) return;

    setUpdating(true);
    setErrorMsg("");

    const payload = {
      title: title.trim(),
      branding_color: brandingColor,
      is_downloadable: isDownloadable,
      watermark_enabled: watermarkEnabled,
      event_date: eventDate || null,
      expires_at: expiresAt || null,
    };

    try {
      let updated;
      if (USE_MOCK_DATA) {
        const mockSlug = payload.title
          .toLowerCase()
          .replace(/[^a-z0-9]+/g, "-")
          .replace(/^-+|-+$/g, "");
        updated = { ...gallery, ...payload, slug: mockSlug };
      } else {
        updated = await galleriesApi.updateGallery(slug, payload);
      }

      // BUG FIX: removed the duplicate setGallery(updated) call and the
      // unused rawDate/formattedDate variables from the original — dead
      // code left over from an earlier edit pass.
      //
      // BUG FIX: freshDate previously fell back to updated.event_date ||
      // payload.event_date with a raw .split("T")[0] — same fragile
      // pattern as the initial state. toDateInputValue() covers both
      // sources the same validated way.
      setGallery(updated);
      setEventDate(toDateInputValue(updated.event_date ?? payload.event_date));
      setExpiresAt(toDateInputValue(updated.expires_at ?? payload.expires_at));
      setTitle(updated.title);
      setBrandingColor(updated.branding_color);
      setIsDownloadable(updated.is_downloadable);
      setHasPassword(updated.has_password);
      setWatermarkEnabled(updated.watermark_enabled);

      if (updated.slug !== slug) {
        skipNextLoadRef.current = true;
        navigate(`/dashboard/galleries/${updated.slug}/settings`, {
          replace: true,
        });
      }
    } catch (err) {
      if (isMountedRef.current) {
        setErrorMsg(
          err.response?.data?.detail ||
            "Failed to save collection configurations.",
        );
      }
    } finally {
      if (isMountedRef.current) setUpdating(false);
    }
  };

  // ── SAVE PASSWORD ────────────────────────────────────────────────────────
  const handleSavePassword = async (e) => {
    e.preventDefault();
    if (updating) return;

    if (!password && hasPassword) {
      const confirmed = window.confirm(
        "Remove password protection from this gallery? Clients will no longer need to authenticate.",
      );
      if (!confirmed) return;
    }

    setUpdating(true);
    setErrorMsg("");

    try {
      if (USE_MOCK_DATA) {
        const newHasPassword = Boolean(password);
        setHasPassword(newHasPassword);
        setGallery((prev) => ({ ...prev, has_password: newHasPassword }));
        setPassword("");
      } else {
        const response = await galleriesApi.setGalleryPassword(
          slug,
          password || null,
        );
        setHasPassword(response.has_password);
        setGallery((prev) => ({
          ...prev,
          has_password: response.has_password,
        }));
        setPassword("");
      }
    } catch (err) {
      if (isMountedRef.current) {
        setErrorMsg(
          err.response?.data?.detail ||
            "Failed to update security credentials.",
        );
      }
    } finally {
      if (isMountedRef.current) setUpdating(false);
    }
  };

  const ownerUsername =
    gallery.owner_username ?? gallery.photographer_username ?? "unknown";

  // ── RENDER ───────────────────────────────────────────────────────────────
  return (
    <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
      <div className="lg:col-span-2 space-y-8">
        {errorMsg && (
          <div
            role="alert"
            className="p-4 rounded-xl bg-red-50 border border-red-200 text-sm text-red-700 font-sans"
          >
            {errorMsg}
          </div>
        )}

        {/* Card 1: Configuration */}
        <div className="bg-white rounded-2xl border border-slate-200 shadow-card p-6">
          <div className="flex items-center gap-3 mb-6">
            <div className="w-9 h-9 rounded-xl bg-teal-50 flex items-center justify-center">
              <svg className="w-5 h-5 text-teal-600" fill="none" stroke="currentColor" strokeWidth="1.8" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" d="M9.594 3.94c.09-.542.56-.94 1.11-.94h2.593c.55 0 1.02.398 1.11.94l.213 1.281c.063.374.313.686.645.87.074.04.147.083.22.127.324.196.72.257 1.075.124l1.217-.456a1.125 1.125 0 011.37.49l1.296 2.247a1.125 1.125 0 01-.26 1.43l-1.003.828c-.293.241-.438.613-.43.992a7.723 7.723 0 010 .255c-.008.378.137.75.43.991l1.004.827c.424.35.534.954.26 1.43l-1.297 2.247a1.125 1.125 0 01-1.369.491l-1.217-.456c-.355-.133-.75-.072-1.076.124a6.47 6.47 0 01-.22.128c-.331.183-.581.495-.644.869l-.213 1.281c-.09.543-.56.94-1.11.94h-2.594c-.552 0-1.02-.398-1.11-.94l-.213-1.281c-.062-.374-.312-.686-.644-.87a6.52 6.52 0 01-.22-.127c-.325-.196-.72-.257-1.076-.124l-1.217.456a1.125 1.125 0 01-1.369-.49l-1.297-2.247a1.125 1.125 0 01.26-1.43l1.004-.827c.292-.24.437-.613.43-.991a6.932 6.932 0 010-.255c.007-.38-.138-.751-.43-.992l-1.004-.827a1.125 1.125 0 01-.26-1.43l1.297-2.247a1.125 1.125 0 011.37-.491l1.216.456c.356.133.751.072 1.076-.124.072-.044.146-.086.22-.128.332-.183.582-.495.644-.869l.214-1.28Z" />
                <path strokeLinecap="round" strokeLinejoin="round" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
              </svg>
            </div>
            <h2 className="font-serif text-lg text-ink">Collection Configurations</h2>
          </div>
          <form onSubmit={handleSaveSettings} noValidate className="space-y-6">
            <div className="flex flex-col gap-1">
              <label
                className="text-xs font-semibold text-ink/80"
                htmlFor="gallery-title"
              >
                Gallery Title
              </label>
              <input
                id="gallery-title"
                type="text"
                value={title}
                maxLength={100}
                onChange={(e) => setTitle(e.target.value)}
                disabled={updating}
                className="w-full px-3 py-2 text-sm rounded-lg border border-slate-200 focus:border-teal-500 focus:outline-none focus:ring-2 focus:ring-teal-500/10 transition-all disabled:opacity-50"
                required
              />
            </div>

            <div className="p-4 bg-slate-50 rounded-xl border border-slate-100 text-xs">
              <span className="font-semibold text-muted uppercase tracking-wider block text-[10px]">
                Live Slug Link
              </span>
              <p className="mt-1 font-semibold text-ink/70 truncate">
                yourname.kyapture.com/g/{ownerUsername}/
                <span className="text-ink font-bold font-mono">
                  {title
                    .toLowerCase()
                    .trim()
                    .replace(/[^a-z0-9]+/g, "-")
                    .replace(/^-+|-+$/g, "") || "your-slug"}
                </span>
              </p>
            </div>

            <div className="flex flex-col gap-1">
              <label
                className="text-xs font-semibold text-ink/80"
                htmlFor="gallery-event-date"
              >
                Event Date
              </label>
              <input
                id="gallery-event-date"
                type="date"
                value={eventDate}
                onChange={(e) => setEventDate(e.target.value)}
                disabled={updating}
                className="w-full px-3 py-2 text-sm rounded-lg border border-slate-200 focus:border-teal-500 focus:outline-none focus:ring-2 focus:ring-teal-500/10 transition-all disabled:opacity-50"
              />
            </div>

            <div className="flex flex-col gap-1">
              <label
                className="text-xs font-semibold text-ink/80"
                htmlFor="gallery-expires-at"
              >
                Gallery Expiration Date (Optional)
              </label>
              <input
                id="gallery-expires-at"
                type="date"
                value={expiresAt}
                onChange={(e) => setExpiresAt(e.target.value)}
                disabled={updating}
                className="w-full px-3 py-2 text-sm rounded-lg border border-slate-200 focus:border-teal-500 focus:outline-none focus:ring-2 focus:ring-teal-500/10 transition-all disabled:opacity-50"
              />
              <span className="text-[11px] text-muted">
                After this date, clients will lose access to view and download photos. Leave blank for no expiration.
              </span>
            </div>

            <div className="flex flex-col gap-1">
              <label
                className="text-xs font-semibold text-ink/80"
                htmlFor="gallery-color"
              >
                Photographer Brand Accent
              </label>
              <div className="flex items-center gap-3">
                <input
                  id="gallery-color"
                  type="color"
                  value={brandingColor}
                  onChange={(e) => setBrandingColor(e.target.value)}
                  disabled={updating}
                  className="w-10 h-10 rounded-lg border border-slate-200 cursor-pointer overflow-hidden p-0 bg-transparent disabled:cursor-not-allowed"
                />
                <span className="text-xs text-muted font-medium font-mono uppercase">
                  {brandingColor}
                </span>
              </div>
            </div>

            <div className="flex items-center gap-2 pt-2 border-t border-slate-100">
              <input
                id="gallery-download"
                type="checkbox"
                checked={isDownloadable}
                onChange={(e) => setIsDownloadable(e.target.checked)}
                disabled={updating}
                className="w-4 h-4 rounded border-slate-300 text-teal-600 focus:ring-teal-500 cursor-pointer disabled:cursor-not-allowed"
              />
              <label
                className="text-xs font-semibold text-ink/80 cursor-pointer select-none"
                htmlFor="gallery-download"
              >
                Allow clients to download high-resolution photos
              </label>
            </div>

            <div className="flex items-center gap-2 pt-2 border-t border-slate-100">
              <input
                id="gallery-watermark"
                type="checkbox"
                checked={watermarkEnabled}
                onChange={(e) => setWatermarkEnabled(e.target.checked)}
                disabled={updating}
                className="w-4 h-4 rounded border-slate-300 text-teal-600 focus:ring-teal-500 cursor-pointer disabled:cursor-not-allowed"
              />
              <label
                className="text-xs font-semibold text-ink/80 cursor-pointer select-none"
                htmlFor="gallery-watermark"
              >
                Apply copyright watermark to photos
              </label>
            </div>

            <div className="flex justify-end pt-4 border-t border-slate-100">
              <button
                type="submit"
                disabled={
                  updating ||
                  !title.trim() ||
                  (title.trim() === gallery.title &&
                    brandingColor === gallery.branding_color &&
                    isDownloadable === gallery.is_downloadable &&
                    watermarkEnabled === (gallery.watermark_enabled ?? false) &&
                    // BUG FIX: both sides now go through the SAME
                    // toDateInputValue() helper instead of eventDate (raw
                    // input value) being compared against an independently
                    // inline-trimmed gallery.event_date. Two different
                    // conversions of the same value can silently drift —
                    // one shared helper can't.
                    eventDate === toDateInputValue(gallery.event_date) &&
                  expiresAt === toDateInputValue(gallery.expires_at))
                }
                className="px-4 py-2 bg-teal-600 text-white text-sm font-medium rounded-lg hover:bg-teal-700 transition-colors cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {updating ? "Saving..." : "Save Settings"}
              </button>
            </div>
          </form>
        </div>

        {/* Card 2: Password Protection */}
        <div className="bg-white rounded-2xl border border-slate-200 shadow-card p-6">
          <div className="flex items-center gap-3 mb-2">
            <div className="w-9 h-9 rounded-xl bg-blue-50 flex items-center justify-center">
              <svg className="w-5 h-5 text-blue-600" fill="none" stroke="currentColor" strokeWidth="1.8" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" d="M16.5 10.5V6.75a4.5 4.5 0 10-9 0v3.75m-.75 11.25h10.5a2.25 2.25 0 002.25-2.25v-6.75a2.25 2.25 0 00-2.25-2.25H6.75a2.25 2.25 0 00-2.25 2.25v6.75a2.25 2.25 0 002.25 2.25z" />
              </svg>
            </div>
            <h2 className="font-serif text-lg text-ink">Password Protection</h2>
          </div>
          <p className="text-xs text-muted mb-6">
            When password protection is enabled, clients must authenticate
            before entering the public photo grid.
          </p>

          <form onSubmit={handleSavePassword} className="space-y-4">
            <div className="flex flex-col gap-1">
              <label
                className="text-xs font-semibold text-ink/80"
                htmlFor="gallery-password"
              >
                {hasPassword
                  ? "Update/Clear Password"
                  : "Set Protection Password"}
              </label>
              <div className="flex gap-3">
                <input
                  id="gallery-password"
                  type="password"
                  placeholder={
                    hasPassword ? "••••••••" : "Enter security password"
                  }
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  disabled={updating}
                  className="flex-1 px-3 py-2 text-sm rounded-lg border border-slate-200 focus:border-teal-500 focus:outline-none focus:ring-2 focus:ring-teal-500/10 transition-all disabled:opacity-50"
                />
                <button
                  type="submit"
                  disabled={updating}
                  className="px-4 py-2 border border-slate-200 text-slate-700 hover:text-ink hover:bg-slate-50 text-sm font-medium rounded-lg transition-colors cursor-pointer disabled:opacity-50"
                >
                  {password
                    ? "Save"
                    : hasPassword
                      ? "Clear Protection"
                      : "Set Lock"}
                </button>
              </div>
            </div>
          </form>
        </div>
      </div>

      {/* Right column — existing preview card, unchanged */}
      <div className="space-y-8">
        <div className="bg-white rounded-2xl border border-slate-200 shadow-card overflow-hidden p-6 flex flex-col items-center justify-center text-center py-10 min-h-[300px]">
          {gallery.cover_url ? (
            <img
              src={gallery.cover_url}
              alt={`${gallery.title} cover`}
              className="w-24 h-24 rounded-full object-cover border border-slate-100 mb-4 shadow-sm"
            />
          ) : (
            <div
              className="w-16 h-16 rounded-full flex items-center justify-center text-white/30 mb-4"
              style={{ backgroundColor: brandingColor }}
            >
              <svg
                xmlns="http://www.w3.org/2000/svg"
                width="24"
                height="24"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
              >
                <path d="M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 1 2 2z" />
                <circle cx="12" cy="13" r="4" />
              </svg>
            </div>
          )}
          <h3 className="text-sm font-semibold text-ink">{gallery.title}</h3>
          <span
            className={`inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-medium border mt-2 ${
              gallery.is_published
                ? "bg-emerald-50 text-emerald-700 border-emerald-200"
                : "bg-amber-50 text-amber-700 border-amber-200"
            }`}
          >
            {gallery.is_published ? "Published" : "Draft"}
          </span>
        </div>
      </div>
    </div>
  );
}