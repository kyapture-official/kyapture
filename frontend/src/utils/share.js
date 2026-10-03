// File Location: frontend/src/utils/share.js
//
// Share helpers. The shared link is ALWAYS the gallery's canonical, plain
// client URL — the server sends it as `share_url` (built from the public app
// origin) and it carries no credential of any kind. Opening it puts the visitor
// in front of the gallery's normal gates (published, not expired, password),
// exactly like anyone else, so sharing can never grant access.

import { buildClientGalleryUrl } from './formatters'

const FACEBOOK_APP_ID = import.meta.env.VITE_FACEBOOK_APP_ID || ''

/**
 * Normalizes whatever URL we were given down to `origin + path`. Anything
 * after the path (a query string such as ?token=…, a hash) is dropped, so even
 * a caller that mistakenly passes a URL with a secret attached can't put it
 * into a social/email share payload. Returns '' for anything that isn't http(s).
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

/** The URL to share: the server's canonical `share_url`, else the path-based client URL. */
export function resolveShareUrl(shareUrl, username, slug) {
  return toCanonicalShareUrl(shareUrl || buildClientGalleryUrl(username, slug))
}

export function isMobileDevice() {
  if (typeof navigator === 'undefined') return false
  return /Android|iPhone|iPad|iPod/i.test(navigator.userAgent || '')
}

export function canNativeShare() {
  return typeof navigator !== 'undefined' && typeof navigator.share === 'function'
}

/** Every target URL, correctly encoded. `url` must already be canonical. */
export function buildShareTargets({ url, title }) {
  const encodedUrl = encodeURIComponent(url)
  const heading = title ? title.trim() : ''
  const text = heading ? `${heading} — view the gallery` : 'View this gallery'
  return {
    whatsapp: `https://wa.me/?text=${encodeURIComponent(`${text}: ${url}`)}`,
    facebook: `https://www.facebook.com/sharer/sharer.php?u=${encodedUrl}`,
    // Messenger: the app deep link works on phones; the web "send" dialog
    // needs a Facebook app id, so it's only available when one is configured.
    messengerApp: `fb-messenger://share/?link=${encodedUrl}`,
    messengerWeb: FACEBOOK_APP_ID
      ? `https://www.facebook.com/dialog/send?link=${encodedUrl}&app_id=${encodeURIComponent(FACEBOOK_APP_ID)}&redirect_uri=${encodedUrl}`
      : null,
    email: `mailto:?subject=${encodeURIComponent(heading || 'A gallery for you')}&body=${encodeURIComponent(`${text}:\n\n${url}`)}`,
    text,
  }
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
