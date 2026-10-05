// File Location: frontend/src/components/shared/WatermarkSettings.jsx
import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { galleriesApi } from "../../api/galleriesApi";
import { useAuthStore } from "../../store/authStore";
import { useSubscription } from "../../hooks/useSubscription";
import { useToast } from "../ui/Toast";
import UpgradePrompt from "./UpgradePrompt";

/**
 * Watermark settings for one gallery (Gallery settings → Watermark).
 *
 * Persistence reuses what already exists: the on/off switch is the gallery's
 * `watermark_enabled`, everything else lives in `design_settings.watermark`.
 * The server validates every value and refuses the write for a plan without
 * Watermark — the locked state here only explains that refusal.
 *
 * What it affects (see apps/core/watermark.py): the gallery images clients
 * browse — display, medium and thumbnail. Your original files and the
 * High Resolution download are never watermarked. Existing photos are
 * re-processed in the background after a save; new uploads use the settings
 * automatically.
 */

const DEFAULTS = { type: "text", text: "", position: "bottom-right", opacity: 55, size: 20, margin: 5 };
const POSITIONS = [
  "top-left", "top-center", "top-right",
  "center-left", "center", "center-right",
  "bottom-left", "bottom-center", "bottom-right",
];
// position -> [vertical, horizontal] anchor, matching the server's grid.
const ANCHORS = {
  "top-left": ["top", "left"], "top-center": ["top", "center"], "top-right": ["top", "right"],
  "center-left": ["center", "left"], center: ["center", "center"], "center-right": ["center", "right"],
  "bottom-left": ["bottom", "left"], "bottom-center": ["bottom", "center"], "bottom-right": ["bottom", "right"],
};
const POSITION_LABELS = {
  "top-left": "Top left", "top-center": "Top center", "top-right": "Top right",
  "center-left": "Middle left", center: "Center", "center-right": "Middle right",
  "bottom-left": "Bottom left", "bottom-center": "Bottom center", "bottom-right": "Bottom right",
};

function Slider({ id, label, value, min, max, unit = "%", onChange, disabled }) {
  return (
    <div className="space-y-1">
      <div className="flex items-center justify-between">
        <label htmlFor={id} className="text-xs font-semibold text-ink/80">{label}</label>
        <span className="font-mono text-xs text-muted">{value}{unit}</span>
      </div>
      <input
        id={id}
        type="range"
        min={min}
        max={max}
        value={value}
        disabled={disabled}
        onChange={(e) => onChange(Number(e.target.value))}
        className="w-full accent-brand-green-600 disabled:opacity-50"
      />
    </div>
  );
}

/** Rough visual preview of where/how big the mark will be — not pixel-exact. */
function Preview({ config, logoUrl, fallbackText }) {
  const boxRef = useRef(null);
  const [width, setWidth] = useState(320);
  useEffect(() => {
    const el = boxRef.current;
    if (!el || typeof ResizeObserver === "undefined") return undefined;
    const observer = new ResizeObserver(([entry]) => setWidth(entry.contentRect.width));
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  const [vertical, horizontal] = ANCHORS[config.position] || ANCHORS[DEFAULTS.position];
  const margin = (config.margin / 100) * Math.min(width, (width * 10) / 16);
  const style = {
    position: "absolute",
    opacity: config.opacity / 100,
    [vertical === "center" ? "top" : vertical]: vertical === "center" ? "50%" : margin,
    [horizontal === "center" ? "left" : horizontal]: horizontal === "center" ? "50%" : margin,
    transform: `translate(${horizontal === "center" ? "-50%" : "0"}, ${vertical === "center" ? "-50%" : "0"})`,
    width: `${config.size}%`,
  };
  const text = config.text.trim() || fallbackText;
  const fontSize = Math.max(8, (width * config.size) / 100 / Math.max(4, text.length * 0.62));

  return (
    <div
      ref={boxRef}
      aria-label="Watermark preview"
      className="relative w-full overflow-hidden rounded-xl border border-cream-200"
      style={{ aspectRatio: "16 / 10", background: "linear-gradient(135deg,#5b7c99,#c9b79c 55%,#8a6f5a)" }}
    >
      {config.type === "logo" ? (
        logoUrl ? (
          <img src={logoUrl} alt="" style={style} className="object-contain" draggable={false} />
        ) : null
      ) : (
        <span
          style={{ ...style, fontSize, textShadow: "0 1px 3px rgba(0,0,0,.55)" }}
          className="whitespace-nowrap font-semibold leading-none text-white"
        >
          {text}
        </span>
      )}
    </div>
  );
}

export default function WatermarkSettings({ gallery, setGallery, slug, isMountedRef }) {
  const toast = useToast();
  const user = useAuthStore((s) => s.user);
  const { entitlements, loading: planLoading } = useSubscription();
  const locked = !planLoading && !entitlements.watermark;

  const stored = gallery.design_settings?.watermark || {};
  const [enabled, setEnabled] = useState(Boolean(gallery.watermark_enabled));
  const [config, setConfig] = useState({ ...DEFAULTS, ...stored });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  const logoUrl = user?.logo || null;
  const fallbackText = `© ${user?.display_name || user?.username || "Your Name"}`;
  const set = (key) => (value) => setConfig((prev) => ({ ...prev, [key]: value }));

  const save = async (nextEnabled = enabled) => {
    if (saving) return;
    setSaving(true);
    setError("");
    try {
      const payload = { watermark_enabled: nextEnabled };
      // A locked (lapsed) account may still switch the watermark OFF; only
      // send settings when the plan includes them.
      if (!locked) {
        const { coverPhoto: _coverPhoto, ...settingsWithoutCover } = gallery.design_settings || {};
        payload.design_settings = { ...settingsWithoutCover, watermark: { ...config, text: config.text.trim() } };
      }
      const updated = await galleriesApi.updateGallery(slug, payload);
      if (isMountedRef?.current === false) return;
      setGallery((prev) => ({ ...prev, ...updated }));
      setEnabled(Boolean(updated.watermark_enabled));
      toast(
        nextEnabled
          ? "Watermark saved. Existing photos are updating in the background."
          : "Watermark turned off. Existing photos are updating in the background.",
        "success",
      );
    } catch (err) {
      if (isMountedRef?.current === false) return;
      const data = err.response?.data;
      const details = data?.details?.watermark || data?.watermark;
      const detailMessage =
        details && typeof details === "object" ? Object.values(details).flat().join(" ") : details;
      setError(
        data?.code === "watermark_requires_upgrade"
          ? data.error
          : detailMessage || data?.error || "Failed to save the watermark.",
      );
      toast("Failed to save the watermark", "error");
    } finally {
      if (isMountedRef?.current !== false) setSaving(false);
    }
  };

  const controlsDisabled = locked || saving || planLoading;
  const needsLogo = config.type === "logo" && !logoUrl;

  return (
    <div className="space-y-6 rounded-2xl border border-cream-200 bg-surface-light p-6 shadow-card">
      <div>
        <h2 className="font-serif text-lg text-ink">Watermark</h2>
        <p className="mt-1 text-xs text-muted">
          Protect the photos clients browse. Your original files and the High Resolution download are
          never watermarked.
        </p>
      </div>

      {locked && (
        <UpgradePrompt
          feature="watermark"
          message={
            gallery.watermark_enabled
              ? "Your current plan no longer includes watermarking, so new photos are not watermarked. You can turn the setting off below."
              : "Add a text or logo watermark to your client galleries."
          }
        />
      )}

      <div className="flex items-center justify-between rounded-xl border border-cream-200 bg-cream-100 p-4">
        <div>
          <p className="text-sm font-medium text-ink">Enable watermark</p>
          <p className="mt-0.5 text-xs text-muted">Applied to display, medium and thumbnail images.</p>
        </div>
        <label className="toggle-wrap">
          <input
            type="checkbox"
            aria-label="Enable watermark"
            checked={enabled}
            disabled={saving || planLoading || (locked && !enabled)}
            onChange={(e) => {
              const next = e.target.checked;
              setEnabled(next);
              // Turning it off saves immediately (always allowed); turning it
              // on waits for the settings below and an explicit save.
              if (!next) save(false);
            }}
          />
          <span className="toggle-slider" />
        </label>
      </div>

      <fieldset disabled={controlsDisabled} className="space-y-5 disabled:opacity-60">
        <div>
          <legend className="mb-2 text-xs font-semibold text-ink/80">Type</legend>
          <div className="flex gap-2">
            {[
              { value: "text", label: "Text" },
              { value: "logo", label: "Logo" },
            ].map((option) => (
              <label
                key={option.value}
                className={`flex-1 cursor-pointer rounded-lg border px-3 py-2 text-center text-sm transition-colors ${
                  config.type === option.value ? "border-ink bg-white text-ink" : "border-cream-200 bg-cream-100 text-muted"
                }`}
              >
                <input
                  type="radio"
                  name="watermark-type"
                  value={option.value}
                  checked={config.type === option.value}
                  onChange={() => set("type")(option.value)}
                  className="sr-only"
                />
                {option.label}
              </label>
            ))}
          </div>
        </div>

        {config.type === "text" ? (
          <div className="space-y-1">
            <label htmlFor="watermark-text" className="text-xs font-semibold text-ink/80">Watermark text</label>
            <input
              id="watermark-text"
              type="text"
              maxLength={60}
              value={config.text}
              placeholder={fallbackText}
              onChange={(e) => set("text")(e.target.value)}
              className="w-full rounded-lg border border-cream-200 px-3 py-2 text-sm focus:border-brand-green-500 focus:outline-none focus:ring-2 focus:ring-brand-green-500/10"
            />
            <p className="text-[11px] text-muted">Leave blank to use “{fallbackText}”.</p>
          </div>
        ) : (
          <div className="rounded-xl border border-cream-200 bg-cream-100 p-4 text-xs text-muted">
            {logoUrl ? (
              <div className="flex items-center gap-3">
                <img src={logoUrl} alt="Your business logo" className="h-10 w-16 rounded border border-cream-200 bg-white object-contain p-1" />
                <span>Your business logo is used as the watermark.</span>
              </div>
            ) : (
              <span>
                A logo watermark uses your business logo.{" "}
                <Link to="/dashboard/settings/branding" className="font-medium text-ink underline underline-offset-2">
                  Upload it in Branding settings
                </Link>{" "}
                first.
              </span>
            )}
          </div>
        )}

        <div>
          <legend className="mb-2 text-xs font-semibold text-ink/80">Position</legend>
          <div role="radiogroup" aria-label="Watermark position" className="grid w-40 grid-cols-3 gap-1.5">
            {POSITIONS.map((position) => (
              <button
                key={position}
                type="button"
                role="radio"
                aria-checked={config.position === position}
                aria-label={POSITION_LABELS[position]}
                title={POSITION_LABELS[position]}
                onClick={() => set("position")(position)}
                className={`h-9 rounded-md border transition-colors ${
                  config.position === position ? "border-ink bg-ink" : "border-cream-300 bg-cream-100 hover:bg-white"
                }`}
              />
            ))}
          </div>
        </div>

        <div className="grid gap-4 sm:grid-cols-3">
          <Slider id="watermark-opacity" label="Opacity" value={config.opacity} min={5} max={100} onChange={set("opacity")} />
          <Slider id="watermark-size" label="Size" value={config.size} min={5} max={50} onChange={set("size")} />
          <Slider id="watermark-margin" label="Margin" value={config.margin} min={0} max={20} onChange={set("margin")} />
        </div>

        <Preview config={config} logoUrl={logoUrl} fallbackText={fallbackText} />
      </fieldset>

      {error && (
        <p role="alert" className="rounded-lg bg-red-50 px-3 py-2 text-xs text-red-700">{error}</p>
      )}

      <div className="flex items-center justify-between gap-4 border-t border-cream-200 pt-4">
        <p className="text-[11px] leading-relaxed text-muted">
          Changes apply to new uploads right away; photos already in this gallery are updated in the background.
        </p>
        <button
          type="button"
          onClick={() => save(enabled)}
          disabled={controlsDisabled || needsLogo}
          className="flex-shrink-0 cursor-pointer rounded-lg bg-brand-green-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-brand-green-700 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {saving ? "Saving…" : "Save Watermark"}
        </button>
      </div>
    </div>
  );
}
