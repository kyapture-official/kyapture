import { useId, useRef, useState } from "react";
import { clientsApi } from "../../api/clientsApi";
import { useClientStore } from "../../store/clientStore";
import { useVisitorStore } from "../../store/visitorStore";
import { EMAIL_PATTERN, blockedMessage, gateIntro, tooManyAttemptsMessage } from "../../utils/downloadFlow.js";
import { pageButtonClass } from "./DownloadShell";

const EXPIRY_MARGIN_MS = 60 * 1000;

const inputClass = (hasError) =>
  `block h-12 w-full border bg-white px-4 text-base text-ink placeholder:text-muted/70 focus:border-ink focus:outline-none ${hasError ? "border-red-500" : "border-cream-300"}`;

/**
 * Download page 1 — "DOWNLOAD PHOTOS". Asks only for what this visitor still
 * owes: an email (the gallery requires one) and/or the Download PIN. NEXT sends
 * both to the server together; the server is the one that decides, so a wrong PIN
 * comes back as an inline "Incorrect PIN" and nothing is skipped by editing the URL.
 * The single-photo dialog reuses it with its own `heading` and `intro`.
 *
 * "Restrict Downloads to Specific Contacts" (7-B): an address on the list is
 * proven, not just typed. The server answers the first NEXT with
 * `email_verification_required` and emails a 6-digit code; this step then asks
 * for that code and sends it with the same email/PIN.
 */
export default function DownloadAuthStep({
  username,
  slug,
  galleryToken = null,
  studio,
  needsEmail,
  needsPin,
  notice = "",
  heading = "Download Photos",
  intro = null,
  onGranted,
}) {
  const uid = useId();
  const sessionKey = `${username}:${slug}`;
  const setDownloadAccess = useClientStore((state) => state.setDownloadAccess);
  const profile = useVisitorStore((state) => state.profiles[sessionKey]);
  const setProfile = useVisitorStore((state) => state.setProfile);

  const [email, setEmail] = useState(profile?.email || "");
  const [pin, setPin] = useState("");
  const [errors, setErrors] = useState(notice ? { form: notice } : {});
  const [submitting, setSubmitting] = useState(false);
  const [codeSentTo, setCodeSentTo] = useState(null);
  const [emailCode, setEmailCode] = useState("");
  const pinInputRef = useRef(null);

  const useAnotherEmail = () => {
    setCodeSentTo(null);
    setEmailCode("");
    setErrors({});
  };

  const handleError = (err) => {
    if (err?.status === 429) {
      setPin("");
      setErrors({ form: tooManyAttemptsMessage(err) });
    } else if (err?.code === "pin_required" || err?.code === "invalid_pin") {
      setPin("");
      setErrors({ pin: "Incorrect PIN" });
      requestAnimationFrame(() => pinInputRef.current?.focus());
    } else if (err?.code === "email_required" || err?.code === "invalid_email") {
      setErrors({ email: err.message });
    } else if (err?.code === "email_not_authorized") {
      setErrors({ email: blockedMessage(err.code, studio, err.message) });
    } else if (err?.code === "invalid_email_code") {
      setEmailCode("");
      setErrors({ code: err.message });
    } else if (err?.code === "pin_limit_reached") {
      setErrors({ form: blockedMessage(err.code, studio, err.message) });
    } else {
      setErrors({ form: err?.message || "Something went wrong. Please try again." });
    }
  };

  const handleSubmit = async (event) => {
    event.preventDefault();
    if (submitting) return;
    const cleanEmail = email.trim();
    const problems = {};
    if (needsEmail && !EMAIL_PATTERN.test(cleanEmail)) problems.email = "Please enter a valid email address.";
    if (needsPin && !pin.trim()) problems.pin = "Enter the download PIN.";
    if (codeSentTo && !/^\d{6}$/.test(emailCode.trim())) problems.code = "Enter the 6-digit code from the email.";
    setErrors(problems);
    if (Object.keys(problems).length) return;

    setSubmitting(true);
    try {
      const grant = await clientsApi.requestDownloadAccess(
        username,
        slug,
        {
          email: needsEmail ? cleanEmail : undefined,
          pin: needsPin ? pin.trim() : undefined,
          emailCode: codeSentTo ? emailCode.trim() : undefined,
          token: galleryToken,
        },
      );
      if (grant?.code === "email_verification_required") {
        setCodeSentTo(grant.email || cleanEmail);
        setEmailCode("");
        setErrors({});
        return;
      }
      const access = {
        token: grant.download_token,
        email: grant.email || (needsEmail ? cleanEmail : null),
        expiresAt: Date.now() + Math.max(0, (grant.expires_in || 0) * 1000 - EXPIRY_MARGIN_MS),
      };
      setDownloadAccess(sessionKey, access);
      if (access.email) setProfile(sessionKey, { email: access.email, name: profile?.name || "" });
      setPin("");
      onGranted(access);
    } catch (err) {
      handleError(err);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <form onSubmit={handleSubmit} noValidate className="space-y-8">
      <h2 className="text-center font-serif text-xl font-bold uppercase tracking-[0.16em] text-ink">{heading}</h2>
      <p className="text-[15px] leading-8 text-muted">{intro ?? gateIntro({ needsEmail, needsPin, studio })}</p>

      {codeSentTo ? (
        <div className="space-y-3">
          <p className="text-[15px] leading-7 text-ink">
            We sent a 6-digit code to <span className="font-medium break-all">{codeSentTo}</span>. Enter it to continue.
          </p>
          <label htmlFor={`${uid}-code`} className="sr-only">Code from the email</label>
          <input
            id={`${uid}-code`}
            type="text"
            inputMode="numeric"
            autoComplete="one-time-code"
            autoFocus
            maxLength={6}
            value={emailCode}
            onChange={(event) => { setEmailCode(event.target.value.replace(/\D/g, "")); if (errors.code || errors.form) setErrors({}); }}
            placeholder="6-digit code"
            aria-invalid={Boolean(errors.code)}
            aria-describedby={errors.code ? `${uid}-code-error` : undefined}
            className={inputClass(errors.code)}
          />
          {errors.code && <p id={`${uid}-code-error`} role="alert" className="mt-1.5 text-sm text-red-600">{errors.code}</p>}
          <button type="button" onClick={useAnotherEmail} className="cursor-pointer text-sm text-muted underline underline-offset-4 hover:text-ink">
            Use a different email
          </button>
        </div>
      ) : (
      <div className="space-y-4">
        {needsEmail && (
          <div>
            <label htmlFor={`${uid}-email`} className="sr-only">Email address</label>
            <input
              id={`${uid}-email`}
              type="email"
              autoComplete="email"
              autoFocus={!email}
              value={email}
              onChange={(event) => { setEmail(event.target.value); if (errors.email || errors.form) setErrors({}); }}
              placeholder="Enter your email"
              aria-invalid={Boolean(errors.email)}
              aria-describedby={errors.email ? `${uid}-email-error` : undefined}
              className={inputClass(errors.email)}
            />
            {errors.email && <p id={`${uid}-email-error`} role="alert" className="mt-1.5 text-sm text-red-600">{errors.email}</p>}
          </div>
        )}
        {needsPin && (
          <div>
            <label htmlFor={`${uid}-pin`} className="sr-only">Download PIN</label>
            <input
              id={`${uid}-pin`}
              ref={pinInputRef}
              type="password"
              inputMode="numeric"
              autoComplete="off"
              autoFocus={Boolean(email) || !needsEmail}
              maxLength={8}
              value={pin}
              onChange={(event) => { setPin(event.target.value.replace(/\D/g, "")); if (errors.pin || errors.form) setErrors({}); }}
              placeholder="Enter download PIN"
              aria-invalid={Boolean(errors.pin)}
              aria-describedby={errors.pin ? `${uid}-pin-error` : undefined}
              className={inputClass(errors.pin)}
            />
            {errors.pin && <p id={`${uid}-pin-error`} role="alert" className="mt-1.5 text-sm text-red-600">{errors.pin}</p>}
          </div>
        )}
      </div>
      )}

      {errors.form && <p role="alert" className="bg-red-50 px-3 py-2 text-sm text-red-700">{errors.form}</p>}

      <div className="flex justify-center">
        <button type="submit" disabled={submitting} className={pageButtonClass}>{submitting ? "Checking…" : "Next"}</button>
      </div>
    </form>
  );
}
