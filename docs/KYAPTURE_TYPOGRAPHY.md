# KYAPTURE typography (chunk 6.2-A, backend)

Reference: `docs/pixieset-ref/settings/px-design-typography.png` (six named styles, no free font picker).

## What is stored

One key: `Gallery.design_settings["typography"]`, one of `sans | serif | modern | timeless | bold | subtle`.
It is the same key Collection Defaults already stores (`User.collection_defaults["design"]["typography"]`), and the same key the Design page already writes. No second font key, no `title_color`.

- Missing / null / legacy value -> app default `serif` (`DEFAULT_TYPOGRAPHY`), at render time. No migration.
- Writers (`PATCH /galleries/<slug>/` and `PATCH /auth/settings/`) accept only the six ids; anything else is a 400 and nothing is saved. `null` on a gallery removes the key (back to the app default).
- Other presentation keys use the same allowlists (`DESIGN_CHOICES`, `gridSpacing` 4-32 integer) in both places, from one function (`validate_presentation`).

## Style table (server constants, `backend/apps/core/typography.py`)

The id is looked up in this table. A stored value is never put into CSS; the public API returns the mapped values only (`typography_style`).

| id | Pixieset blurb | Family (self-host) | Licence | Weight / style | Letter-spacing / case | System fallback (after the family) |
|----|----------------|--------------------|---------|----------------|-----------------------|------------------------------------|
| sans | neutral | Inter | SIL OFL 1.1 | 400 / normal | 0 / none | system-ui, Segoe UI, Roboto, Helvetica Neue, Arial, sans-serif |
| serif | classic | Libre Baskerville | SIL OFL 1.1 | 400 / normal | 0 / none | Georgia, Times New Roman, Times, serif |
| modern | sophisticated | Jost | SIL OFL 1.1 | 400 / normal | 0.12em / uppercase | system sans stack |
| timeless | light and airy | Cormorant Garamond | SIL OFL 1.1 | 300 / italic | 0.02em / none | Georgia, Times New Roman, Times, serif |
| bold | punchy | Oswald | SIL OFL 1.1 | 600 / normal | 0.02em / uppercase | Impact, Arial Narrow Bold, system sans stack |
| subtle | minimal | Work Sans | SIL OFL 1.1 | 300 / normal | 0.05em / none | system sans stack |

Source for all six: Google Fonts catalogue (fonts.google.com/specimen/<Family+Name>; source repo github.com/google/fonts, each family folder has its `OFL.txt`).
The licences are recorded from the Google Fonts catalogue as known at writing; **6.2-B must open the `OFL.txt` that ships with each file it downloads and confirm it before committing the font** (also keep that file next to the font).
Font files were added in 6.2-B (below); licences were opened and checked there.

## Public payload (`GET /api/v1/public/<user>/<slug>/`)

- `design_settings`: an ALLOWLIST of presentation keys (`typography, colorPalette, layout, gridStyle, thumbSize, gridSpacing, coverPhoto`). Each value is re-validated on read; a stale or tampered value is dropped. `watermark`, `downloads`, `privacy` and every unknown key are never returned.
- `typography_style`: `{id, family_key, font_family, weight, font_style, letter_spacing, text_transform}` from the table above. `font_family` is a complete stack ending in system fonts, so the page is readable when the font file fails to load.

## Loading the fonts (for 6.2-B)

nginx CSP today (`frontend/nginx.conf`): `style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; font-src 'self' https://fonts.gstatic.com data:`.
Self-hosted woff2 files served from our origin work under `font-src 'self'` and `@font-face` in a built stylesheet works under `style-src 'self'`: no CSP change is needed, and no third party sees the client's IP.
Do not use `fonts.googleapis.com` for the six styles. (The app already loads Cormorant Garamond, Outfit and Plus Jakarta Sans from Google in `frontend/index.html`: see debt row 115.)
6.2-B maps `family_key` to a bundled `@font-face` and applies `font_family`, `weight`, `font_style`, `letter_spacing`, `text_transform` from the API; it must not build CSS from `design_settings.typography` itself.

## 6.2-B: Design tab, hero and self-hosted fonts

- `GET /api/v1/galleries/typography-styles/` (signed-in) returns `{default, styles[]}`: id, label, one-line description and the same mapping as the public payload. The Design page cards, the Live Preview, the dashboard Preview and the Collection Defaults names read it (cached for the session). The public payload is unchanged (no label or description).
- A style becomes five CSS variables (`--ky-font-family/-weight/-style/-letter-spacing/-text-transform`, `utils/typography.js`) set only on the title element, and `.ky-type` (styles/index.css) reads them. Each value is re-checked against a strict pattern before it is emitted; a stored id is never turned into CSS. Body, `:root` and dashboard UI never get the variables.
- Fonts: `frontend/src/assets/fonts/*.woff2` (20 Latin-subset files from the Fontsource packages; 6.2-C adds 5 Devanagari-only files, see below) declared in `frontend/src/styles/fonts.css` with `font-display: swap`; Vite emits them to `/assets/` (immutable cache). The six style files: Inter 400, Libre Baskerville 400, Jost 400, Cormorant Garamond 300 italic, Oswald 600, Work Sans 300. The other 14 keep the dashboard/landing look (Cormorant Garamond 300/400/500/600 + 400 italic, Outfit 300-600, Plus Jakarta Sans 400-800). A browser fetches a file only when text renders with it; nothing is preloaded.
- Licences: SIL OFL 1.1 text of every family in `frontend/public/font-licenses/OFL-<family>.txt`.
- nginx CSP unchanged (`font-src 'self'` covers `/assets/*.woff2`); verified in a browser with the CSP applied: all faces load, no request to fonts.googleapis.com / fonts.gstatic.com.
- Invalid or missing stored value: the Design page shows the app default (Serif) selected and its next save sends only valid values (`normalizeDesignSettings`).

## 6.2-C: Devanagari

A title such as "सारी र रवि" is drawn with a Devanagari family that matches the style, not a random system font.

- **Families (SIL OFL 1.1, from the Fontsource packages `@fontsource/noto-sans-devanagari` and `@fontsource/noto-serif-devanagari`, Devanagari subset, woff2, `font-display: swap`, served from our origin):** Noto Sans Devanagari for the sans styles, Noto Serif Devanagari for the serif styles.

  | style | Latin family | Devanagari family and weight |
  |-------|--------------|------------------------------|
  | sans | Inter 400 | Noto Sans Devanagari 400 |
  | modern | Jost 400 | Noto Sans Devanagari 400 |
  | bold | Oswald 600 | Noto Sans Devanagari 600 |
  | subtle | Work Sans 300 | Noto Sans Devanagari 300 |
  | serif | Libre Baskerville 400 | Noto Serif Devanagari 400 |
  | timeless | Cormorant Garamond 300 italic | Noto Serif Devanagari 300 (upright, see below) |

  Five files, 50-54 KB each, in `frontend/src/assets/fonts/noto-{sans,serif}-devanagari-devanagari-<weight>-normal.woff2`; licence texts in `frontend/public/font-licenses/OFL-noto-sans-devanagari.txt` and `OFL-noto-serif-devanagari.txt` (copied from the package `LICENSE`, "Copyright 2022 The Noto Project Authors").
- **Only when needed.** Each `@font-face` has `unicode-range: U+0900-097F, U+1CD0-1CF9, U+200C-200D, U+25CC, U+A8E0-A8FF` (`src/styles/fonts.css`). The family is only in the stacks of the six styles, after the Latin family, so a browser asks for a Devanagari file only when a title draws a character in that range. Latin-only titles request nothing extra. Currency and punctuation blocks are deliberately not in the range (a Latin title with a rupee sign does not fetch the file). A ZWJ/ZWNJ alone in a Latin title would fetch one file; accepted.
- **Stack (server table, still the single source).** `font_family` of each style is `"<Latin>", "<Noto … Devanagari>", [Impact, Arial Narrow Bold,] <system fallback>` (`apps/core/typography.py`). The frontend takes it from the API through the same strict pattern as before; the only frontend copy is the no-style fallback of `.ky-type` (`"Libre Baskerville", "Noto Serif Devanagari", Georgia, …`). No free-text font names.
- **Devanagari has no italic.** `timeless` is 300 italic, so the italic `@font-face` of Noto Serif Devanagari points at the upright file: the Latin letters are the real italic, the Devanagari letters are upright and are not artificially slanted.
- **Letter-spacing and line height.** Letter-spacing on Devanagari cuts the continuous headline (shirorekha) into dashes, and the vowel marks above and below the line need more room. `components/shared/TypeText.jsx` wraps each Devanagari run of a title in `<span class="ky-deva">` (`utils/scriptRuns.js`); `.ky-type .ky-deva` has `letter-spacing: 0` and `line-height: 1.6`, and a title that contains one gets `line-height: 1.6` on the whole title (`.ky-type:has(.ky-deva)`, so mixed lines stay even). The Latin letters keep the style's spacing. All five title places use it: client hero, sticky toolbar title, Preview modal (hero and section title), Design Live Preview.
- **No size jump.** `size-adjust` per Devanagari face, from the font files: height of "क" above the baseline / Latin cap height is Inter .85, Jost .89, Oswald 600 .77, Work Sans 300 .94, Libre Baskerville .81, Cormorant Garamond 300 1.00. With sans 400 at 108%, sans 600 at 115%, serif 400 at 115% and the 300 faces at 100% the ratio is .89-1.00. The other metrics are untouched; line height is a multiple of the font size, so baselines are shared.
- **Toolbar fix found in this chunk's QA.** `.ky-type { text-wrap: balance }` reset the nowrap of the Tailwind `truncate` class on the toolbar title, so a long title wrapped to three lines at 390 px instead of ending in an ellipsis. `.ky-type.truncate { text-wrap: nowrap }` restores the one-line toolbar.
- **Tests.** Backend (`test_typography_settings.py`): every style's stack has the right Devanagari family exactly once, after the Latin family and before the system fonts, in the catalog and the public payload. Frontend (`npm test`): `scriptRuns.test.js` (run splitting), `styles/fonts.test.js` (exactly the six faces, each woff2 present, `swap`, Devanagari-only `unicode-range`, Latin faces untouched, licences present, `.ky-type` fallback). Browser: see the numbers below.

### 6.2-C browser QA (docker nginx build on :3000, real API, own QA gallery, deleted by exact id afterwards)

Hero title of the client gallery, six styles x titles (Latin, "सारी र रवि", "Sari र रवि Wedding 2026", a long Devanagari title of about 70 characters, a long Latin title of about 100 characters) x desktop 1280 and 390 px = 60 runs, each in a fresh browser context (cold cache):

- Latin-only titles (24 runs): **0** Devanagari font requests; only the style's own Latin file plus the four UI fonts the gallery already loaded (row 121).
- Devanagari, mixed and long Devanagari titles (36 runs): **exactly 1** Devanagari request each, the right one for the style (sans, modern, bold, subtle: `noto-sans-devanagari`, weights 400, 400, 600, 300; serif, timeless: `noto-serif-devanagari`, weights 400, 300). No request to fonts.googleapis.com / fonts.gstatic.com.
- Chrome's platform font report for the hero: the Devanagari glyphs are drawn by Noto Sans/Serif Devanagari of the right weight, the Latin glyphs by the style's Latin family.
- Devanagari run letter-spacing is `normal` (headline unbroken) while the Latin letters keep the style's spacing (e.g. modern 8.64 px at 1280, 4.32 px at 390). Line height of a title with Devanagari is 1.6 (115.2 px at 72 px, 57.6 px at 36 px). The Devanagari run boxes sit 2-16 px inside the title box (the line is taller than the marks), no ancestor with `overflow` cuts the title, no horizontal scroll at 390 (`scrollWidth` = viewport).
- Sticky toolbar title (`truncate`): one line with an ellipsis for the long Devanagari and the long Latin title at 390 (before the `.ky-type.truncate` fix the long title took three lines, 115 px); top marks visible.
- Design tab Live Preview and the dashboard Preview modal with a mixed title in Bold: Devanagari in Noto Sans Devanagari 600, no horizontal scroll at 1280 and 390 (the extra fetches seen in the Design tab are debt row 127).
- Not done: Free/Pro and blocked-font variants (not touched by this chunk, covered in 6.2-B).

