// C:\Users\David\Desktop\kyapture\frontend\src\pages\dashboard\GallerySettingsPage.jsx
import { useEffect, useRef, useState } from "react";
import { useOutletContext } from "react-router-dom";
import { galleriesApi } from "../../api/galleriesApi";
import { photosApi } from "../../api/photosApi";
import { useToast } from "../../components/ui/Toast";
import { useSubscription } from "../../hooks/useSubscription";
import UpgradePrompt from "../../components/shared/UpgradePrompt";
import { toDateInputValue } from "../../utils/formatters";
import WatermarkSettings from "../../components/shared/WatermarkSettings";

const USE_MOCK_DATA = import.meta.env.VITE_USE_MOCK_DATA === "true";

// The three real derivative tiers the processing pipeline generates
// (apps/core/utils.py::_DISPLAY_TIERS on the backend) -- these are the
// honest numbers for this app, not Pixieset's 2048/1024/640 labels.
const WEB_SIZE_OPTIONS = [
  { value: 2048, label: "2048px", hint: "Full web resolution" },
  { value: 1280, label: "1280px", hint: "Medium" },
  { value: 640, label: "640px", hint: "Small" },
];

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

function clampPositiveIntOrNull(raw) {
  const trimmed = String(raw ?? "").trim();
  if (!trimmed) return null;
  const n = parseInt(trimmed, 10);
  return Number.isFinite(n) && n > 0 ? n : null;
}

/** Small fading "Saved" / "Saving…" indicator for the autosaved Download tab. */
function SaveIndicator({ state }) {
  if (state === "idle") return null;
  return (
    <span
      className={`text-[11px] font-medium transition-opacity ${
        state === "error" ? "text-red-600" : "text-muted"
      }`}
    >
      {state === "saving" ? "Saving…" : state === "saved" ? "Saved" : "Couldn't save"}
    </span>
  );
}

export default function GallerySettingsPage() {
  const { gallery, setGallery, slug, navigate, isMountedRef } = useOutletContext();
  const toast = useToast();
  const { entitlements, loading: planLoading } = useSubscription();
  const originalLocked = !planLoading && !entitlements.original_download;

  const [activeTab, setActiveTab] = useState("general");

  const [title, setTitle] = useState(gallery.title);
  const [brandingColor, setBrandingColor] = useState(gallery.branding_color);
  const [eventDate, setEventDate] = useState(toDateInputValue(gallery.event_date));
  const [expiresAt, setExpiresAt] = useState(toDateInputValue(gallery.expires_at));
  const [hasPassword, setHasPassword] = useState(gallery.has_password);
  const passwordInputRef = useRef(null);
  const [password, setPassword] = useState("");
  const [updating, setUpdating] = useState(false);
  const [errorMsg, setErrorMsg] = useState("");

  // ── Privacy tab: Download PIN -- the ONLY other gate secret, independent
  // of the gallery password above. Never shown in plaintext; the server
  // never returns it, only has_download_pin. ──────────────────────────────
  const [hasDownloadPin, setHasDownloadPin] = useState(gallery.has_download_pin ?? false);
  const [pinEditing, setPinEditing] = useState(false);
  const [downloadPin, setDownloadPin] = useState("");
  const [pinUpdating, setPinUpdating] = useState(false);
  const [pinError, setPinError] = useState("");

  // "Limit PIN usage" (Privacy tab, Advanced) -- a non-secret cap, so it
  // autosaves like the Download tab's own limits.
  const initialPrivacy = gallery.design_settings?.privacy || {};
  const [pinLimit, setPinLimit] = useState(
    initialPrivacy.pin_limit != null ? String(initialPrivacy.pin_limit) : "",
  );
  const [pinLimitSaveState, setPinLimitSaveState] = useState("idle");
  const pinLimitTimerRef = useRef(null);
  const pinLimitSkipRef = useRef(true);

  // ── Download tab ─────────────────────────────────────────────────────
  const initialDownloads = gallery.design_settings?.downloads || {};
  const legacySizes = Array.isArray(initialDownloads.allowed_sizes) ? initialDownloads.allowed_sizes : null;

  const [isDownloadable, setIsDownloadable] = useState(
    gallery.is_downloadable ?? gallery.allow_download ?? false,
  );
  const [downloadSubTab, setDownloadSubTab] = useState("general"); // general | advanced

  const [highResEnabled, setHighResEnabled] = useState(
    initialDownloads.high_res?.enabled ?? (legacySizes ? legacySizes.includes("download") : true),
  );
  const [highResMode, setHighResMode] = useState(initialDownloads.high_res?.mode || "3600");
  const [webEnabled, setWebEnabled] = useState(
    initialDownloads.web?.enabled ?? (legacySizes ? legacySizes.includes("web") : true),
  );
  const [webPx, setWebPx] = useState(initialDownloads.web?.px || 2048);
  const [requireDownloadEmail, setRequireDownloadEmail] = useState(
    initialDownloads.require_email !== false,
  );

  const [sets, setSets] = useState([]);
  const [setsEnabled, setSetsEnabled] = useState(
    Array.isArray(initialDownloads.sets_enabled) ? initialDownloads.sets_enabled : null,
  );

  const [limitTotal, setLimitTotal] = useState(
    initialDownloads.limit_total != null ? String(initialDownloads.limit_total) : "",
  );
  const [restrictContacts, setRestrictContacts] = useState(Boolean(initialDownloads.restrict_contacts));
  const [allowedEmails, setAllowedEmails] = useState(
    Array.isArray(initialDownloads.allowed_emails) ? initialDownloads.allowed_emails : [],
  );
  const [newEmail, setNewEmail] = useState("");
  const [emailError, setEmailError] = useState("");

  const [downloadSaveState, setDownloadSaveState] = useState("idle"); // idle | saving | saved | error
  const [downloadSaveError, setDownloadSaveError] = useState("");
  const downloadTimerRef = useRef(null);
  const downloadSkipRef = useRef(true);

  useEffect(() => {
    let cancelled = false;
    photosApi.listSets(slug).then((data) => {
      if (!cancelled) setSets(Array.isArray(data) ? data : data?.results || []);
    }).catch(() => {});
    return () => { cancelled = true; };
  }, [slug]);

  // Locked product decision: the MVP gallery URL is /g/:username/:slug —
  // stable, server-assigned, not photographer-editable (there is no
  // custom-URL/vanity-slug feature; the slug is generated once from the
  // title at creation and never changes on a title edit, see
  // GalleryUpdateSerializer.update()). This tab shows it read-only.
  const ownerUsername = gallery.owner_username ?? gallery.photographer_username ?? "unknown";
  const canonicalPath = `/g/${ownerUsername}/${gallery.slug}`;
  const canonicalUrl = typeof window !== "undefined" ? `${window.location.origin}${canonicalPath}` : canonicalPath;

  const tabs = [
    { id: "general", label: "General" },
    { id: "privacy", label: "Privacy" },
    { id: "download", label: "Download" },
    { id: "watermark", label: "Watermark" },
  ];

  const handleSaveSettings = async (e) => {
    e.preventDefault();
    if (!title.trim() || updating) return;
    setUpdating(true);
    setErrorMsg("");

    const payload = {
      title: title.trim(),
      branding_color: brandingColor,
      event_date: eventDate || null,
      expires_at: expiresAt || null,
    };

    try {
      let updated;
      if (USE_MOCK_DATA) {
        updated = { ...gallery, ...payload };
      } else {
        updated = await galleriesApi.updateGallery(slug, payload);
      }
      setGallery(updated);
      setTitle(updated.title);
      setBrandingColor(updated.branding_color);
      toast("Settings saved successfully", "success");
    } catch (err) {
      if (isMountedRef.current) {
        setErrorMsg(err.response?.data?.detail || err.response?.data?.error || "Failed to save settings.");
        toast("Failed to save settings", "error");
      }
    } finally {
      if (isMountedRef.current) setUpdating(false);
    }
  };

  // ── Download tab: one consistent autosave pattern. Every toggle/radio/
  // checkbox/number field below lands here, debounced, with a small
  // "Saved" indicator -- no more separate Save/Set buttons on this tab. ──
  const saveDownloadSettings = async () => {
    setDownloadSaveState("saving");
    setDownloadSaveError("");
    const payload = {
      is_downloadable: isDownloadable,
      design_settings: {
        ...(gallery.design_settings || {}),
        downloads: {
          require_email: requireDownloadEmail,
          high_res: { enabled: highResEnabled, mode: highResMode },
          web: { enabled: webEnabled, px: webPx },
          sets_enabled: setsEnabled,
          limit_total: clampPositiveIntOrNull(limitTotal),
          restrict_contacts: restrictContacts,
          allowed_emails: allowedEmails,
        },
      },
    };
    try {
      const updated = USE_MOCK_DATA ? { ...gallery, ...payload } : await galleriesApi.updateGallery(slug, payload);
      if (!isMountedRef.current) return;
      setGallery(updated);
      setDownloadSaveState("saved");
      window.clearTimeout(saveDownloadSettings._fadeTimer);
      saveDownloadSettings._fadeTimer = window.setTimeout(() => {
        if (isMountedRef.current) setDownloadSaveState((s) => (s === "saved" ? "idle" : s));
      }, 2000);
    } catch (err) {
      if (!isMountedRef.current) return;
      const data = err.response?.data;
      setDownloadSaveState("error");
      setDownloadSaveError(data?.error || "Failed to save download settings.");
      toast(data?.error || "Failed to save download settings", "error");
    }
  };

  useEffect(() => {
    if (downloadSkipRef.current) { downloadSkipRef.current = false; return; }
    if (!highResEnabled && !webEnabled) return; // invalid -- wait for the user to fix it
    if (downloadTimerRef.current) window.clearTimeout(downloadTimerRef.current);
    downloadTimerRef.current = window.setTimeout(saveDownloadSettings, 700);
    return () => window.clearTimeout(downloadTimerRef.current);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [
    isDownloadable, highResEnabled, highResMode, webEnabled, webPx, requireDownloadEmail,
    setsEnabled, limitTotal, restrictContacts, allowedEmails,
  ]);

  // ── Privacy tab: "Limit PIN usage" autosave (non-secret). ───────────────
  const savePinLimit = async () => {
    setPinLimitSaveState("saving");
    const payload = {
      design_settings: {
        ...(gallery.design_settings || {}),
        privacy: { ...(gallery.design_settings?.privacy || {}), pin_limit: clampPositiveIntOrNull(pinLimit) },
      },
    };
    try {
      const updated = USE_MOCK_DATA ? { ...gallery, ...payload } : await galleriesApi.updateGallery(slug, payload);
      if (!isMountedRef.current) return;
      setGallery(updated);
      setPinLimitSaveState("saved");
      window.setTimeout(() => { if (isMountedRef.current) setPinLimitSaveState((s) => (s === "saved" ? "idle" : s)); }, 2000);
    } catch {
      if (isMountedRef.current) setPinLimitSaveState("error");
    }
  };

  useEffect(() => {
    if (pinLimitSkipRef.current) { pinLimitSkipRef.current = false; return; }
    if (pinLimitTimerRef.current) window.clearTimeout(pinLimitTimerRef.current);
    pinLimitTimerRef.current = window.setTimeout(savePinLimit, 700);
    return () => window.clearTimeout(pinLimitTimerRef.current);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pinLimit]);

  const handleSaveDownloadPin = async (nextPin) => {
    if (pinUpdating) return;
    if (!nextPin && hasDownloadPin) {
      if (!window.confirm("Remove the download PIN? Downloads will no longer require one.")) return;
    }
    setPinUpdating(true);
    setPinError("");
    try {
      let response;
      if (USE_MOCK_DATA) {
        response = { has_download_pin: Boolean(nextPin) };
      } else {
        response = await galleriesApi.setDownloadPin(slug, nextPin || null);
      }
      if (!isMountedRef.current) return;
      setHasDownloadPin(response.has_download_pin);
      setGallery((prev) => ({ ...prev, has_download_pin: response.has_download_pin }));
      setDownloadPin("");
      setPinEditing(false);
      toast(nextPin ? "Download PIN set" : "Download PIN removed", "success");
    } catch (err) {
      if (isMountedRef.current) {
        setPinError(err.response?.data?.error || "Failed to update download PIN.");
        toast("Failed to update download PIN", "error");
      }
    } finally {
      if (isMountedRef.current) setPinUpdating(false);
    }
  };

  const handleSavePassword = async (e) => {
    e.preventDefault();
    if (updating) return;
    if (!password && !hasPassword) {
      setErrorMsg("Enter a password before enabling password protection.");
      passwordInputRef.current?.focus();
      return;
    }
    if (!password && hasPassword) {
      if (!window.confirm("Remove password protection?")) return;
    }
    setUpdating(true);
    try {
      if (USE_MOCK_DATA) {
        const newHasPassword = Boolean(password);
        setHasPassword(newHasPassword);
        setGallery((prev) => ({
          ...prev,
          has_password: newHasPassword,
          is_password_protected: newHasPassword,
        }));
        setPassword("");
        toast(password ? "Password set" : "Password removed", "success");
      } else {
        const response = await galleriesApi.setGalleryPassword(slug, password || null);
        setHasPassword(response.has_password);
        setGallery((prev) => ({
          ...prev,
          has_password: response.has_password,
          is_password_protected: response.is_password_protected,
        }));
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

  const toggleSet = (setId) => {
    setSetsEnabled((current) => {
      const allIds = sets.map((s) => s.id);
      const activeIds = current === null ? allIds : current;
      const isOn = activeIds.includes(setId);
      const next = isOn ? activeIds.filter((id) => id !== setId) : [...activeIds, setId];
      return next.length === allIds.length ? null : next;
    });
  };
  const isSetEnabled = (setId) => setsEnabled === null || setsEnabled.includes(setId);

  const addAllowedEmail = () => {
    const email = newEmail.trim().toLowerCase();
    if (!email) return;
    if (!EMAIL_RE.test(email)) { setEmailError("Enter a valid email address."); return; }
    setEmailError("");
    if (!allowedEmails.includes(email)) setAllowedEmails((prev) => [...prev, email]);
    setNewEmail("");
  };
  const removeAllowedEmail = (email) => setAllowedEmails((prev) => prev.filter((e) => e !== email));

  const noSizeSelected = !highResEnabled && !webEnabled;

  return (
    <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
      <div className="lg:col-span-2 space-y-6">
        {/* Tab bar */}
        <div className="flex gap-1 bg-cream-100 rounded-xl p-1 overflow-x-auto">
          {tabs.map((tab) => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`flex-none px-4 py-2.5 text-xs font-medium rounded-lg transition-all cursor-pointer ${
                activeTab === tab.id
                  ? "bg-surface-light text-ink shadow-sm"
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
          <div className="bg-surface-light rounded-2xl border border-cream-200 shadow-card p-6">
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
                  className="w-full px-3 py-2 text-sm rounded-lg border border-cream-200 focus:border-brand-green-500 focus:outline-none focus:ring-2 focus:ring-brand-green-500/10 transition-all disabled:opacity-50"
                  required
                />
              </div>

              <div className="p-4 bg-cream-100 rounded-xl border border-cream-200 text-xs">
                <span className="font-semibold text-muted uppercase tracking-wider block text-[10px]">Gallery Link</span>
                <p className="mt-2 text-ink font-mono break-all">{canonicalUrl}</p>
                <p className="mt-1.5 text-muted">
                  This link stays the same even if you change the title above.
                </p>
              </div>

              <div className="flex flex-col gap-1">
                <label className="text-xs font-semibold text-ink/80" htmlFor="gallery-event-date">Event Date</label>
                <input
                  id="gallery-event-date"
                  type="date"
                  value={eventDate}
                  onChange={(e) => setEventDate(e.target.value)}
                  disabled={updating}
                  className="w-full px-3 py-2 text-sm rounded-lg border border-cream-200 focus:border-brand-green-500 focus:outline-none focus:ring-2 focus:ring-brand-green-500/10 transition-all disabled:opacity-50"
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
                  className="w-full px-3 py-2 text-sm rounded-lg border border-cream-200 focus:border-brand-green-500 focus:outline-none focus:ring-2 focus:ring-brand-green-500/10 transition-all disabled:opacity-50"
                />
                <span className="text-[11px] text-muted">After this date, clients lose access.</span>
              </div>

              <div className="flex justify-end pt-4 border-t border-cream-200">
                <button
                  type="submit"
                  disabled={updating || !title.trim()}
                  className="px-4 py-2 bg-brand-green-600 text-white text-sm font-medium rounded-lg hover:bg-brand-green-700 transition-colors cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  {updating ? "Saving..." : "Save Settings"}
                </button>
              </div>
            </form>
          </div>
        )}

        {/* Watermark Tab — owns its own save, plan gating and background re-apply */}
        {activeTab === "watermark" && (
          <WatermarkSettings
            gallery={gallery}
            setGallery={setGallery}
            slug={slug}
            isMountedRef={isMountedRef}
          />
        )}

        {/* Privacy Tab — the ONLY place gate secrets live: gallery password
            and download PIN, plus the non-secret "Limit PIN usage" cap. */}
        {activeTab === "privacy" && (
          <div className="bg-surface-light rounded-2xl border border-cream-200 shadow-card p-6">
            <h2 className="font-serif text-lg text-ink mb-2">Privacy & Security</h2>
            <p className="text-xs text-muted mb-6">
              Nothing is asked when a visitor opens this gallery unless you turn on a password or PIN below.
            </p>

            <div className="space-y-5">
              <div className="flex items-center justify-between p-4 bg-cream-100 rounded-xl border border-cream-200">
                <div>
                  <p className="text-sm font-medium text-ink">Gallery Password</p>
                  <p className="text-xs text-muted mt-0.5">Require a password just to view the gallery</p>
                </div>
                <label className="toggle-wrap">
                  <input
                    type="checkbox"
                    checked={hasPassword}
                    disabled={updating}
                    onChange={(e) => {
                      if (e.target.checked) {
                        // The server intentionally refuses an enabled state
                        // without a password. Move the user to the real
                        // action rather than showing a false-on toggle.
                        setErrorMsg("Enter a password below, then select Set to enable protection.");
                        passwordInputRef.current?.focus();
                      } else {
                        handleSavePassword({ preventDefault: () => {} });
                      }
                    }}
                  />
                  <span className="toggle-slider" />
                </label>
              </div>

              <form onSubmit={handleSavePassword} className="flex gap-3">
                <input
                  ref={passwordInputRef}
                  type="password"
                  placeholder={hasPassword ? "Enter new password" : "Set a password"}
                  value={password}
                  onChange={(e) => {
                    setPassword(e.target.value);
                    setErrorMsg("");
                  }}
                  disabled={updating}
                  className="flex-1 px-3 py-2 text-sm rounded-lg border border-cream-200 focus:border-brand-green-500 focus:outline-none focus:ring-2 focus:ring-brand-green-500/10 transition-all disabled:opacity-50"
                />
                <button
                  type="submit"
                  disabled={updating}
                  className="px-4 py-2 border border-cream-200 text-ink text-sm font-medium rounded-lg hover:bg-cream-100 transition-colors cursor-pointer disabled:opacity-50"
                >
                  {password ? "Save" : hasPassword ? "Clear" : "Set"}
                </button>
              </form>

              {/* Download PIN — a second, independent gate from the gallery
                  password above. The photographer always types their own
                  PIN; there is no auto-generated default and no reset button. */}
              <div className="pt-5 border-t border-cream-200">
                <div className="flex items-center justify-between mb-3">
                  <div>
                    <p className="text-sm font-medium text-ink">Download PIN</p>
                    <p className="text-xs text-muted mt-0.5">
                      Require a 4–8 digit PIN before a visitor can download anything — view access stays open.
                    </p>
                  </div>
                  <span
                    className={`inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-medium border ${
                      hasDownloadPin
                        ? "bg-brand-green-50 text-brand-green-700 border-brand-green-200"
                        : "bg-cream-200 text-muted border-cream-300"
                    }`}
                  >
                    {hasDownloadPin ? "Enabled" : "Off"}
                  </span>
                </div>

                {pinError && <p className="text-xs text-red-600 mb-2">{pinError}</p>}

                {!pinEditing ? (
                  <div className="flex items-center gap-3 p-4 bg-cream-100 rounded-xl border border-cream-200">
                    <span className="flex-1 font-mono text-sm text-ink tracking-[0.3em]">
                      {hasDownloadPin ? "••••" : "No PIN set"}
                    </span>
                    <button
                      type="button"
                      onClick={() => { setPinEditing(true); setDownloadPin(""); }}
                      className="px-3 py-1.5 border border-cream-200 bg-white text-ink text-xs font-medium rounded-lg hover:bg-cream-50 transition-colors cursor-pointer"
                    >
                      {hasDownloadPin ? "Change PIN" : "Set PIN"}
                    </button>
                    {hasDownloadPin && (
                      <button
                        type="button"
                        disabled={pinUpdating}
                        onClick={() => handleSaveDownloadPin("")}
                        className="px-3 py-1.5 border border-red-200 text-red-600 text-xs font-medium rounded-lg hover:bg-red-50 transition-colors cursor-pointer disabled:opacity-50"
                      >
                        Remove PIN
                      </button>
                    )}
                  </div>
                ) : (
                  <form
                    onSubmit={(e) => { e.preventDefault(); if (downloadPin) handleSaveDownloadPin(downloadPin); }}
                    className="flex gap-3"
                  >
                    <input
                      type="text"
                      autoFocus
                      inputMode="numeric"
                      pattern="[0-9]*"
                      maxLength={8}
                      placeholder="4–8 digits"
                      value={downloadPin}
                      onChange={(e) => setDownloadPin(e.target.value.replace(/\D/g, ""))}
                      disabled={pinUpdating}
                      className="flex-1 px-3 py-2 text-sm rounded-lg border border-cream-200 focus:border-brand-green-500 focus:outline-none focus:ring-2 focus:ring-brand-green-500/10 transition-all disabled:opacity-50"
                    />
                    <button
                      type="submit"
                      disabled={pinUpdating || downloadPin.length < 4}
                      className="px-4 py-2 bg-brand-green-600 text-white text-sm font-medium rounded-lg hover:bg-brand-green-700 transition-colors cursor-pointer disabled:opacity-50"
                    >
                      Save
                    </button>
                    <button
                      type="button"
                      onClick={() => { setPinEditing(false); setDownloadPin(""); setPinError(""); }}
                      className="px-4 py-2 border border-cream-200 text-ink text-sm font-medium rounded-lg hover:bg-cream-100 transition-colors cursor-pointer"
                    >
                      Cancel
                    </button>
                  </form>
                )}

                {hasDownloadPin && (
                  <div className="mt-4 flex items-center justify-between gap-3 p-4 bg-cream-100 rounded-xl border border-cream-200">
                    <div>
                      <p className="text-sm font-medium text-ink">Limit PIN usage</p>
                      <p className="text-xs text-muted mt-0.5">Block downloads once the PIN has been used this many times.</p>
                    </div>
                    <div className="flex items-center gap-2">
                      <input
                        type="number"
                        min={1}
                        placeholder="Unlimited"
                        value={pinLimit}
                        onChange={(e) => setPinLimit(e.target.value)}
                        className="w-24 px-3 py-1.5 text-sm rounded-lg border border-cream-200 focus:border-brand-green-500 focus:outline-none text-right"
                      />
                      <SaveIndicator state={pinLimitSaveState} />
                    </div>
                  </div>
                )}
              </div>
            </div>
          </div>
        )}

        {/* Download Tab — Pixieset-style General / Advanced, one autosave
            pattern throughout. */}
        {activeTab === "download" && (
          <div className="bg-surface-light rounded-2xl border border-cream-200 shadow-card p-6">
            <div className="flex items-start justify-between gap-4 mb-2">
              <div>
                <h2 className="font-serif text-lg text-ink">Download Settings</h2>
                <p className="text-xs text-muted mt-1">Control how clients download photos.</p>
              </div>
              <div className="flex items-center gap-3 flex-none">
                <SaveIndicator state={downloadSaveState} />
                <button
                  type="button"
                  onClick={() => navigate(`/dashboard/galleries/${slug}/activities`)}
                  className="text-xs font-medium text-brand-green-700 hover:text-brand-green-800 underline-offset-2 hover:underline cursor-pointer whitespace-nowrap"
                >
                  Download Activity →
                </button>
              </div>
            </div>
            {downloadSaveState === "error" && (
              <p className="text-xs text-red-600 mb-4">{downloadSaveError}</p>
            )}

            <div className="flex gap-1 bg-cream-100 rounded-lg p-1 mb-6 w-fit">
              {[{ id: "general", label: "General" }, { id: "advanced", label: "Advanced" }].map((t) => (
                <button
                  key={t.id}
                  type="button"
                  onClick={() => setDownloadSubTab(t.id)}
                  className={`px-4 py-1.5 text-xs font-medium rounded-md transition-all cursor-pointer ${
                    downloadSubTab === t.id ? "bg-surface-light text-ink shadow-sm" : "text-muted hover:text-ink"
                  }`}
                >
                  {t.label}
                </button>
              ))}
            </div>

            {downloadSubTab === "general" && (
              <div className="space-y-4">
                <div className="flex items-center justify-between p-4 bg-cream-100 rounded-xl border border-cream-200">
                  <div>
                    <p className="text-sm font-medium text-ink">Photo Download</p>
                    <p className="text-xs text-muted mt-0.5">Let clients download photos from this gallery</p>
                  </div>
                  <label className="toggle-wrap">
                    <input type="checkbox" checked={isDownloadable} onChange={(e) => setIsDownloadable(e.target.checked)} />
                    <span className="toggle-slider" />
                  </label>
                </div>

                <fieldset disabled={!isDownloadable} className="rounded-xl border border-cream-200 p-4 space-y-4 disabled:opacity-60">
                  <legend className="px-1 text-sm font-medium text-ink">Photo Download Sizes</legend>

                  <div className="space-y-2">
                    <label className="flex cursor-pointer items-center gap-3 text-sm text-ink">
                      <input
                        type="checkbox"
                        checked={highResEnabled}
                        onChange={(e) => setHighResEnabled(e.target.checked)}
                        className="accent-brand-green-600"
                      />
                      <span className="font-medium">High Resolution</span>
                    </label>
                    {highResEnabled && (
                      <div className="ml-7 space-y-2">
                        <label className="flex items-center gap-2 text-sm text-ink">
                          <input
                            type="radio"
                            name="high-res-mode"
                            checked={highResMode === "3600"}
                            onChange={() => setHighResMode("3600")}
                            className="accent-brand-green-600"
                          />
                          3600px (Download Master)
                        </label>
                        <label
                          className={`flex items-center gap-2 text-sm ${originalLocked ? "text-muted cursor-not-allowed" : "text-ink cursor-pointer"}`}
                        >
                          <input
                            type="radio"
                            name="high-res-mode"
                            checked={highResMode === "original"}
                            disabled={originalLocked}
                            onChange={() => setHighResMode("original")}
                            className="accent-brand-green-600 disabled:cursor-not-allowed"
                          />
                          Original{originalLocked ? " — Upgrade required" : ""}
                        </label>
                        {originalLocked && (
                          <UpgradePrompt
                            className="mt-2"
                            title="Original downloads are a Pro feature"
                            message="Offer clients the untouched, full-resolution original with the Pro plan or above."
                          />
                        )}
                      </div>
                    )}
                  </div>

                  <div className="space-y-2 pt-2 border-t border-cream-200">
                    <label className="flex cursor-pointer items-center gap-3 text-sm text-ink">
                      <input
                        type="checkbox"
                        checked={webEnabled}
                        onChange={(e) => setWebEnabled(e.target.checked)}
                        className="accent-brand-green-600"
                      />
                      <span className="font-medium">Web Size</span>
                    </label>
                    {webEnabled && (
                      <div className="ml-7 flex flex-wrap gap-4">
                        {WEB_SIZE_OPTIONS.map((opt) => (
                          <label key={opt.value} className="flex items-center gap-2 text-sm text-ink cursor-pointer">
                            <input
                              type="radio"
                              name="web-px"
                              checked={webPx === opt.value}
                              onChange={() => setWebPx(opt.value)}
                              className="accent-brand-green-600"
                            />
                            {opt.label}
                          </label>
                        ))}
                      </div>
                    )}
                  </div>

                  {noSizeSelected && <p className="text-xs text-red-600">Choose at least one download size.</p>}
                </fieldset>

                <label className="flex cursor-pointer items-center justify-between rounded-xl border border-cream-200 p-4">
                  <span>
                    <span className="block text-sm font-medium text-ink">Require email</span>
                    <span className="block text-xs text-muted mt-0.5">Record the downloader's email before any download.</span>
                  </span>
                  <input
                    type="checkbox"
                    checked={requireDownloadEmail}
                    disabled={!isDownloadable}
                    onChange={(e) => setRequireDownloadEmail(e.target.checked)}
                    className="h-4 w-4 accent-brand-green-600 disabled:cursor-not-allowed"
                  />
                </label>
                {!requireDownloadEmail && !hasDownloadPin && isDownloadable && (
                  <p className="text-xs text-amber-700">Frictionless downloads are on: clients will not be asked for email or a PIN.</p>
                )}

                <fieldset disabled={!isDownloadable} className="rounded-xl border border-cream-200 p-4 space-y-2 disabled:opacity-60">
                  <legend className="px-1 text-sm font-medium text-ink">Photo Sets Available for Download</legend>
                  <p className="text-xs text-muted -mt-1 mb-2">Leave every set checked to allow the whole gallery to be downloaded.</p>
                  {sets.length === 0 ? (
                    <p className="text-xs text-muted">This gallery has no photo sets yet.</p>
                  ) : (
                    sets.map((set) => (
                      <label key={set.id} className="flex cursor-pointer items-center gap-3 text-sm text-ink">
                        <input
                          type="checkbox"
                          checked={isSetEnabled(set.id)}
                          onChange={() => toggleSet(set.id)}
                          className="accent-brand-green-600"
                        />
                        {set.name}
                        <span className="text-xs text-muted">({set.photo_count ?? 0})</span>
                      </label>
                    ))
                  )}
                </fieldset>
              </div>
            )}

            {downloadSubTab === "advanced" && (
              <div className="space-y-4">
                <div className="flex items-center justify-between gap-3 p-4 bg-cream-100 rounded-xl border border-cream-200">
                  <div>
                    <p className="text-sm font-medium text-ink">Limit Photo Downloads</p>
                    <p className="text-xs text-muted mt-0.5">Stop all downloads once this many have been completed, in total.</p>
                  </div>
                  <input
                    type="number"
                    min={1}
                    placeholder="Unlimited"
                    value={limitTotal}
                    onChange={(e) => setLimitTotal(e.target.value)}
                    className="w-28 px-3 py-1.5 text-sm rounded-lg border border-cream-200 focus:border-brand-green-500 focus:outline-none text-right"
                  />
                </div>

                <div className="rounded-xl border border-cream-200 p-4 space-y-3">
                  <label className="flex cursor-pointer items-center justify-between">
                    <span>
                      <span className="block text-sm font-medium text-ink">Restrict Downloads to Specific Contacts</span>
                      <span className="block text-xs text-muted mt-0.5">Only the email addresses below may download.</span>
                    </span>
                    <input
                      type="checkbox"
                      checked={restrictContacts}
                      onChange={(e) => setRestrictContacts(e.target.checked)}
                      className="h-4 w-4 accent-brand-green-600"
                    />
                  </label>

                  {restrictContacts && (
                    <div className="space-y-2 pt-2 border-t border-cream-200">
                      <div className="flex gap-2">
                        <input
                          type="email"
                          placeholder="client@example.com"
                          value={newEmail}
                          onChange={(e) => { setNewEmail(e.target.value); setEmailError(""); }}
                          onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); addAllowedEmail(); } }}
                          className="flex-1 px-3 py-2 text-sm rounded-lg border border-cream-200 focus:border-brand-green-500 focus:outline-none"
                        />
                        <button
                          type="button"
                          onClick={addAllowedEmail}
                          className="px-3 py-2 border border-cream-200 text-ink text-sm font-medium rounded-lg hover:bg-cream-100 transition-colors cursor-pointer"
                        >
                          Add
                        </button>
                      </div>
                      {emailError && <p className="text-xs text-red-600">{emailError}</p>}
                      {allowedEmails.length === 0 ? (
                        <p className="text-xs text-amber-700">Add at least one email address to restrict downloads to.</p>
                      ) : (
                        <ul className="space-y-1.5">
                          {allowedEmails.map((email) => (
                            <li key={email} className="flex items-center justify-between px-3 py-1.5 bg-cream-100 rounded-lg text-sm text-ink">
                              {email}
                              <button
                                type="button"
                                onClick={() => removeAllowedEmail(email)}
                                className="text-xs text-red-600 hover:text-red-700 cursor-pointer"
                              >
                                Remove
                              </button>
                            </li>
                          ))}
                        </ul>
                      )}
                    </div>
                  )}
                </div>
              </div>
            )}
          </div>
        )}
      </div>

      {/* Right sidebar — preview */}
      <div className="space-y-8">
        <div className="bg-surface-light rounded-2xl border border-cream-200 shadow-card overflow-hidden p-6 flex flex-col items-center justify-center text-center py-10 min-h-[300px]">
          {gallery.cover_url ? (
            <img src={gallery.cover_url} alt="" className="w-24 h-24 rounded-full object-cover border border-cream-200 mb-4 shadow-sm" />
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
            gallery.is_published ? "bg-brand-green-50 text-brand-green-700 border-brand-green-200" : "bg-amber-50 text-amber-700 border-amber-200"
          }`}>
            {gallery.is_published ? "Published" : "Draft"}
          </span>
        </div>
      </div>
    </div>
  );
}
