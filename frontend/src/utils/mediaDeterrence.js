// File Location: frontend/src/utils/mediaDeterrence.js
//
// 7-D: casual-save deterrence for the PUBLIC client gallery's photo and video
// tiles, the lightbox and the slideshow. It is deterrence, not protection: it
// stops the right-click menu and drag-to-desktop on the media itself, and
// nothing more. A visitor can still take a screenshot, read the network tab or
// use the Download button a photographer allows. It is not "protected", "secure"
// or "capture-proof", so the UI must never say it is.
//
// Scope is decided by where the markers are put (`data-ky-media-guard` on a
// tile or the lightbox stage, class `ky-media-guard` on the <img>/<video>), so
// the photographer's dashboard, forms, titles, captions, inputs, links and the
// download pages are untouched. The handler below is the second line: even
// inside a marked region it never cancels an event that started on a control,
// a link or a text field, so the keyboard "context menu" key on a focused
// button, and any input, keep the browser's own behaviour.

export const MEDIA_GUARD_ATTR = 'data-ky-media-guard'
export const MEDIA_GUARD_CLASS = 'ky-media-guard'

// Anything a visitor can click, focus or type into. Right-click / drag on these
// is never ours to cancel.
const FREE_SELECTOR = [
  'a[href]',
  'button',
  'input',
  'textarea',
  'select',
  'label',
  'summary',
  '[contenteditable=""]',
  '[contenteditable="true"]',
  '[role="button"]',
  '[role="link"]',
  '[role="textbox"]',
  '[role="menuitem"]',
  '[role="slider"]',
].join(',')

/**
 * True when a contextmenu / dragstart that started on `target` is on guarded
 * media: inside a marked region, and not on a control, link or text field.
 */
export function shouldGuardMediaEvent(target) {
  if (!target || typeof target.closest !== 'function') return false
  if (target.closest(FREE_SELECTOR)) return false
  return Boolean(target.closest(`[${MEDIA_GUARD_ATTR}]`))
}

/** onContextMenu / onDragStart handler for a marked media region. */
export function guardMediaEvent(event) {
  if (shouldGuardMediaEvent(event?.target)) event.preventDefault()
}
