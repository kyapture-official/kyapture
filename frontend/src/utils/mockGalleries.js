// ─────────────────────────────────────────────────────────────────────────────
// OFFLINE-SAFE, PERCENT-ENCODED SVG COVER PLACEHOLDERS
//
// WHY Percent-Encoded:
//   According to RFC 3986, characters like '<', '>', and '#' are reserved/excluded
//   and must be percent-encoded (%3C, %3E, %23) inside URL schemes [18].
//   Failing to encode these will cause silent rendering failures on iOS WKWebView
//   and Android WebView.
// ─────────────────────────────────────────────────────────────────────────────

// Dark, neutral cover — matches the '#1a1a1a' branding of the wedding gallery.
// Camera shape: outer body (rect) + lens (circle) + viewfinder bump (rect).
const COVER_DARK = [
  "data:image/svg+xml,",
  "%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 800 530'%3E",
  "%3Crect width='800' height='530' fill='%231a1a1a'/%3E",
  // Camera body
  "%3Crect x='320' y='192' width='160' height='124' rx='10'",
  " fill='none' stroke='%23ffffff' stroke-width='2' opacity='0.2'/%3E",
  // Lens ring
  "%3Ccircle cx='400' cy='254' r='38'",
  " fill='none' stroke='%23ffffff' stroke-width='2' opacity='0.2'/%3E",
  // Viewfinder bump
  "%3Crect x='354' y='178' width='58' height='18' rx='5'",
  " fill='none' stroke='%23ffffff' stroke-width='1.5' opacity='0.15'/%3E",
  "%3C/svg%3E",
].join('')

// Warm amber cover — complements the '#e5c158' branding of the portrait gallery.
const COVER_WARM = [
  "data:image/svg+xml,",
  "%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 800 530'%3E",
  "%3Crect width='800' height='530' fill='%238a6d1a'/%3E",
  // Camera body
  "%3Crect x='320' y='192' width='160' height='124' rx='10'",
  " fill='none' stroke='%23ffffff' stroke-width='2' opacity='0.3'/%3E",
  // Lens ring
  "%3Ccircle cx='400' cy='254' r='38'",
  " fill='none' stroke='%23ffffff' stroke-width='2' opacity='0.3'/%3E",
  // Viewfinder bump
  "%3Crect x='354' y='178' width='58' height='18' rx='5'",
  " fill='none' stroke='%23ffffff' stroke-width='1.5' opacity='0.25'/%3E",
  "%3C/svg%3E",
].join('')

// ─────────────────────────────────────────────────────────────────────────────
// SEED DATA
// ─────────────────────────────────────────────────────────────────────────────
const _mockGalleries = [
  {
    id:              'f47ac10b-58cc-4372-a567-0e02b2c3d479',
    title:           'Aria & David Wedding',
    slug:            'aria-david-wedding',
    branding_color:  '#1a1a1a',
    is_downloadable: true,
    is_active:       true,
    is_published:    true,
    has_password:    true,
    cover_url:       COVER_DARK,
    photo_count:     142,
    created_at:      '2026-05-15T08:30:00.000Z',
    updated_at:      '2026-06-01T14:22:18.000Z',
  },
  {
    id:              'b78a9c2d-12ef-45ab-bcde-9fabcde12345',
    title:           'Mila Portrait Session',
    slug:            'mila-portraits',
    branding_color:  '#e5c158',
    is_downloadable: false,
    is_active:       true,
    is_published:    false,
    has_password:    false,
    cover_url:       COVER_WARM,
    photo_count:     38,
    created_at:      '2026-06-02T11:15:00.000Z',
    updated_at:      '2026-06-03T09:45:12.000Z',
  },
  {
    id:              '9efabcd1-2345-6789-abcd-ef0123456789',
    title:           'Himalayan Landscapes',
    slug:            'himalayan-landscapes',
    branding_color:  '#2563eb',
    is_downloadable: true,
    is_active:       true,
    is_published:    true,
    has_password:    false,
    cover_url:       null, // Deliberate null — tests the empty-cover fallback render path
    photo_count:     89,
    created_at:      '2026-04-10T06:00:00.000Z',
    updated_at:      '2026-04-12T18:20:00.000Z',
  },
]

/**
 * WHAT: Recursive Deep Freeze Utility
 * WHY:  Recursively freezes an object and all its nested properties [20].
 *       The Object.isFrozen check short-circuits traversal on pre-frozen
 *       objects (like shared elements), optimizing execution and preventing call-stack overflows [20].
 */
function deepFreeze(obj) {
  if (Object.isFrozen(obj)) return obj
  for (const key of Object.getOwnPropertyNames(obj)) {
    const value = obj[key]
    if (value !== null && typeof value === 'object') {
      deepFreeze(value)
    }
  }
  return Object.freeze(obj)
}

// Export as a completely immutable, deeply frozen database seed
export const mockGalleries = deepFreeze(_mockGalleries.map((g) => ({ ...g })))