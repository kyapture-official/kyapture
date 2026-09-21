import { useState } from "react";
import { useOutletContext } from "react-router-dom";
import { galleriesApi } from "../../api/galleriesApi";
import { useToast } from "../../components/ui/Toast";
import { toDateInputValue } from "../../utils/formatters";

const USE_MOCK_DATA = import.meta.env.VITE_USE_MOCK_DATA === "true";

export default function GallerySettingsPage() {
  const { gallery, setGallery, slug, skipNextLoadRef, navigate, isMountedRef } = useOutletContext();
  const toast = useToast();

  const [activeTab, setActiveTab] = useState("general");

  const [title, setTitle] = useState(gallery.title);
  const [brandingColor, setBrandingColor] = useState(gallery.branding_color);
  const [isDownloadable, setIsDownloadable] = useState(gallery.is_downloadable);
  const [password, setPassword] = useState("");
  const [eventDate, setEventDate] = useState(toDateInputValue(gallery.event_date));
  const [expiresAt, setExpiresAt] = useState(toDateInputValue(gallery.expires_at));
  const [hasPassword, setHasPassword] = useState(gallery.has_password);
  const [watermarkEnabled, setWatermarkEnabled] = useState(gallery.watermark_enabled ?? false);
  const [updating, setUpdating] = useState(false);
  const [errorMsg, setErrorMsg] = useState("");

  // Settings sub-state
  const [customUrl, setCustomUrl] = useState(gallery.custom_url || "davilandd");
  const [categoryTags, setCategoryTags] = useState(gallery.category_tags || "");
  const [downloadPin, setDownloadPin] = useState("");
  const [pinEnabled, setPinEnabled] = useState(gallery.download_pin_enabled ?? false);
  const [favoritesEnabled, setFavoritesEnabled] = useState(gallery.favorites_enabled ?? true);
  const [storeEnabled, setStoreEnabled] = useState(gallery.store_enabled ?? false);
  const [sliderEnabled, setSliderEnabled] = useState(gallery.slider_enabled ?? false);
  const [slideshowEnabled, setSlideshowEnabled] = useState(gallery.slideshow_enabled ?? false);

  const tabs = [
    { id: "general", label: "General" },
    { id: "privacy", label: "Privacy" },
    { id: "download", label: "Download" },
    { id: "favorites", label: "Favorites" },
    { id: "store", label: "Store" },
  ];

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
      custom_url: customUrl,
      category_tags: categoryTags,
      download_pin_enabled: pinEnabled,
      favorites_enabled: favoritesEnabled,
      store_enabled: storeEnabled,
      slider_enabled: sliderEnabled,
      slideshow_enabled: slideshowEnabled,
    };

    try {
      let updated;
      if (USE_MOCK_DATA) {
        const mockSlug = payload.title.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "");
        updated = { ...gallery, ...payload, slug: mockSlug };
      } else {
        updated = await galleriesApi.updateGallery(slug, payload);
      }
      setGallery(updated);
      setTitle(updated.title);
      setBrandingColor(updated.branding_color);
      setIsDownloadable(updated.is_downloadable);
      setHasPassword(updated.has_password);
      setWatermarkEnabled(updated.watermark_enabled);
      toast("Settings saved successfully", "success");
      if (updated.slug !== slug) {
        skipNextLoadRef.current = true;
        navigate(`/dashboard/galleries/${updated.slug}/settings`, { replace: true });
      }
    } catch (err) {
      if (isMountedRef.current) {
        setErrorMsg(err.response?.data?.detail || "Failed to save settings.");
        toast("Failed to save settings", "error");
      }
    } finally {
      if (isMountedRef.current) setUpdating(false);
    }
  };

  const handleSavePassword = async (e) => {
    e.preventDefault();
    if (updating) return;
    if (!password && hasPassword) {
      if (!window.confirm("Remove password protection?")) return;
    }
    setUpdating(true);
    try {
      if (USE_MOCK_DATA) {
        const newHasPassword = Boolean(password);
        setHasPassword(newHasPassword);
        setGallery((prev) => ({ ...prev, has_password: newHasPassword }));
        setPassword("");
        toast(password ? "Password set" : "Password removed", "success");
      } else {
        const response = await galleriesApi.setGalleryPassword(slug, password || null);
        setHasPassword(response.has_password);
        setGallery((prev) => ({ ...prev, has_password: response.has_password }));
        setPassword("");
        toast(password ? "Password set" : "Password removed", "success");
      }
    } catch (err) {
      if (isMountedRef.current) {
        setErrorMsg(err.response?.data?.detail || "Failed to update password.");
        toast("Failed to update password", "error");
      }
    } finally {
      if (isMountedRef.current) setUpdating(false);
    }
  };

  const ownerUsername = gallery.owner_username ?? gallery.photographer_username ?? "unknown";

  return (
    <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
      <div className="lg:col-span-2 space-y-6">
        {/* Tab bar */}
        <div className="flex gap-1 bg-slate-100 rounded-xl p-1 overflow-x-auto">
          {tabs.map((tab) => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`flex-none px-4 py-2.5 text-xs font-medium rounded-lg transition-all cursor-pointer ${
                activeTab === tab.id
                  ? "bg-white text-ink shadow-sm"
                  : "text-muted hover:text-ink"
              }`}
            >
              {tab.label}
            </button>
          ))}
        </div>

        {errorMsg && (
          <div role="alert" className="p-4 rounded-xl bg-red-50 border border-red-200 text-sm text-red-700">
            {errorMsg}
          </div>
        )}

        {/* General Tab */}
        {activeTab === "general" && (
          <div className="bg-white rounded-2xl border border-slate-200 shadow-card p-6">
            <h2 className="font-serif text-lg text-ink mb-6">General Settings</h2>
            <form onSubmit={handleSaveSettings} noValidate className="space-y-5">
              <div className="flex flex-col gap-1">
                <label className="text-xs font-semibold text-ink/80" htmlFor="gallery-title">Gallery Title</label>
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
                <span className="font-semibold text-muted uppercase tracking-wider block text-[10px]">Custom URL</span>
                <div className="mt-2 flex items-center gap-2">
                  <input
                    type="text"
                    value={customUrl}
                    onChange={(e) => setCustomUrl(e.target.value)}
                    disabled={updating}
                    className="flex-1 px-2 py-1.5 text-sm rounded-lg border border-slate-200 focus:border-teal-500 focus:outline-none focus:ring-2 focus:ring-teal-500/10 transition-all font-mono text-ink bg-white disabled:opacity-50"
                    placeholder="your-username"
                  />
                </div>
                <p className="mt-1.5 text-muted truncate">
                  /g/<span className="text-ink font-bold">{customUrl || "your-username"}</span>/
                  <span className="text-ink font-mono">{title.toLowerCase().trim().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "") || "your-slug"}</span>
                </p>
              </div>

              <div className="flex flex-col gap-1">
                <label className="text-xs font-semibold text-ink/80" htmlFor="gallery-tags">Category Tags</label>
                <input
                  id="gallery-tags"
                  type="text"
                  value={categoryTags}
                  onChange={(e) => setCategoryTags(e.target.value)}
                  disabled={updating}
                  placeholder="e.g. wedding, portraits, outdoor"
                  className="w-full px-3 py-2 text-sm rounded-lg border border-slate-200 focus:border-teal-500 focus:outline-none focus:ring-2 focus:ring-teal-500/10 transition-all disabled:opacity-50"
                />
              </div>

              <div className="flex flex-col gap-1">
                <label className="text-xs font-semibold text-ink/80" htmlFor="gallery-event-date">Event Date</label>
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
                <label className="text-xs font-semibold text-ink/80" htmlFor="gallery-expires">Expiration Date (Optional)</label>
                <input
                  id="gallery-expires"
                  type="date"
                  value={expiresAt}
                  onChange={(e) => setExpiresAt(e.target.value)}
                  disabled={updating}
                  className="w-full px-3 py-2 text-sm rounded-lg border border-slate-200 focus:border-teal-500 focus:outline-none focus:ring-2 focus:ring-teal-500/10 transition-all disabled:opacity-50"
                />
                <span className="text-[11px] text-muted">After this date, clients lose access.</span>
              </div>

              <div className="flex flex-col gap-1">
                <label className="text-xs font-semibold text-ink/80" htmlFor="gallery-watermark">Default Watermark</label>
                <div className="flex items-center gap-3">
                  <input
                    id="gallery-watermark"
                    type="checkbox"
                    checked={watermarkEnabled}
                    onChange={(e) => setWatermarkEnabled(e.target.checked)}
                    disabled={updating}
                    className="w-4 h-4 rounded border-slate-300 text-teal-600 focus:ring-teal-500 cursor-pointer disabled:cursor-not-allowed"
                  />
                  <label className="text-xs text-muted cursor-pointer select-none" htmlFor="gallery-watermark">
                    Apply copyright watermark to photos
                  </label>
                </div>
              </div>

              <div className="flex justify-end pt-4 border-t border-slate-100">
                <button
                  type="submit"
                  disabled={updating || !title.trim()}
                  className="px-4 py-2 bg-teal-600 text-white text-sm font-medium rounded-lg hover:bg-teal-700 transition-colors cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  {updating ? "Saving..." : "Save Settings"}
                </button>
              </div>
            </form>
          </div>
        )}

        {/* Privacy Tab */}
        {activeTab === "privacy" && (
          <div className="bg-white rounded-2xl border border-slate-200 shadow-card p-6">
            <h2 className="font-serif text-lg text-ink mb-2">Privacy & Security</h2>
            <p className="text-xs text-muted mb-6">Control access to your gallery.</p>

            <div className="space-y-5">
              <div className="flex items-center justify-between p-4 bg-slate-50 rounded-xl border border-slate-100">
                <div>
                  <p className="text-sm font-medium text-ink">Password Protection</p>
                  <p className="text-xs text-muted mt-0.5">Require a password to view the gallery</p>
                </div>
                <label className="toggle-wrap">
                  <input type="checkbox" checked={hasPassword} onChange={(e) => {
                    if (!e.target.checked) {
                      handleSavePassword({ preventDefault: () => {} });
                    }
                  }} />
                  <span className="toggle-slider" />
                </label>
              </div>

              <form onSubmit={handleSavePassword} className="flex gap-3">
                <input
                  type="password"
                  placeholder={hasPassword ? "Enter new password" : "Set a password"}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  disabled={updating}
                  className="flex-1 px-3 py-2 text-sm rounded-lg border border-slate-200 focus:border-teal-500 focus:outline-none focus:ring-2 focus:ring-teal-500/10 transition-all disabled:opacity-50"
                />
                <button
                  type="submit"
                  disabled={updating}
                  className="px-4 py-2 border border-slate-200 text-ink text-sm font-medium rounded-lg hover:bg-slate-50 transition-colors cursor-pointer disabled:opacity-50"
                >
                  {password ? "Save" : hasPassword ? "Clear" : "Set"}
                </button>
              </form>
            </div>
          </div>
        )}

        {/* Download Tab */}
        {activeTab === "download" && (
          <div className="bg-white rounded-2xl border border-slate-200 shadow-card p-6">
            <h2 className="font-serif text-lg text-ink mb-2">Download Settings</h2>
            <p className="text-xs text-muted mb-6">Control how clients download photos.</p>

            <div className="space-y-4">
              <div className="flex items-center justify-between p-4 bg-slate-50 rounded-xl border border-slate-100">
                <div>
                  <p className="text-sm font-medium text-ink">Allow Downloads</p>
                  <p className="text-xs text-muted mt-0.5">Let clients download high-resolution photos</p>
                </div>
                <label className="toggle-wrap">
                  <input type="checkbox" checked={isDownloadable} onChange={(e) => setIsDownloadable(e.target.checked)} />
                  <span className="toggle-slider" />
                </label>
              </div>

              <div className="flex items-center justify-between p-4 bg-slate-50 rounded-xl border border-slate-100">
                <div>
                  <p className="text-sm font-medium text-ink">Download PIN</p>
                  <p className="text-xs text-muted mt-0.5">Require a PIN to download photos</p>
                </div>
                <label className="toggle-wrap">
                  <input type="checkbox" checked={pinEnabled} onChange={(e) => setPinEnabled(e.target.checked)} />
                  <span className="toggle-slider" />
                </label>
              </div>

              {pinEnabled && (
                <div className="flex flex-col gap-1 ml-4">
                  <label className="text-xs font-semibold text-ink/80">Set Download PIN</label>
                  <input
                    type="text"
                    value={downloadPin}
                    onChange={(e) => setDownloadPin(e.target.value)}
                    placeholder="Enter 4-6 digit PIN"
                    maxLength={6}
                    className="w-full max-w-xs px-3 py-2 text-sm rounded-lg border border-slate-200 focus:border-teal-500 focus:outline-none focus:ring-2 focus:ring-teal-500/10 transition-all font-mono"
                  />
                </div>
              )}
            </div>
          </div>
        )}

        {/* Favorites Tab */}
        {activeTab === "favorites" && (
          <div className="bg-white rounded-2xl border border-slate-200 shadow-card p-6">
            <h2 className="font-serif text-lg text-ink mb-2">Favorites</h2>
            <p className="text-xs text-muted mb-6">Let clients mark their favorite photos.</p>

            <div className="flex items-center justify-between p-4 bg-slate-50 rounded-xl border border-slate-100">
              <div>
                <p className="text-sm font-medium text-ink">Enable Favorites</p>
                <p className="text-xs text-muted mt-0.5">Clients can heart photos to create a favorites list</p>
              </div>
              <label className="toggle-wrap">
                <input type="checkbox" checked={favoritesEnabled} onChange={(e) => setFavoritesEnabled(e.target.checked)} />
                <span className="toggle-slider" />
              </label>
            </div>
          </div>
        )}

        {/* Store Tab */}
        {activeTab === "store" && (
          <div className="bg-white rounded-2xl border border-slate-200 shadow-card p-6">
            <h2 className="font-serif text-lg text-ink mb-2">Store</h2>
            <p className="text-xs text-muted mb-6">Enable print sales directly from your gallery.</p>

            <div className="flex items-center justify-between p-4 bg-slate-50 rounded-xl border border-slate-100">
              <div>
                <p className="text-sm font-medium text-ink">Enable Store</p>
                <p className="text-xs text-muted mt-0.5">Clients can purchase prints and products</p>
              </div>
              <label className="toggle-wrap">
                <input type="checkbox" checked={storeEnabled} onChange={(e) => setStoreEnabled(e.target.checked)} />
                <span className="toggle-slider" />
              </label>
            </div>
          </div>
        )}
      </div>

      {/* Right sidebar — preview */}
      <div className="space-y-8">
        <div className="bg-white rounded-2xl border border-slate-200 shadow-card overflow-hidden p-6 flex flex-col items-center justify-center text-center py-10 min-h-[300px]">
          {gallery.cover_url ? (
            <img src={gallery.cover_url} alt="" className="w-24 h-24 rounded-full object-cover border border-slate-100 mb-4 shadow-sm" />
          ) : (
            <div className="w-16 h-16 rounded-full flex items-center justify-center text-white/30" style={{ backgroundColor: brandingColor }}>
              <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 1 2 2z" />
                <circle cx="12" cy="13" r="4" />
              </svg>
            </div>
          )}
          <h3 className="text-sm font-semibold text-ink">{gallery.title}</h3>
          <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-medium border mt-2 ${
            gallery.is_published ? "bg-emerald-50 text-emerald-700 border-emerald-200" : "bg-amber-50 text-amber-700 border-amber-200"
          }`}>
            {gallery.is_published ? "Published" : "Draft"}
          </span>
        </div>
      </div>
    </div>
  );
}
