import { useId, useMemo, useState } from "react";
import { clientsApi } from "../../api/clientsApi";
import { useClientStore } from "../../store/clientStore";

const SIZE_OPTIONS = [
  { value: "download", label: "High Resolution", hint: "Full-quality photos" },
  { value: "web", label: "Web Size", hint: "Smaller files, easy to share" },
];
const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
const EXPIRY_MARGIN_MS = 60 * 1000;

function startBrowserDownload(href, filename) {
  const anchor = document.createElement("a");
  anchor.href = href;
  anchor.rel = "noopener";
  anchor.download = filename || "";
  anchor.style.display = "none";
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
}

function downloadFilename(slug, target, selectedSet) {
  if (target?.type === "photo") return target.photo?.original_name || "photo";
  return `${slug}${selectedSet ? `-${selectedSet.name}` : ""}.zip`;
}

/**
 * Explicit download flow: choose scope/size, then request identity only when
 * server policy requires it. The browser owns the resulting stream, avoiding
 * large ZIPs in JavaScript memory.
 */
export default function DownloadForm({
  username,
  slug,
  galleryToken = null,
  hasDownloadPin = false,
  downloadPolicy,
  target,
  photoSets = [],
  photoCount = 0,
  onCancel,
}) {
  const uid = useId();
  const sessionKey = `${username}:${slug}`;
  const getDownloadAccess = useClientStore((state) => state.getDownloadAccess);
  const setDownloadAccess = useClientStore((state) => state.setDownloadAccess);
  const storedAccess = useClientStore((state) => state.downloadAccess[sessionKey]);
  const policy = downloadPolicy || { allowed_sizes: ["download", "web"], require_email: true };
  const allowedSizes = useMemo(() => {
    const values = Array.isArray(policy.allowed_sizes) ? policy.allowed_sizes : [];
    const allowed = SIZE_OPTIONS.filter((option) => values.includes(option.value));
    return allowed.length ? allowed : SIZE_OPTIONS;
  }, [policy.allowed_sizes]);
  const requiresEmail = policy.require_email !== false;
  const requiresAccess = requiresEmail || hasDownloadPin;
  const isPhoto = target?.type === "photo";

  const [step, setStep] = useState("choose");
  const [scopeSetId, setScopeSetId] = useState(target?.type === "gallery" ? target.setId || "" : "");
  const [resolution, setResolution] = useState(allowedSizes[0].value);
  const [email, setEmail] = useState(storedAccess?.email || "");
  const [pin, setPin] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [errors, setErrors] = useState({});
  const selectedSet = photoSets.find((set) => set.id === scopeSetId) || null;

  const launchDownload = (access = null) => {
    const href = isPhoto
      ? clientsApi.buildPhotoDownloadHref(target.photo?.download_url, {
          token: galleryToken, downloadToken: access?.token, resolution,
        })
      : clientsApi.buildGalleryDownloadAllHref(username, slug, {
          token: galleryToken, downloadToken: access?.token, resolution, setId: scopeSetId || undefined,
        });
    if (!href) {
      setErrors({ form: "This file isn't available for download." });
      return;
    }
    startBrowserDownload(href, downloadFilename(slug, target, selectedSet));
    setStep("requested");
  };

  const handleChoose = (event) => {
    event.preventDefault();
    setErrors({});
    const rememberedAccess = getDownloadAccess(sessionKey);
    if (!requiresAccess || rememberedAccess) {
      launchDownload(rememberedAccess);
      return;
    }
    setStep("identity");
  };

  const handleAuthorizationError = (err) => {
    if (err?.status === 429) {
      setErrors({ form: "Too many attempts. Please wait a minute and try again." });
    } else if (err?.code === "pin_required" || err?.code === "invalid_pin") {
      setPin("");
      setErrors({ pin: err.message });
    } else if (err?.code === "email_required" || err?.code === "invalid_email") {
      setErrors({ email: err.message });
    } else {
      setErrors({ form: err?.message || "Something went wrong. Please try again." });
    }
  };

  const handleIdentity = async (event) => {
    event.preventDefault();
    if (submitting) return;
    setErrors({});
    const cleanEmail = email.trim();
    if (requiresEmail && !EMAIL_PATTERN.test(cleanEmail)) {
      setErrors({ email: "Please enter a valid email address." });
      return;
    }
    if (hasDownloadPin && !pin.trim()) {
      setErrors({ pin: "Enter the download PIN your photographer gave you." });
      return;
    }
    setSubmitting(true);
    try {
      const grant = await clientsApi.requestDownloadAccess(username, slug, {
        email: requiresEmail ? cleanEmail : undefined,
        pin: hasDownloadPin ? pin.trim() : undefined,
        token: galleryToken,
      });
      const access = {
        token: grant.download_token,
        email: grant.email || cleanEmail || null,
        expiresAt: Date.now() + Math.max(0, (grant.expires_in || 0) * 1000 - EXPIRY_MARGIN_MS),
      };
      setDownloadAccess(sessionKey, access);
      setPin("");
      launchDownload(access);
    } catch (err) {
      handleAuthorizationError(err);
    } finally {
      setSubmitting(false);
    }
  };

  const inputClass = (hasError) =>
    `block w-full rounded-lg border px-3.5 py-2.5 text-sm text-ink bg-white focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-green-500 ${hasError ? "border-red-500" : "border-cream-300"}`;

  if (step === "requested") {
    const filename = downloadFilename(slug, target, selectedSet);
    const sizeLabel = SIZE_OPTIONS.find((option) => option.value === resolution)?.label;
    return (
      <div className="space-y-5 text-center" aria-live="polite">
        <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-cream-100">
          <svg className="h-6 w-6 text-ink" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.8} d="M12 3v12m0 0 4-4m-4 4-4-4m-5 6v2a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-2" /></svg>
        </div>
        <div>
          <h4 className="font-serif text-xl text-ink">Your download was requested</h4>
          <p className="mt-2 text-sm leading-relaxed text-muted">{isPhoto ? "Your browser is downloading the selected photo." : "Your browser is preparing the ZIP. Keep this tab open while it begins downloading."}</p>
        </div>
        <p className="rounded-lg bg-cream-100 px-3 py-2 text-xs text-muted" title={filename}>{filename} · {sizeLabel}</p>
        <div className="flex justify-center gap-3">
          <button type="button" onClick={() => setStep("choose")} className="rounded-lg border border-cream-300 px-4 py-2 text-sm text-ink hover:bg-cream-100">Download again</button>
          <button type="button" onClick={onCancel} className="rounded-lg bg-ink px-4 py-2 text-sm text-white hover:bg-ink/85">Done</button>
        </div>
      </div>
    );
  }

  if (step === "identity") {
    return (
      <form onSubmit={handleIdentity} noValidate className="space-y-5 text-left">
        <div>
          <h4 className="font-serif text-xl text-ink">Download Photos</h4>
          {requiresEmail && <p className="mt-1 text-sm leading-relaxed text-muted">Your email will be used to notify you when the files are ready.</p>}
        </div>
        {requiresEmail && <div className="space-y-1.5"><label htmlFor={`${uid}-email`} className="block text-[11px] font-medium uppercase tracking-wider text-muted">Email address</label><input id={`${uid}-email`} type="email" autoComplete="email" value={email} onChange={(event) => setEmail(event.target.value)} placeholder="you@email.com" aria-invalid={Boolean(errors.email)} className={inputClass(errors.email)} />{errors.email && <p role="alert" className="text-xs text-red-600">{errors.email}</p>}</div>}
        {hasDownloadPin && <div className="space-y-1.5"><label htmlFor={`${uid}-pin`} className="block text-[11px] font-medium uppercase tracking-wider text-muted">Download PIN</label><input id={`${uid}-pin`} type="password" inputMode="numeric" autoComplete="off" maxLength={8} value={pin} onChange={(event) => setPin(event.target.value.replace(/\D/g, ""))} placeholder="PIN from your photographer" aria-invalid={Boolean(errors.pin)} className={inputClass(errors.pin)} />{errors.pin && <p role="alert" className="text-xs text-red-600">{errors.pin}</p>}</div>}
        {errors.form && <p role="alert" className="rounded-lg bg-red-50 px-3 py-2 text-xs text-red-700">{errors.form}</p>}
        <div className="flex justify-end gap-2 pt-1"><button type="button" onClick={() => setStep("choose")} className="rounded-lg px-4 py-2.5 text-sm text-muted hover:text-ink">Back</button><button type="submit" disabled={submitting} className="rounded-lg bg-ink px-6 py-2.5 text-sm font-medium text-white hover:bg-ink/85 disabled:cursor-not-allowed disabled:opacity-60">{submitting ? "Checking…" : "Next"}</button></div>
      </form>
    );
  }

  return (
    <form onSubmit={handleChoose} noValidate className="space-y-5 text-left">
      {!isPhoto && <fieldset className="space-y-2"><legend className="mb-1 text-[11px] font-medium uppercase tracking-wider text-muted">Choose photos</legend>{[{ id: "", name: "All photos", photo_count: photoCount }, ...photoSets].map((option) => <label key={option.id || "all"} className="flex cursor-pointer items-center justify-between gap-3 rounded-lg border border-cream-200 px-3 py-2.5 text-sm text-ink hover:bg-cream-100"><span className="flex items-center gap-2.5"><input type="radio" name={`${uid}-scope`} checked={scopeSetId === option.id} onChange={() => setScopeSetId(option.id)} className="accent-brand-green-600" />{option.name}</span><span className="text-xs text-muted">{option.photo_count ?? 0}</span></label>)}</fieldset>}
      {isPhoto && <p className="truncate text-sm text-muted">{target.photo?.original_name || "This photo"}</p>}
      <fieldset><legend className="mb-2 text-[11px] font-medium uppercase tracking-wider text-muted">Choose download size</legend><div className="grid grid-cols-2 gap-2">{allowedSizes.map((option) => { const selected = resolution === option.value; return <label key={option.value} className={`cursor-pointer rounded-lg border px-3 py-2.5 transition-colors ${selected ? "border-ink bg-white" : "border-cream-300 bg-cream-100 hover:bg-white"}`}><input type="radio" name={`${uid}-resolution`} value={option.value} checked={selected} onChange={() => setResolution(option.value)} className="sr-only" /><span className="block text-xs font-medium text-ink">{option.label}</span><span className="mt-0.5 block text-[11px] text-muted">{option.hint}</span></label>; })}</div></fieldset>
      <div className="rounded-lg bg-cream-100 px-3 py-2.5 text-sm text-ink"><span className="text-muted">Download to:</span> My Device</div>
      {errors.form && <p role="alert" className="rounded-lg bg-red-50 px-3 py-2 text-xs text-red-700">{errors.form}</p>}
      <div className="flex justify-end gap-2 pt-1">{onCancel && <button type="button" onClick={onCancel} className="rounded-lg px-4 py-2.5 text-sm text-muted hover:text-ink">Cancel</button>}<button type="submit" className="rounded-lg bg-ink px-6 py-2.5 text-sm font-medium text-white hover:bg-ink/85">Start Download</button></div>
    </form>
  );
}
