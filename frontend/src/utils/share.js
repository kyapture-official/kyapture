// File Location: frontend/src/utils/share.js
//
// Share helpers. The shared link is ALWAYS the gallery's plain client URL built
// by utils/appUrl.js — it carries no credential of any kind. Opening it puts the
// visitor in front of the gallery's normal gates (published, not expired,
// password), exactly like anyone else, so sharing can never grant access.

import { buildGalleryLink } from './appUrl.js'

/**
 * Normalizes whatever URL we were given down to `origin + path`. Anything
 * after the path (a query string such as ?token=…, a hash) is dropped, so even
 * a caller that mistakenly passes a URL with a secret attached can't put it
 * into an email or share payload. Returns '' for anything that isn't http(s).
 */
export function toCanonicalShareUrl(rawUrl) {
  try {
    const parsed = new URL(rawUrl, typeof window !== 'undefined' ? window.location.origin : undefined)
    if (parsed.protocol !== 'https:' && parsed.protocol !== 'http:') return ''
    return `${parsed.origin}${parsed.pathname}`.replace(/\/+$/, '')
  } catch {
    return ''
  }
}

/** The link to share for a gallery: built from the app origin, credential-free. */
export function resolveShareUrl(username, slug) {
  return toCanonicalShareUrl(buildGalleryLink(username, slug))
}

export function canNativeShare() {
  return typeof navigator !== 'undefined' && typeof navigator.share === 'function'
}

/** The sentence that accompanies a shared gallery link. */
export function shareText(title) {
  const heading = title ? title.trim() : ''
  return heading ? `${heading} — view the gallery` : 'View this gallery'
}

/** `mailto:` for "Share by email": the gallery title as subject, the link in the body. */
export function buildShareEmailHref({ url, title }) {
  const heading = title ? title.trim() : ''
  return `mailto:?subject=${encodeURIComponent(heading || 'A gallery for you')}&body=${encodeURIComponent(`${shareText(title)}:\n\n${url}`)}`
}

/**
 * The Share submenu entries for a gallery's three-dot menu: the same four labels,
 * in the same order, as the client gallery's Share popover (components/shared/
 * ShareMenu.jsx). "Share by email" is a mailto: link (there is no email service);
 * "Share…" (native share sheet) is present only where the device supports it.
 * The handlers are supplied by the caller, which owns the modals.
 */
export function buildShareMenuChildren({ url, title, onLink, onQr, onNative }) {
  const children = [
    { key: 'email', label: 'Share by email', href: buildShareEmailHref({ url, title }) },
    { key: 'link', label: 'Get direct link', onSelect: onLink },
    { key: 'qr', label: 'Get QR code', onSelect: onQr },
  ]
  if (canNativeShare()) children.push({ key: 'native', label: 'Share…', onSelect: onNative })
  return children
}

/**
 * Copies text. Tries the async Clipboard API (needs a secure context), then the
 * legacy execCommand path (works on plain http and older browsers). Resolves
 * true/false — never throws — so the caller can show an honest result.
 */
export async function copyText(text) {
  try {
    if (typeof navigator !== 'undefined' && navigator.clipboard?.writeText && window.isSecureContext) {
      await navigator.clipboard.writeText(text)
      return true
    }
  } catch {
    /* fall through to the legacy path */
  }
  try {
    const area = document.createElement('textarea')
    area.value = text
    area.setAttribute('readonly', '')
    area.style.cssText = 'position:fixed;top:0;left:0;opacity:0;pointer-events:none;'
    document.body.appendChild(area)
    area.select()
    area.setSelectionRange(0, text.length)
    const ok = document.execCommand('copy')
    area.remove()
    return Boolean(ok)
  } catch {
    return false
  }
}
