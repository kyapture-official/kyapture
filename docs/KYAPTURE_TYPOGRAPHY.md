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
No font files were added in 6.2-A.

## Public payload (`GET /api/v1/public/<user>/<slug>/`)

- `design_settings`: an ALLOWLIST of presentation keys (`typography, colorPalette, layout, gridStyle, thumbSize, gridSpacing, coverPhoto`). Each value is re-validated on read; a stale or tampered value is dropped. `watermark`, `downloads`, `privacy` and every unknown key are never returned.
- `typography_style`: `{id, family_key, font_family, weight, font_style, letter_spacing, text_transform}` from the table above. `font_family` is a complete stack ending in system fonts, so the page is readable when the font file fails to load.

## Loading the fonts (for 6.2-B)

nginx CSP today (`frontend/nginx.conf`): `style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; font-src 'self' https://fonts.gstatic.com data:`.
Self-hosted woff2 files served from our origin work under `font-src 'self'` and `@font-face` in a built stylesheet works under `style-src 'self'`: no CSP change is needed, and no third party sees the client's IP.
Do not use `fonts.googleapis.com` for the six styles. (The app already loads Cormorant Garamond, Outfit and Plus Jakarta Sans from Google in `frontend/index.html`: see debt row 115.)
6.2-B maps `family_key` to a bundled `@font-face` and applies `font_family`, `weight`, `font_style`, `letter_spacing`, `text_transform` from the API; it must not build CSS from `design_settings.typography` itself.
