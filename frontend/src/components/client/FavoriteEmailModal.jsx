import { useId, useState } from "react";
import ClientDialog from "./ClientDialog";

const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

/**
 * First heart on a gallery: "Enter your email to save favorites". The email
 * (and an optional name) is remembered in this browser, so it is asked once; it
 * creates the visitor's default "My Favorites" list, and the photographer sees
 * the email next to what was saved.
 */
export default function FavoriteEmailModal({ open, onClose, onSubmit, galleryTitle, photographerName, initialEmail = "", initialName = "" }) {
  const uid = useId();
  const [email, setEmail] = useState(initialEmail);
  const [name, setName] = useState(initialName);
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const handleSubmit = async (event) => {
    event.preventDefault();
    if (submitting) return;
    const cleanEmail = email.trim();
    if (!EMAIL_PATTERN.test(cleanEmail)) {
      setError("Please enter a valid email address.");
      return;
    }
    setError("");
    setSubmitting(true);
    try {
      await onSubmit({ email: cleanEmail, name: name.trim() });
    } catch (err) {
      setError(err?.message || "We couldn't save that. Please try again.");
    } finally {
      setSubmitting(false);
    }
  };

  const inputClass = (invalid) =>
    `block w-full rounded-lg border px-3.5 py-3 text-sm text-ink bg-white focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-green-500 ${invalid ? "border-red-500" : "border-cream-300"}`;

  return (
    <ClientDialog open={open} onClose={onClose} galleryTitle={galleryTitle} photographerName={photographerName} heading="Favorites">
      <form onSubmit={handleSubmit} noValidate className="space-y-5 text-center">
        <div>
          <h4 className="font-serif text-xl uppercase tracking-[0.14em] text-ink">Save Favorites</h4>
          <p className="mt-3 text-sm leading-relaxed text-muted">Enter your email to save favorites. You can come back to your list any time on this device.</p>
        </div>
        <div className="space-y-4 text-left">
          <div className="space-y-1.5">
            <label htmlFor={`${uid}-email`} className="block text-[11px] font-medium uppercase tracking-wider text-muted">Email address</label>
            <input id={`${uid}-email`} type="email" autoComplete="email" autoFocus value={email} onChange={(event) => setEmail(event.target.value)} placeholder="you@email.com" aria-invalid={Boolean(error)} className={inputClass(Boolean(error))} />
            {error && <p role="alert" className="text-xs text-red-600">{error}</p>}
          </div>
          <div className="space-y-1.5">
            <label htmlFor={`${uid}-name`} className="block text-[11px] font-medium uppercase tracking-wider text-muted">Name <span className="normal-case tracking-normal">(optional)</span></label>
            <input id={`${uid}-name`} type="text" autoComplete="name" maxLength={80} value={name} onChange={(event) => setName(event.target.value)} placeholder="Your name" className={inputClass(false)} />
          </div>
        </div>
        <div className="flex justify-center gap-2">
          <button type="button" onClick={onClose} className="rounded-lg px-4 py-2.5 text-sm text-muted transition hover:text-ink">Cancel</button>
          <button type="submit" disabled={submitting} className="rounded-lg bg-ink px-8 py-3 text-xs font-medium uppercase tracking-[0.2em] text-white transition hover:bg-ink/85 disabled:cursor-not-allowed disabled:opacity-60">
            {submitting ? "Saving…" : "Continue"}
          </button>
        </div>
      </form>
    </ClientDialog>
  );
}
