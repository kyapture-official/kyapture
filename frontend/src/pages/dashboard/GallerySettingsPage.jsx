// C:\Users\David\Desktop\kyapture\frontend\src\pages\dashboard\GallerySettingsPage.jsx
import { useEffect, useRef, useState } from "react";
import { Link, useOutletContext } from "react-router-dom";
import { galleriesApi } from "../../api/galleriesApi";
import { photosApi } from "../../api/photosApi";
import { useToast } from "../../components/ui/Toast";
import { useSubscription } from "../../hooks/useSubscription";
import { toDateInputValue } from "../../utils/formatters";
import WatermarkSettings from "../../components/shared/WatermarkSettings";

const USE_MOCK_DATA = import.meta.env.VITE_USE_MOCK_DATA === "true";

// Web Size choices. 1280 was this setting's value before 1R.6-B; the server
// still reads it as 1024, so a gallery saved earlier loads with 1024 selected.
const WEB_SIZE_OPTIONS = [
  { value: 2048, label: "2048px" },
  { value: 1024, label: "1024px" },
  { value: 640, label: "640px" },
];
const normalizeWebPx = (px) => (px === 1280 ? 1024 : px);

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
const PASSWORD_MIN_LENGTH = 4; // mirrors GallerySetPasswordView

/** Small fading "Saved" / "Saving…" indicator for the autosaved Download tab. */
function SaveIndicator({ state }) {
  if (state === "idle") return null;
  return (
    <span
      className={`text-[11px] font-medium transition-opacity ${
        state === "error" ? "text-red-600" : "text-muted"
      }`}
    >
      {state === "saving" ? "Saving…" : "Couldn't save"}
    </span>
  );
}

/**
 * Masked secret input with a show/hide eye. Commits on Enter and on blur
 * (no Save button); the eye keeps focus in the input so clicking it does not
 * count as a blur.
 */
function SecretField({ id, value, onChange, onCommit, label, invalid, ...inputProps }) {
  const [shown, setShown] = useState(false);
  return (
    <div
      className={`flex items-center rounded-lg border bg-white transition-all focus-within:ring-2 ${
        invalid
          ? "border-red-300 focus-within:border-red-400 focus-within:ring-red-200"
          : "border-cream-200 focus-within:border-brand-green-500 focus-within:ring-brand-green-500/10"
      }`}
    >
      <input
        id={id}
        type={shown ? "text" : "password"}
        autoComplete="new-password"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); onCommit(); } }}
        onBlur={onCommit}
        className="flex-1 min-w-0 bg-transparent px-3 py-2 text-sm text-ink focus:outline-none disabled:opacity-50"
        {...inputProps}
      />
      <button
        type="button"
        aria-label={shown ? `Hide ${label}` : `Show ${label}`}
        aria-pressed={shown}
        onMouseDown={(e) => e.preventDefault()}
        onClick={() => setShown((v) => !v)}
        className="px-3 py-2 text-muted hover:text-ink cursor-pointer"
      >
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
          <path d="M1 12s4-7 11-7 11 7 11 7-4 7-11 7S1 12 1 12Z" />
          <circle cx="12" cy="12" r="3" />
          {shown && <path d="M3 3l18 18" />}
        </svg>
      </button>
    </div>
  );
}

/** "On"/"Off" switch with its label beside it (Download > Advanced). */
function OnOffToggle({ label, checked, onChange, disabled }) {
  return (
    <label className="flex items-center gap-3 text-sm text-ink w-fit cursor-pointer">
      <span className="toggle-wrap">
        <input
          type="checkbox"
          aria-label={label}
          checked={checked}
          disabled={disabled}
          onChange={(e) => onChange(e.target.checked)}
        />
        <span className="toggle-slider" />
      </span>
      {checked ? "On" : "Off"}
    </label>
  );
}

const LIMIT_RE = /^[1-9]\d{0,6}$/;

/**
 * Whole-number field that commits on blur / Enter only -- never while the
 * photographer is still typing ("1" on the way to "100" must not be saved).
 * An empty field commits null (no limit); anything else that is not a whole
 * number >= 1 shows an inline message and leaves the saved value alone.
 */
function LimitField({ id, committed, onCommit, placeholder, suffix, disabled }) {
  const [draft, setDraft] = useState(committed != null ? String(committed) : "");
  const [error, setError] = useState("");
  useEffect(() => {
    setDraft(committed != null ? String(committed) : "");
    setError("");
  }, [committed]);

  const commit = () => {
    const text = draft.trim();
    if (text === "") { setError(""); onCommit(null); return; }
    if (!LIMIT_RE.test(text)) { setError("Enter a whole number of 1 or more."); return; }
    setError("");
    onCommit(Number(text));
  };

  return (
    <div className="space-y-1.5">
      <div
        className={`flex items-center w-full max-w-xs rounded-lg border bg-white transition-all focus-within:ring-2 ${
          error
            ? "border-red-300 focus-within:border-red-400 focus-within:ring-red-200"
            : "border-cream-200 focus-within:border-brand-green-500 focus-within:ring-brand-green-500/10"
        }`}
      >
        <input
          id={id}
          type="text"
          inputMode="numeric"
          autoComplete="off"
          maxLength={7}
          placeholder={placeholder}
          value={draft}
          disabled={disabled}
          onChange={(e) => { setDraft(e.target.value.replace(/\D/g, "")); setError(""); }}
          onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); commit(); } }}
          onBlur={commit}
          className="flex-1 min-w-0 bg-transparent px-3 py-2 text-sm text-ink focus:outline-none disabled:opacity-50"
        />
        <span className="pr-3 text-xs text-muted">{suffix}</span>
      </div>
      {error && <p role="alert" className="text-xs text-red-600">{error}</p>}
    </div>
  );
}

const MAX_CONTACTS = 500;
const CONTACT_SPLIT_RE = /[\s,;]+/;

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
  // ── Privacy tab: Collection Password only. The server never returns it,
  // only has_password. Empty = off. ────────────────────────────────────────
  const [hasPassword, setHasPassword] = useState(gallery.has_password);
  const [password, setPassword] = useState("");
  const [pwEditing, setPwEditing] = useState(false);
  const [pwSaving, setPwSaving] = useState(false);
  const [pwError, setPwError] = useState("");
  const pwCommitRef = useRef(false);
  const [updating, setUpdating] = useState(false);
  const [errorMsg, setErrorMsg] = useState("");

  // ── Download tab: Download PIN. Never shown in plaintext; the server
  // never returns it, only has_download_pin (a stored hash exists). The
  // toggle is separate from the hash: Off stops enforcement but keeps it. ──
  const initialDownloads = gallery.design_settings?.downloads || {};
  const [hasDownloadPin, setHasDownloadPin] = useState(gallery.has_download_pin ?? false);
  const [pinEnabled, setPinEnabled] = useState(
    (gallery.has_download_pin ?? false)
      ? initialDownloads.pin_enabled !== false
      : initialDownloads.pin_enabled === true,
  );
  const [pinEditing, setPinEditing] = useState(false);
  const [downloadPin, setDownloadPin] = useState("");
  const [pinUpdating, setPinUpdating] = useState(false);
  const [pinError, setPinError] = useState("");
  const pinCommitRef = useRef(false);

  // ── Download tab ─────────────────────────────────────────────────────
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
  const [webPx, setWebPx] = useState(normalizeWebPx(initialDownloads.web?.px) || 2048);
  const [requireDownloadEmail, setRequireDownloadEmail] = useState(
    initialDownloads.require_email !== false,
  );

  // Photo sets (Advanced). null = every set may be downloaded (the default).
  const [sets, setSets] = useState(null); // null while loading
  const [setsEnabled, setSetsEnabled] = useState(
    Array.isArray(initialDownloads.sets_enabled) ? initialDownloads.sets_enabled : null,
  );
  const [setsError, setSetsError] = useState("");

  // Limit Photo Downloads: `limitOn` is only the reveal state; nothing is
  // enforced until a whole number >= 1 is saved. Off = null.
  const [limitTotal, setLimitTotal] = useState(initialDownloads.limit_total ?? null);
  const [limitOn, setLimitOn] = useState(initialDownloads.limit_total != null);

  // Restrict Downloads to Specific Contacts. On with an empty list is a real,
  // saved state: the server then lets nobody download. Off clears the list.
  const [restrictContacts, setRestrictContacts] = useState(Boolean(initialDownloads.restrict_contacts));
  const [allowedEmails, setAllowedEmails] = useState(
    Array.isArray(initialDownloads.allowed_emails) ? initialDownloads.allowed_emails : [],
  );
  const [emailDraft, setEmailDraft] = useState("");
  const [emailError, setEmailError] = useState("");

  // Limit PIN usage (design_settings.privacy.pin_limit). Off = null.
  const [pinLimit, setPinLimit] = useState(gallery.design_settings?.privacy?.pin_limit ?? null);
  const [pinLimitOn, setPinLimitOn] = useState(gallery.design_settings?.privacy?.pin_limit != null);
  const pinUseCount = gallery.design_settings?.privacy?.pin_use_count ?? 0;

  const [downloadSaveState, setDownloadSaveState] = useState("idle"); // idle | saving | error
  const [downloadSaveError, setDownloadSaveError] = useState("");
  const downloadTimerRef = useRef(null);
  const savedDownloadsRef = useRef(null); // last values the server confirmed

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

  useEffect(() => {
    let cancelled = false;
    photosApi.listSets(slug).then((data) => {
      if (!cancelled) setSets(Array.isArray(data) ? data : data?.results || []);
    }).catch(() => { if (!cancelled) setSets([]); });
    return () => { cancelled = true; };
  }, [slug]);

  // ── Download tab: one consistent autosave pattern. Every toggle/radio/
  // checkbox/field below lands here (number fields only once committed on
  // blur/Enter), debounced, with a "Collection updated" toast -- no separate
  // Save/Set buttons. A failed save puts every control back to the last
  // value the server confirmed and says so inline. ──
  const downloadsSnapshot = () => ({
    isDownloadable, highResEnabled, highResMode: effectiveHighResMode, webEnabled, webPx,
    requireDownloadEmail, setsEnabled, limitTotal, restrictContacts, allowedEmails, pinEnabled, pinLimit,
  });

  const restoreDownloads = (s) => {
    setIsDownloadable(s.isDownloadable);
    setHighResEnabled(s.highResEnabled);
    setHighResMode(s.highResMode);
    setWebEnabled(s.webEnabled);
    setWebPx(s.webPx);
    setRequireDownloadEmail(s.requireDownloadEmail);
    setSetsEnabled(s.setsEnabled);
    setLimitTotal(s.limitTotal);
    setLimitOn(s.limitTotal != null);
    setRestrictContacts(s.restrictContacts);
    setAllowedEmails(s.allowedEmails);
    setPinEnabled(s.pinEnabled);
    setPinLimit(s.pinLimit);
    setPinLimitOn(s.pinLimit != null);
  };

  const saveDownloadSettings = async () => {
    const snapshot = downloadsSnapshot();
    setDownloadSaveState("saving");
    setDownloadSaveError("");
    const { coverPhoto: _coverPhoto, ...settingsWithoutCover } = gallery.design_settings || {};
    const payload = {
      is_downloadable: snapshot.isDownloadable,
      design_settings: {
        ...settingsWithoutCover,
        downloads: {
          require_email: snapshot.requireDownloadEmail,
          high_res: { enabled: snapshot.highResEnabled, mode: snapshot.highResMode },
          web: { enabled: snapshot.webEnabled, px: snapshot.webPx },
          sets_enabled: snapshot.setsEnabled,
          limit_total: snapshot.limitTotal,
          restrict_contacts: snapshot.restrictContacts,
          allowed_emails: snapshot.allowedEmails,
          pin_enabled: snapshot.pinEnabled,
        },
        privacy: { ...(gallery.design_settings?.privacy || {}), pin_limit: snapshot.pinLimit },
      },
    };
    try {
      const updated = USE_MOCK_DATA ? { ...gallery, ...payload } : await galleriesApi.updateGallery(slug, payload);
      if (!isMountedRef.current) return;
      savedDownloadsRef.current = snapshot;
      setGallery(updated);
      setDownloadSaveState("idle");
      toast("Collection updated", "success");
    } catch (err) {
      if (!isMountedRef.current) return;
      const data = err.response?.data;
      const detail = data?.error || data?.detail
        || (data && typeof data === "object" ? Object.values(data).flat().map(String).join(" ") : "");
      if (savedDownloadsRef.current) restoreDownloads(savedDownloadsRef.current);
      setDownloadSaveState("error");
      setDownloadSaveError(`Couldn't save, your previous setting was kept. ${detail}`.trim());
    }
  };

  const setsInvalid = Array.isArray(setsEnabled) && setsEnabled.length === 0;

  useEffect(() => {
    // The first run only records what the page loaded with.
    if (savedDownloadsRef.current === null) { savedDownloadsRef.current = downloadsSnapshot(); return undefined; }
    if (JSON.stringify(downloadsSnapshot()) === JSON.stringify(savedDownloadsRef.current)) return undefined;
    if (!highResEnabled && !webEnabled) return undefined; // invalid -- wait for the user to fix it
    if (setsInvalid) return undefined; // same: at least one set must stay on
    if (downloadTimerRef.current) window.clearTimeout(downloadTimerRef.current);
    downloadTimerRef.current = window.setTimeout(saveDownloadSettings, 700);
    return () => window.clearTimeout(downloadTimerRef.current);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [
    isDownloadable, highResEnabled, highResMode, webEnabled, webPx, requireDownloadEmail,
    setsEnabled, limitTotal, restrictContacts, allowedEmails, pinEnabled, pinLimit,
  ]);

  // ── Download PIN (Download tab). Typed by the photographer, hashed
  // server-side, never returned -- only has_download_pin. ──────────────────
  const commitDownloadPin = async () => {
    if (pinUpdating || pinCommitRef.current) return;
    if (!downloadPin) {
      if (pinEditing) { setPinEditing(false); setPinError(""); } // blur on an untouched Change
      return;
    }
    if (!/^\d{4,8}$/.test(downloadPin)) {
      setPinError("PIN must be 4 to 8 digits.");
      return;
    }
    pinCommitRef.current = true;
    setPinUpdating(true);
    setPinError("");
    try {
      const response = USE_MOCK_DATA
        ? { has_download_pin: true }
        : await galleriesApi.setDownloadPin(slug, downloadPin);
      if (!isMountedRef.current) return;
      setHasDownloadPin(response.has_download_pin);
      setGallery((prev) => ({ ...prev, has_download_pin: response.has_download_pin }));
      setDownloadPin("");
      setPinEditing(false);
      toast("Collection updated", "success");
    } catch (err) {
      if (isMountedRef.current) setPinError(err.response?.data?.error || "Failed to update download PIN.");
    } finally {
      pinCommitRef.current = false;
      if (isMountedRef.current) setPinUpdating(false);
    }
  };

  // ── Privacy tab: Collection Password. Autosaves on Enter/blur. ──────────
  const applyPasswordState = (response) => {
    setHasPassword(response.has_password);
    setGallery((prev) => ({
      ...prev,
      has_password: response.has_password,
      is_password_protected: response.is_password_protected,
    }));
    setPassword("");
    setPwEditing(false);
    toast("Collection updated", "success");
  };

  const commitPassword = async () => {
    if (pwSaving || pwCommitRef.current) return;
    const next = password.trim();
    if (!next) {
      if (pwEditing) { setPwEditing(false); setPwError(""); } // blur on an untouched Change
      return;
    }
    if (next.length < PASSWORD_MIN_LENGTH) {
      setPwError(`Password must be at least ${PASSWORD_MIN_LENGTH} characters.`);
      return;
    }
    pwCommitRef.current = true;
    setPwSaving(true);
    setPwError("");
    try {
      const response = USE_MOCK_DATA
        ? { has_password: true, is_password_protected: true }
        : await galleriesApi.setGalleryPassword(slug, next);
      if (isMountedRef.current) applyPasswordState(response);
    } catch (err) {
      if (isMountedRef.current) setPwError(err.response?.data?.error || "Failed to update password.");
    } finally {
      pwCommitRef.current = false;
      if (isMountedRef.current) setPwSaving(false);
    }
  };

  const handleRemovePassword = async () => {
    if (pwSaving) return;
    if (!window.confirm("Remove the collection password? Anyone with the link will be able to view the gallery.")) return;
    setPwSaving(true);
    setPwError("");
    try {
      const response = USE_MOCK_DATA
        ? { has_password: false, is_password_protected: false }
        : await galleriesApi.setGalleryPassword(slug, null);
      if (isMountedRef.current) applyPasswordState(response);
    } catch (err) {
      if (isMountedRef.current) setPwError(err.response?.data?.error || "Failed to remove password.");
    } finally {
      if (isMountedRef.current) setPwSaving(false);
    }
  };

  // ── Advanced: Restrict Downloads to Specific Contacts (email chips). ──────
  // Splits on commas/spaces/newlines, lowercases, de-duplicates. Invalid
  // entries are never added as chips; they stay in the box with a message.
  const addContacts = (raw) => {
    const parts = String(raw).split(CONTACT_SPLIT_RE).map((p) => p.trim().toLowerCase()).filter(Boolean);
    if (parts.length === 0) { setEmailDraft(""); setEmailError(""); return; }
    const invalid = [];
    const next = [...allowedEmails];
    let capped = false;
    for (const part of parts) {
      if (!EMAIL_RE.test(part) || part.length > 254) { invalid.push(part); continue; }
      if (next.includes(part)) continue;
      if (next.length >= MAX_CONTACTS) { capped = true; continue; }
      next.push(part);
    }
    if (next.length !== allowedEmails.length) setAllowedEmails(next);
    setEmailDraft(invalid.join(" "));
    if (capped) setEmailError(`You can add up to ${MAX_CONTACTS} contacts.`);
    else if (invalid.length === 1 && parts.length === 1) setEmailError("Enter a valid email address.");
    else if (invalid.length > 0) {
      const shown = invalid.slice(0, 3).join(", ") + (invalid.length > 3 ? ` and ${invalid.length - 3} more` : "");
      setEmailError(`Not added, not valid email addresses: ${shown}`);
    } else setEmailError("");
  };
  const removeAllowedEmail = (email) => setAllowedEmails((prev) => prev.filter((e) => e !== email));

  const toggleRestrictContacts = (on) => {
    setRestrictContacts(on);
    if (!on) { setAllowedEmails([]); setEmailDraft(""); setEmailError(""); }
  };

  const toggleLimitTotal = (on) => {
    setLimitOn(on);
    if (!on) setLimitTotal(null);
  };

  const togglePinLimit = (on) => {
    setPinLimitOn(on);
    if (!on) setPinLimit(null);
  };

  // ── Advanced: Photo Sets Available for Download. Checking every set is the
  // same as "no restriction" (null); at least one must stay checked. ───────
  const isSetEnabled = (setId) => setsEnabled === null || setsEnabled.includes(setId);
  const toggleSet = (setId) => {
    const allIds = sets.map((s) => s.id);
    const active = setsEnabled === null ? allIds : setsEnabled;
    const next = active.includes(setId) ? active.filter((id) => id !== setId) : [...active, setId];
    if (next.length === 0) {
      setSetsError("At least one set must stay available for download.");
      return;
    }
    setSetsError("");
    setSetsEnabled(next.length === allIds.length ? null : next);
  };

  const noSizeSelected = !highResEnabled && !webEnabled;
  // A Free (or lapsed) account never sees or saves "original": the server
  // would refuse it, and would serve the 3600px master anyway.
  const effectiveHighResMode = originalLocked && highResMode === "original" ? "3600" : highResMode;

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

        {/* Privacy Tab — Collection Password only (Pixieset "Collection
            Password"). Empty = off. The download PIN lives on the Download tab. */}
        {activeTab === "privacy" && (
          <div className="bg-surface-light rounded-2xl border border-cream-200 shadow-card p-6">
            <h2 className="font-serif text-lg text-ink mb-6">Privacy Settings</h2>

            <div className="space-y-2 max-w-xl">
              <label htmlFor="collection-password" className="block text-sm font-medium text-ink">
                Collection Password
              </label>
              {hasPassword && !pwEditing ? (
                <div className="flex items-center gap-2 px-3 py-2 rounded-lg border border-cream-200 bg-cream-50">
                  <span
                    id="collection-password"
                    aria-label="Password is set"
                    className="flex-1 text-sm text-ink tracking-[0.3em]"
                  >
                    ••••••••
                  </span>
                  <button
                    type="button"
                    disabled={pwSaving}
                    onClick={() => { setPwEditing(true); setPassword(""); setPwError(""); }}
                    className="px-2 py-1 text-xs font-medium text-brand-green-700 hover:underline underline-offset-2 cursor-pointer disabled:opacity-50"
                  >
                    Change
                  </button>
                  <button
                    type="button"
                    disabled={pwSaving}
                    onClick={handleRemovePassword}
                    className="px-2 py-1 text-xs font-medium text-red-600 hover:underline underline-offset-2 cursor-pointer disabled:opacity-50"
                  >
                    Remove
                  </button>
                </div>
              ) : (
                <SecretField
                  id="collection-password"
                  value={password}
                  onChange={(v) => { setPassword(v); setPwError(""); }}
                  onCommit={commitPassword}
                  placeholder="Add a password"
                  autoFocus={pwEditing}
                  disabled={pwSaving}
                  invalid={Boolean(pwError)}
                  label="password"
                />
              )}
              {pwError && <p role="alert" className="text-xs text-red-600">{pwError}</p>}
              <p className="text-xs text-muted">
                Require visitors to enter this password in order to see the collection.
              </p>
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
                <div className="space-y-2">
                  <p className="text-sm font-medium text-ink">Photo Download</p>
                  <label className="flex items-center gap-3 text-sm text-ink w-fit cursor-pointer">
                    <span className="toggle-wrap">
                      <input
                        type="checkbox"
                        aria-label="Photo Download"
                        checked={isDownloadable}
                        onChange={(e) => setIsDownloadable(e.target.checked)}
                      />
                      <span className="toggle-slider" />
                    </span>
                    {isDownloadable ? "On" : "Off"}
                  </label>
                  <p className="text-xs text-muted">Allow visitors to download photos in your gallery</p>
                </div>

                <div className={`pt-4 border-t border-cream-200 space-y-3 ${isDownloadable ? "" : "opacity-60"}`}>
                  <p className="text-sm font-medium text-ink">Photo Download Sizes</p>

                  <div className="flex flex-col sm:flex-row sm:items-center gap-x-6 gap-y-2">
                    <label className="flex items-center gap-3 text-sm text-ink sm:w-44 flex-none cursor-pointer">
                      <input
                        type="checkbox"
                        checked={highResEnabled}
                        disabled={!isDownloadable}
                        onChange={(e) => setHighResEnabled(e.target.checked)}
                        className="accent-brand-green-600"
                      />
                      High Resolution
                    </label>
                    <div className="flex flex-wrap items-center gap-x-5 gap-y-2 pl-7 sm:pl-0">
                      <span className="inline-flex items-center gap-2 text-sm">
                        <label className={`inline-flex items-center gap-2 ${originalLocked ? "text-muted cursor-not-allowed" : "text-ink cursor-pointer"}`}>
                          <input
                            type="radio"
                            name="high-res-mode"
                            checked={effectiveHighResMode === "original"}
                            disabled={!isDownloadable || !highResEnabled || originalLocked}
                            onChange={() => setHighResMode("original")}
                            className="accent-brand-green-600 disabled:cursor-not-allowed"
                          />
                          {originalLocked ? "Original — Upgrade required." : "Original"}
                        </label>
                        {originalLocked && (
                          <Link to="/dashboard/billing" className="text-brand-green-700 underline-offset-2 hover:underline">
                            Upgrade
                          </Link>
                        )}
                      </span>
                      <label className="inline-flex items-center gap-2 text-sm text-ink cursor-pointer">
                        <input
                          type="radio"
                          name="high-res-mode"
                          checked={effectiveHighResMode === "3600"}
                          disabled={!isDownloadable || !highResEnabled}
                          onChange={() => setHighResMode("3600")}
                          className="accent-brand-green-600"
                        />
                        3600px
                      </label>
                    </div>
                  </div>

                  <div className="flex flex-col sm:flex-row sm:items-center gap-x-6 gap-y-2">
                    <label className="flex items-center gap-3 text-sm text-ink sm:w-44 flex-none cursor-pointer">
                      <input
                        type="checkbox"
                        checked={webEnabled}
                        disabled={!isDownloadable}
                        onChange={(e) => setWebEnabled(e.target.checked)}
                        className="accent-brand-green-600"
                      />
                      Web Size
                    </label>
                    <div className="flex flex-wrap items-center gap-x-5 gap-y-2 pl-7 sm:pl-0">
                      {WEB_SIZE_OPTIONS.map((opt) => (
                        <label key={opt.value} className="inline-flex items-center gap-2 text-sm text-ink cursor-pointer">
                          <input
                            type="radio"
                            name="web-px"
                            checked={webPx === opt.value}
                            disabled={!isDownloadable || !webEnabled}
                            onChange={() => setWebPx(opt.value)}
                            className="accent-brand-green-600"
                          />
                          {opt.label}
                        </label>
                      ))}
                    </div>
                  </div>

                  {noSizeSelected && (
                    <p role="alert" className="text-xs text-red-600">Choose at least one download size.</p>
                  )}
                  <p className="text-xs text-muted">Allow photos to be downloaded in select sizes.</p>
                </div>

                {/* Download PIN — independent of the collection password.
                    Off by default; the PIN is typed by the photographer,
                    stored hashed, and never shown again. Off stops
                    enforcement but keeps the stored PIN. */}
                <div className="pt-4 border-t border-cream-200 space-y-3">
                  <p className="text-sm font-medium text-ink">Download PIN</p>
                  <label className="flex items-center gap-3 text-sm text-ink w-fit">
                    <span className="toggle-wrap">
                      <input
                        type="checkbox"
                        aria-label="Download PIN"
                        checked={pinEnabled}
                        disabled={!isDownloadable}
                        onChange={(e) => {
                          setPinEnabled(e.target.checked);
                          setPinEditing(false); setDownloadPin(""); setPinError("");
                        }}
                      />
                      <span className="toggle-slider" />
                    </span>
                    {pinEnabled ? "On" : "Off"}
                  </label>

                  {pinEnabled && (
                    <div className="space-y-2 max-w-xl">
                      {hasDownloadPin && !pinEditing ? (
                        <div className="flex items-center gap-2 px-3 py-2 rounded-lg border border-cream-200 bg-cream-50">
                          <span aria-label="PIN is set" className="flex-1 text-sm text-ink tracking-[0.3em]">••••</span>
                          <button
                            type="button"
                            disabled={pinUpdating || !isDownloadable}
                            onClick={() => { setPinEditing(true); setDownloadPin(""); setPinError(""); }}
                            className="px-2 py-1 text-xs font-medium text-brand-green-700 hover:underline underline-offset-2 cursor-pointer disabled:opacity-50"
                          >
                            Change
                          </button>
                        </div>
                      ) : (
                        <SecretField
                          id="download-pin"
                          value={downloadPin}
                          onChange={(v) => { setDownloadPin(v.replace(/\D/g, "").slice(0, 8)); setPinError(""); }}
                          onCommit={commitDownloadPin}
                          placeholder="4–8 digits"
                          inputMode="numeric"
                          maxLength={8}
                          autoFocus={pinEditing}
                          disabled={pinUpdating || !isDownloadable}
                          invalid={Boolean(pinError)}
                          label="PIN"
                        />
                      )}
                      {pinError && <p role="alert" className="text-xs text-red-600">{pinError}</p>}
                      {!hasDownloadPin && !pinError && (
                        <p className="text-xs text-amber-700">Enter a PIN to activate.</p>
                      )}
                    </div>
                  )}
                  <p className="text-xs text-muted">
                    Share this PIN with your client after payment. Visitors can preview the gallery without it.
                  </p>
                </div>

                <div className="pt-4 border-t border-cream-200 space-y-2">
                  <label className="flex items-center gap-3 text-sm font-medium text-ink w-fit cursor-pointer">
                    <input
                      type="checkbox"
                      checked={requireDownloadEmail}
                      disabled={!isDownloadable}
                      onChange={(e) => setRequireDownloadEmail(e.target.checked)}
                      className="accent-brand-green-600 disabled:cursor-not-allowed"
                    />
                    Require email
                  </label>
                  <p className="text-xs text-muted pl-7">Record the downloader's email before any download.</p>
                  {!requireDownloadEmail && !(pinEnabled && hasDownloadPin) && isDownloadable && (
                    <p className="text-xs text-amber-700 pl-7">Frictionless downloads are on: clients will not be asked for email or a PIN.</p>
                  )}
                </div>
              </div>
            )}

            {downloadSubTab === "advanced" && (
              <div className="space-y-5">
                {/* Limit Photo Downloads */}
                <div className="space-y-3">
                  <p className="text-sm font-medium text-ink">Limit Photo Downloads</p>
                  <OnOffToggle label="Limit Photo Downloads" checked={limitOn} onChange={toggleLimitTotal} />
                  {limitOn && (
                    <LimitField
                      id="limit-total"
                      committed={limitTotal}
                      onCommit={setLimitTotal}
                      placeholder="e.g. 100"
                      suffix="photos"
                    />
                  )}
                  {limitOn && limitTotal == null && (
                    <p className="text-xs text-amber-700">No limit until you enter a number.</p>
                  )}
                  <p className="text-xs text-muted">
                    Stop downloads once this many photos have been downloaded in total, shared by all visitors.
                    A gallery or set ZIP counts every photo in it.
                  </p>
                </div>

                {/* Restrict Downloads to Specific Contacts */}
                <div className="pt-5 border-t border-cream-200 space-y-3">
                  <p className="text-sm font-medium text-ink">Restrict Downloads to Specific Contacts</p>
                  <OnOffToggle label="Restrict Downloads to Specific Contacts" checked={restrictContacts} onChange={toggleRestrictContacts} />
                  {restrictContacts && (
                    <div className="space-y-2 max-w-xl">
                      <div
                        className={`flex flex-wrap items-center gap-2 p-2 rounded-lg border bg-white max-h-64 overflow-y-auto transition-all focus-within:ring-2 ${
                          emailError
                            ? "border-red-300 focus-within:border-red-400 focus-within:ring-red-200"
                            : "border-cream-200 focus-within:border-brand-green-500 focus-within:ring-brand-green-500/10"
                        }`}
                      >
                        {allowedEmails.map((email) => (
                          <span key={email} className="inline-flex items-center gap-1 max-w-full pl-2.5 pr-1 py-1 rounded-full bg-cream-100 border border-cream-200 text-xs text-ink">
                            <span className="truncate">{email}</span>
                            <button
                              type="button"
                              aria-label={`Remove ${email}`}
                              onClick={() => removeAllowedEmail(email)}
                              className="flex-none w-5 h-5 rounded-full text-muted hover:text-ink hover:bg-cream-200 cursor-pointer leading-none"
                            >
                              ×
                            </button>
                          </span>
                        ))}
                        <input
                          id="contacts-input"
                          type="text"
                          inputMode="email"
                          autoComplete="off"
                          autoCapitalize="none"
                          spellCheck={false}
                          placeholder={allowedEmails.length ? "Add another email" : "name@example.com"}
                          value={emailDraft}
                          onChange={(e) => {
                            const v = e.target.value;
                            if (v.includes(",") || v.includes(";")) addContacts(v);
                            else { setEmailDraft(v); setEmailError(""); }
                          }}
                          onKeyDown={(e) => {
                            if (e.key === "Enter") { e.preventDefault(); addContacts(emailDraft); }
                            else if (e.key === "Backspace" && !emailDraft && allowedEmails.length) {
                              removeAllowedEmail(allowedEmails[allowedEmails.length - 1]);
                            }
                          }}
                          onPaste={(e) => {
                            e.preventDefault();
                            addContacts(`${emailDraft} ${e.clipboardData.getData("text")}`);
                          }}
                          onBlur={() => addContacts(emailDraft)}
                          className="flex-1 min-w-[10rem] bg-transparent px-1 py-1 text-sm text-ink focus:outline-none"
                        />
                      </div>
                      {emailError && <p role="alert" className="text-xs text-red-600">{emailError}</p>}
                      <p className="text-xs text-muted" data-testid="contacts-count">
                        {allowedEmails.length} {allowedEmails.length === 1 ? "contact" : "contacts"}
                      </p>
                      {allowedEmails.length === 0 && (
                        <p className="text-xs text-amber-700">No one can download until you add at least one email.</p>
                      )}
                    </div>
                  )}
                  <p className="text-xs text-muted">Allow only specific contacts to download photos and videos.</p>
                </div>

                {/* Photo Sets Available for Download */}
                <div className="pt-5 border-t border-cream-200 space-y-3">
                  <p className="text-sm font-medium text-ink">Photo Sets Available for Download</p>
                  {sets === null ? (
                    <p className="text-xs text-muted">Loading sets…</p>
                  ) : sets.length === 0 ? (
                    <p className="text-xs text-muted">This gallery has no photo sets yet.</p>
                  ) : (
                    <div className="space-y-2">
                      {sets.map((set) => (
                        <label key={set.id} className="flex items-center gap-3 text-sm text-ink w-fit cursor-pointer">
                          <input
                            type="checkbox"
                            checked={isSetEnabled(set.id)}
                            onChange={() => toggleSet(set.id)}
                            className="accent-brand-green-600"
                          />
                          {set.name}
                        </label>
                      ))}
                    </div>
                  )}
                  {(setsError || setsInvalid) && (
                    <p role="alert" className="text-xs text-red-600">At least one set must stay available for download.</p>
                  )}
                  <p className="text-xs text-muted">
                    Select which sets visitors can download. This applies to set, single-photo and whole-gallery
                    downloads; while any set is unchecked, whole-gallery download is unavailable and visitors
                    download set by set.
                  </p>
                </div>

                {/* Limit PIN Usage */}
                <div className="pt-5 border-t border-cream-200 space-y-3">
                  <p className="text-sm font-medium text-ink">Limit PIN Usage</p>
                  {pinEnabled && hasDownloadPin ? (
                    <>
                      <OnOffToggle label="Limit PIN Usage" checked={pinLimitOn} onChange={togglePinLimit} />
                      {pinLimitOn && (
                        <>
                          <LimitField
                            id="pin-limit"
                            committed={pinLimit}
                            onCommit={setPinLimit}
                            placeholder="e.g. 5"
                            suffix="uses"
                          />
                          {pinLimit != null ? (
                            <p className="text-xs text-ink" data-testid="pin-usage">Used {pinUseCount} of {pinLimit}</p>
                          ) : (
                            <p className="text-xs text-amber-700">No limit until you enter a number.</p>
                          )}
                        </>
                      )}
                      <p className="text-xs text-muted">
                        Limit how many times this PIN can be entered. Each correct entry counts once and unlocks
                        downloads for a limited time, whatever the visitor downloads next (gallery, set or single
                        photo). Wrong PINs don't count. Changing the PIN resets the count.
                      </p>
                    </>
                  ) : (
                    <p className="text-xs text-muted">Turn on Download PIN in General to use this.</p>
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
