# KYAPTURE — Execution State

_Last updated: Phase 3 completion (this session). See the "Phase 3" section
near the end of this file for the current status; sections above it are
historical record from Phases 0–2 and the post-Phase-2 hotfix, kept as-is._

## Status: Phase 1 — Core Gallery Correctness — COMPLETE

Phase 0 (production config, docker-compose/settings consistency, password
reset, nginx SPA fallback) was completed and re-verified in prior sessions
— see `KYAPTURE_PHASE0_STATUS.md`. Not repeated here.

---

## Phase 1 tasks completed

All 8 items from the Phase 1 instruction were implemented in one pass:

1. **Gallery update / design settings (F-01, F-13)**
   - Added `Gallery.design_settings` (`JSONField(default=dict, blank=True)`).
   - Migration `galleries/migrations/0005_gallery_design_settings.py`.
   - Added `design_settings` to `GalleryDetailSerializer.Meta.fields` (it was
     already referenced-but-missing in `GalleryUpdateSerializer`, which is
     what caused every PATCH/PUT to crash).
   - Removed the slug-regeneration-on-title-change logic from
     `GalleryUpdateSerializer.update()` — a title edit now only ever
     touches `title`, never `slug`. Slugs are now permanently stable once
     assigned at creation.
   - Added a `design_settings.coverPhoto` → `Gallery.cover_photo` FK sync
     inside `update()`, validated the same way the explicit `cover_photo`
     field already is (must belong to the same gallery) — this makes the
     Design page's existing cover-photo picker double as the "single
     source of truth" for the gallery's cover, feeding both the dashboard
     listing and the public hero.
   - Regression tests: `backend/apps/galleries/tests/test_gallery_update.py`
     (10 tests — title/slug stability, full supported-field round trip,
     design_settings round trip, cover sync + cross-tenant rejection, PUT,
     tenant isolation, sanitization). All passing.

2. **Upload reliability**
   - `photosApi.uploadBulk()` now passes `timeout: 0` (no axios-side
     timeout) instead of inheriting the shared 15s default meant for
     ordinary JSON calls. The caller's `AbortController` `signal` is
     untouched — cancellation still works exactly as before.
   - No changes to the upload pipeline itself, no direct-to-S3 work (per
     scope).

3. **Canonical gallery URL**
   - `formatters.js`'s `buildClientGalleryUrl()` no longer builds a
     `username.domain.tld` subdomain URL in production. It now always
     returns `${window.location.origin}/g/:username/:slug`, matching the
     locked MVP decision and the app's actual router (path-based only).
   - Audited all other URL-builder call sites: `TopNavBar.jsx` and
     `GalleriesPage.jsx` already built path-based URLs correctly and
     needed no changes. `PhotoCard.jsx`, `StickyGalleryHeader.jsx`, and
     `GalleryCard.jsx` all consume the shared `buildClientGalleryUrl()`
     function, so they're fixed automatically.
   - Because slugs are now stable (item 1) and were already stable at the
     URL-builder level, a title change preserves the public URL end to end.

4. **Client gallery error handling (F-10, F-10b)**
   - `ClientGalleryPage.jsx`: `fetchGallery`'s catch block now reads
     `err.status` (the field `clientsApi.js`'s `normalizeError()` actually
     sets on its thrown `Error` objects) instead of the always-undefined
     `err.response?.status`. 404 → not-found state; 401 → password gate
     with the stale token cleared. `handleUnlock`'s catch block now uses
     `err.message` instead of dead `err.response?.data?...` paths.
   - `axiosInstance.js`: the 401 response interceptor now skips the
     refresh-then-logout branch entirely for any request whose URL
     contains `/public/` — a guest's 401 (bad/missing unlock token) can
     never again trigger a photographer's session refresh or logout in a
     shared browser/tab. Public error handling stays entirely in
     `clientsApi.js`/`ClientGalleryPage.jsx`, as intended.
   - "Download Full Gallery" / "Download Selected" now only renders when
     `allow_download` is true in the payload (F-12) — previously always
     rendered regardless of the photographer's setting.
   - Expired/unpublished/deactivated galleries were already
     indistinguishable from nonexistent ones at the API layer by design
     (avoids enumeration) — confirmed by test, no server change needed;
     the frontend fix above is what makes that already-correct 404
     actually reach the not-found UI state.

5. **Public gallery payload (F-11)**
   - `PublicGallerySerializer` now includes `cover_url` (same
     `cover_photo`-FK-driven source of truth as the dashboard side) and
     `event_date`. `allow_download`, `watermark_enabled`, and
     `is_password_protected` were already present.
   - `PublicGalleryView.get_gallery()`'s `assets` prefetch is now scoped
     to `processing_status=READY` only — a guest never sees a broken
     thumbnail for a still-processing or failed asset. Dashboard-side
     (photographer) views are unaffected.
   - No pagination work done (explicitly deferred to the performance
     phase per instructions).

6. **Cover behavior**
   - New `_auto_assign_cover_if_missing()` helper in `photos/tasks.py`,
     called from both `process_photo_asset` and `process_video_asset`
     right after each transitions to `READY`. Uses a single conditional
     `.filter(cover_photo__isnull=True).update(cover_photo_id=asset.id)` —
     translates to one atomic SQL `UPDATE ... WHERE cover_photo_id IS
     NULL`, so it's race-safe when several assets in a batch finish
     processing concurrently. Never raises into the processing task itself
     (wrapped and logged).
   - Manual "Set as cover" flow (`PhotoGrid.jsx`'s button +
     `GalleryPhotosPage.jsx`'s `handleSetCover`) was already fully built
     on the frontend and was blocked purely by the F-01 backend crash —
     now works with no frontend changes needed.
   - Fixed `HomePage.jsx`'s dashboard gallery cards: they were reading
     `gallery.cover_photo.thumbnail || gallery.cover_photo.image` (a
     nested-object shape the API never sends) instead of the actual flat
     `gallery.cover_url` string the backend returns — covers never
     rendered on the dashboard home page against real data. Now fixed.
     (`GalleriesPage.jsx` and `GalleryCard.jsx` already used `cover_url`
     correctly and needed no change.)
   - Client-facing hero (`ClientGalleryPage.jsx`) now prefers the new
     `cover_url` field (item 5) over guessing photo-level field names that
     `PublicMediaAssetSerializer` never actually sends.

7. **Fake / non-functional UI**
   - `TopNavBar.jsx`: `handleDelete()` now actually calls
     `galleriesApi.deleteGallery(id)` (which already existed and worked)
     instead of faking a success toast and navigating away with nothing
     deleted server-side. Removed the "Share by email", "Get QR code",
     "View email history", "Manage presets", "Move to...", and
     "Duplicate" menu items entirely — none had any backend, all were
     toast-only "coming soon" no-ops. "Get direct link" and "Preview" stay
     (both fully functional); Publish/Draft toggle was already real.
   - `GallerySettingsPage.jsx`: removed the "Favorites" and "Store" tabs
     entirely (no backend support; Favorites is explicitly out of scope
     for this phase, Store/print-sales was never a locked MVP feature).
     Removed the fake "Custom URL" input (there is no vanity-URL feature —
     the field defaulted to the literal string `"davilandd"` and was
     silently dropped by the backend), the fake "Category Tags" input, and
     the fake "Download PIN" toggle+input — all three were sent to
     `updateGallery()` but had no corresponding model/serializer field and
     were silently discarded. The General tab now shows a **read-only**
     canonical gallery link (`/g/:username/:slug`) instead, with a note
     that it never changes. Every remaining control (title, event date,
     expiry, watermark, password protection, allow-downloads) is real and
     round-trips through the backend.
   - `PixiesetContext.jsx`'s `updateDesign`/`updateSettings` reducer
     actions were checked and confirmed unused/vestigial (nothing calls
     them) — left as-is, no fake surface reachable through them.

8. **Title/text sanitization (F-15)**
   - `sanitize_text()` in `core/utils.py` now applies `html.unescape()`
     after `bleach.clean(text, tags=[], strip=True)`. Tags are still fully
     stripped (XSS protection unchanged); the entity-escaping bleach
     applies to surviving plain-text characters (`&` → `&amp;`, `"` →
     `&quot;`, etc.) is undone, so normal titles with ampersands, quotes,
     and emoji round-trip correctly. Verified safe: no
     `dangerouslySetInnerHTML` exists anywhere in the frontend (grepped),
     so nothing renders this text as HTML — unescaping cannot re-introduce
     a live tag, only inert visible text. Covered by two new regression
     tests (normal-character round trip, script-tag stripping).

---

## Files changed

**Backend:**
- `backend/apps/galleries/models.py` — `design_settings` field.
- `backend/apps/galleries/migrations/0005_gallery_design_settings.py` — new.
- `backend/apps/galleries/serializers.py` — `design_settings` in
  `GalleryDetailSerializer`; slug-stability fix + cover-photo sync in
  `GalleryUpdateSerializer.update()`.
- `backend/apps/core/utils.py` — `sanitize_text()` fix.
- `backend/apps/clients/serializers.py` — `PublicGallerySerializer` gains
  `cover_url`, `event_date`.
- `backend/apps/clients/views.py` — `assets` prefetch scoped to READY.
- `backend/apps/photos/tasks.py` — `_auto_assign_cover_if_missing()` hook.
- `backend/apps/galleries/tests/test_gallery_update.py` — new (10 tests).
- `backend/apps/clients/tests/test_public_gallery.py` — new (9 tests).

**Frontend:**
- `frontend/src/utils/formatters.js` — `buildClientGalleryUrl()` path-based.
- `frontend/src/api/photosApi.js` — upload timeout override.
- `frontend/src/api/axiosInstance.js` — `/public/` 401 isolation.
- `frontend/src/pages/client/ClientGalleryPage.jsx` — error handling,
  cover_url, download-button gating.
- `frontend/src/pages/dashboard/HomePage.jsx` — cover image fix.
- `frontend/src/components/layout/TopNavBar.jsx` — real delete, removed
  fake menu items.
- `frontend/src/pages/dashboard/GallerySettingsPage.jsx` — removed fake
  tabs/fields, read-only canonical URL.

## Migrations added

- `galleries.0005_gallery_design_settings` — adds `Gallery.design_settings`.
  Applied cleanly against a real Postgres instance; `makemigrations
  --check --dry-run` confirms zero further model drift.

## Tests / checks passed

Run against a real (embedded) PostgreSQL instance, both `development` and
`production` Django settings, via the established `pgserver` +
`uv`-managed venv toolchain from Phase 0:

- `manage.py check --settings=development` — **PASS**
- `manage.py check --settings=production` — **PASS**
- `manage.py makemigrations --check --dry-run` — **PASS** (no drift)
- `apps.galleries` test suite — **15/15 pass** (5 pre-existing gating
  tests + 10 new `test_gallery_update.py` tests), *except* the one
  pre-existing S3-dependent failure noted below.
- `apps.clients` test suite (new `test_public_gallery.py`) — **9/9 pass**
  (public payload contents, READY-only photo filtering, 404 for
  nonexistent/unpublished galleries, password gate, 401 on bad token,
  useful wrong-password error, auto-cover-assign incl. non-override case).
- Full backend suite (`manage.py test`) — **36/41 pass** (3 pre-existing
  errors + 2 pre-existing failures, all one root cause — see below).
- Frontend production build (`npm run build`) — **PASS**, clean, only a
  pre-existing "chunk >500kB" advisory (unrelated to Phase 1, not a
  build error).
- No frontend test framework/files exist in this repo — nothing to run.

## Failures (pre-existing, unrelated to Phase 1 — verified, not assumed)

Five tests fail, all for the **same single root cause**: this sandboxed
verification environment has no working S3 (fake `AWS_ACCESS_KEY_ID`/
`AWS_SECRET_ACCESS_KEY`, no moto/mocked bucket), and these five tests are
the only ones in the suite that create a `MediaAsset` from a *real*
uploaded file (`SimpleUploadedFile`), which makes Django's `FileField`
call `storage.save()`/`storage.exists()` → a real `botocore` call → `403
Forbidden` on `HeadObject`. Confirmed by direct inspection of each
traceback (all end in the identical `botocore.exceptions.ClientError: ...
HeadObject ... Forbidden`), and confirmed that none of the code paths
involved (`PhotoListUploadView.post()`, storage backend config,
`MediaAssetImageUploadSerializer`) were touched by any Phase 1 change:

- `apps.galleries.tests.test_gating.SaaSResourceGatingTestCase.test_photo_upload_count_gating`
  — pre-existing (`test_gating.py` untouched this phase).
- `apps.photos.tests.test_async_uploads.PhotoAsyncUploadTestCase.test_non_blocking_upload_returns_202_and_dispatches_task`
  — pre-existing, already documented as out-of-scope in Phase 0 status.
- `apps.photos.tests.test_bulk_actions.PhotoBulkActionsTestCase.test_reorder_assets_sequentially`
- `apps.photos.tests.test_bulk_actions.PhotoBulkActionsTestCase.test_bulk_delete_assets_successfully`
- `apps.photos.tests.test_bulk_actions.PhotoBulkActionsTestCase.test_bulk_delete_ignores_foreign_assets_silently`

Per the Phase 1 instructions ("if unrelated, leave it documented rather
than changing unrelated media behavior") these were left as-is. My own
new tests (`test_gallery_update.py`, `test_public_gallery.py`) sidestep
this entirely by constructing `MediaAsset` fixtures with a plain string
`original_file` path rather than a real uploaded file — correct Django
practice for tests that don't need to exercise the storage/upload
pipeline, and it keeps them passing independent of the environment's S3
configuration.

## Remaining work / explicitly out of scope for Phase 1

Per the instructions, none of the following were started:
- Photo sets, favorites, slideshow
- CDN migration, responsive image pipeline, video transcoding
- Large-gallery pagination/optimization
- Broad UI redesign
- Card payments (Stripe)
- Wildcard subdomain gallery infrastructure

Also not yet done (belongs to a later phase, not blocking):
- Free-tier limits are now enforced as the locked 3 GB storage maximum and
  10-gallery maximum.
- The pre-existing S3-test-environment limitation above is a
  verification-environment gap, not a Phase 1 code defect; a real AWS/S3
  (or moto-mocked) credential set would need to be wired into whichever
  CI environment eventually runs this suite for real.

## Exact next phase

Per the verified execution plan's ordering, the next unblocked phase is
**media/performance**: CDN delivery, responsive image pipeline for
large-gallery performance, and the large-gallery pagination work
explicitly deferred from Phase 1 item 5. Photo sets, favorites, and
slideshow (explicitly excluded here) are the phase after that, once
core delivery performance is solid.

---

# PHASE 2 — MEDIA DELIVERY + VIDEO + LARGE-GALLERY PERFORMANCE

Status: **COMPLETE** (backend + frontend + tests + production-parity
review). Docker build/compose itself could not be run in this sandbox —
see "Docker status" below; every other validation item ran for real.

## A. Image pipeline

- `apps/core/utils.py::process_image_pipeline()` rewritten. Source image
  is read once, EXIF-orientation-corrected (`exif_transpose`), and
  color-normalized to sRGB (`_normalize_to_srgb()` — converts via any
  embedded ICC profile with `PIL.ImageCms.profileToProfile`, falls back
  to plain RGB conversion on any failure/missing profile). Three WebP
  derivatives are generated from that single normalized image: **display**
  (2048px, q82), **medium** (1280px, q80 — new tier, fills the gap
  between a 640px thumbnail and a full 2048px lightbox image for
  ordinary in-page grid widths), **thumbnail** (640px, q75). Evaluated
  against the 640/1280/2048 MVP set from the instructions — no fourth
  tier, no AVIF; no demonstrated MVP need for either.
- `strip_exif_gps()` rewritten to use the real `piexif` API correctly
  (previous code silently never worked — see "Real bugs found and
  fixed" below) — removes only the GPS IFD, leaves all other EXIF and
  pixel data byte-identical, and is a no-op (returns the original file
  object untouched) when there's no GPS tag to strip. This runs on the
  **original** file before it's stored — the original itself is never
  re-encoded or recompressed, only its GPS tag is zeroed when present.
- BlurHash generation fixed (see "Real bugs found and fixed") — every
  image now gets a real, image-specific blurhash instead of one
  hardcoded placeholder string.
- Idempotency/no-orphans: derivative keys are deterministic
  (`get_display_photo_path()` / `get_medium_photo_path()` /
  `get_thumbnail_photo_path()` in `apps/photos/models.py`, all keyed off
  the asset's UUID), and `PublicMediaStorage` overwrites on retry
  (`file_overwrite=True` in S3 / `allow_overwrite=True` on local disk) —
  a Celery retry regenerates the same key, never accumulates a second
  file.
- Responsive delivery: `srcset`/`sizes` added to the public masonry grid
  (`PublicMasonryGrid.jsx`) and the lightbox full-view image
  (`PhotoLightbox.jsx`) — see item D below for exact wiring.
- Validated with real synthetic JPEGs (built via PIL+piexif in the new
  test file) covering GPS-present/absent, and derivative-tier bounds —
  see `apps/photos/tests/test_image_pipeline.py` (9/9 passing).

## B. Video pipeline

Audited first (per instructions) — found the pipeline was NOT deferred
work; it existed but had two real bugs (see below) and generated an
unused derivative. Rewritten:

- `process_video_pipeline()` now streams the original into a temp file
  via **chunked reads** (`video_file.chunks()`), never a single
  `.read()` that would materialize a multi-GB upload in worker RAM.
- Poster frame: extracted at a **safe timestamp** —
  `min(2.0, duration/2)`, capped at 0 for a zero-length input — instead
  of a hardcoded `-ss 00:00:02`, which silently produced zero output on
  any video under 2 seconds (reproduced and fixed — see below). Poster
  is written as a genuine `.jpg` with `image/jpeg` content type (fixes
  the poster extension/content-type mismatch called out in the
  instructions — the field's upload_to function previously returned a
  `.webp` path for a JPEG file).
- Exactly **one** browser-compatible derivative is generated: H.264
  (`yuv420p`)/AAC MP4, `scale='-2:min(1080,ih)'` (scale-down only, never
  upscales — verified against 360p/1080p-portrait/4K sources), faststart
  (`-movflags +faststart`) for progressive playback before full
  download. The old 3-second silent WebM hover-preview derivative is
  removed — confirmed dead code (no frontend view ever read
  `preview_url`/`preview_file`), so generating it was pure wasted
  FFmpeg time and wasted storage, exactly what the instructions rule
  out ("do not generate unnecessary video variants"). No HLS/DASH — not
  demonstrated necessary for this product's scale.
- Original video keeps `PrivateMediaStorage`; only the poster and the
  new `playback_file` derivative are public. `PublicVideoStreamView`
  now prefers `playback_file` (falling back to `original_file` only if
  a playback derivative doesn't exist yet, e.g. mid-migration).
- Retry/idempotency: same pattern as images — deterministic derivative
  keys (`get_video_poster_path()`, new `get_video_playback_path()`),
  `max_retries=3` unchanged, `PublicMediaStorage` overwrite-on-retry.
- Processing state exposed via the existing `processing_status` field
  (`pending`/`processing`/`ready`/`failed`) — now consumed efficiently
  by the frontend's batched polling (item D).
- Validated with real FFmpeg-generated synthetic videos: small MP4,
  MOV container, video-without-audio, and the specific short-video
  (<2s) regression case — see
  `apps/photos/tests/test_video_pipeline.py` (9/9 passing).

## C. Storage + CDN

- `apps/core/storage.py` (new): `PrivateMediaStorage` (originals —
  private ACL, signed URLs, 1hr expiry, `file_overwrite=False`) and
  `PublicMediaStorage` (every derivative — public-read, no query-string
  signing so URLs never change, `file_overwrite=True`,
  `Cache-Control: public, max-age=31536000, immutable` baked into S3
  object metadata at write time). Falls back to local `FileSystemStorage`
  (with `allow_overwrite=True`) when no AWS credentials are configured
  (local dev).
- Wired onto every relevant `MediaAsset` field in `apps/photos/models.py`
  (`original_file` → private; `display_file`/`medium_file`/
  `thumbnail_file`/`poster_image`/`playback_file` → public).
- Collision-preventing, deterministic storage paths already existed
  (UUID-keyed `get_*_path()` functions) — reused, not reinvented.
- Deletion cleanup: `apps/photos/signals.py` extended with purge blocks
  for the new `medium_file` and `playback_file` fields (mirrors the
  existing pattern for the other derivative fields).

## D. Large gallery performance

- **Public gallery payload no longer embeds every asset.**
  `PublicGalleryView.get_ready_assets_page()` fetches exactly one
  bounded page (`GalleryMediaPagination.page_size` = 60) plus a total
  count — two small indexed queries, regardless of gallery size — and
  the old unbounded `Prefetch('assets', ...)` is removed.
  `PublicGallerySerializer` gained `photos_count`/`photos_has_more`/
  `photos_page_size` fields so the client knows whether to fetch more.
- **New continuation endpoint**: `PublicGalleryPhotosView` (`GET
  /api/v1/public/{username}/{slug}/photos/?page=N`) — standard DRF
  `{count, next, previous, results}` pagination, same password/session
  gate as the main gallery endpoint.
- **Frontend consumes both**: `ClientGalleryPage.jsx` tracks
  `photosHasMore`/a page cursor and renders a "Load More" button that
  calls the new `clientsApi.getGalleryPhotos()`, appending results to
  the existing `photos` array in place (no full re-fetch, no lost
  scroll position/selection).
- **Polling storm removed.** The dashboard's
  `GalleryPhotosPage.jsx` previously fired one `GET
  /photos/photo/{id}/` request *per pending asset* every 3 seconds
  (`Promise.allSettled(pendingAssets.map(...))`) — a gallery mid-upload
  with hundreds of pending videos meant hundreds of parallel requests
  every tick. Replaced with:
  - New backend endpoint `PhotoBatchStatusView` (`GET
    /api/v1/photos/{gallery_slug}/status/?ids=id1,id2,...`, capped at
    200 ids) — one query, one response, for every pending asset at once.
  - Frontend polling loop rewritten from a fixed-cadence `setInterval`
    to a self-rescheduling backoff loop: starts at 3s, doubles on every
    tick that finds nothing new (capped at 15s), and resets to 3s the
    moment a new upload batch adds pending assets or any asset actually
    finishes processing. Same `MAX_POLL_ATTEMPTS` ceiling as before.
- **N+1 avoided**: `gallery.photographer` is `select_related()` once at
  the gallery lookup and reused for every video's `playback_url` build
  in the child serializer, rather than re-querying per video.
- **Dashboard gallery-manager pagination deliberately NOT added** —
  investigated and scoped out: `PhotoReorderView` (drag-and-drop reorder)
  requires the frontend to hold and resubmit the **full** ordered ID
  list for the gallery (`photosApi.reorderPhotos()`'s own documented
  contract: "Always pass every photo currently in the gallery").
  Paginating the dashboard list would silently break reordering past
  page 1. This is a deliberate, documented scope decision per project
  principle #2 (preserve working functionality) — not an oversight. The
  photographer-side view is not the "client gallery" the instructions'
  100/500/1000/2000+ requirement targets (confirmed against this
  codebase's own vocabulary: "client gallery" = the public guest-facing
  view, `apps/clients` + `ClientGalleryPage.jsx`).
- No virtualization added — pagination + lazy loading (existing
  `react-intersection-observer` `LazyPhoto` component, unchanged) is
  sufficient at the page sizes now in play; no real DOM/memory problem
  was demonstrated that would justify it.

## E. Design settings — client application

Investigated and confirmed the gap the instructions describe: Phase 1
persisted `Gallery.design_settings`, but nothing on the public side ever
read it — `ClientGalleryPage.jsx` had hardcoded `font-serif` typography
and no color/grid variation, and `PublicGallerySerializer` didn't even
expose the field. Fixed:

- `PublicGallerySerializer` now includes `design_settings` in its output
  fields (the same JSON the photographer's Design page already saves).
- New shared module `frontend/src/utils/designSettings.js` — the exact
  same `LAYOUT_CLASSES`/`TYPOGRAPHY_CLASSES`/`COLOR_THEMES` option maps
  the Design page's live preview (`CoverPreview.jsx`) already used,
  extracted so both sides of the product agree on what a given design
  choice looks like. `CoverPreview.jsx` refactored to import from it
  (previously a private local copy) instead of duplicating it.
- `ClientGalleryPage.jsx` now reads `data.design_settings`, resolves it
  via `resolveDesignSettings()` (safe per-field fallback to the same
  defaults `GalleryDesignPage.jsx` itself falls back to), and applies:
  typography to the hero title and grid section heading; the color
  theme's background/text/accent to the page background and grid
  section heading/divider; grid style/thumbnail size/spacing to
  `PublicMasonryGrid.jsx` (new `gridStyle`/`thumbSize`/`gridSpacing`
  props — "vertical" keeps the original CSS-column masonry with each
  photo's natural aspect ratio, "horizontal" switches to a uniform CSS
  grid of fixed-aspect tiles; "large" thumbnails means fewer/bigger
  columns at every breakpoint; `gridSpacing` drives the grid gap
  directly). Cover-photo selection was already wired correctly in
  Phase 1 (`cover_photo` FK kept in sync by `GalleryUpdateSerializer`)
  — confirmed, not touched.
- Scope kept deliberately small per the instructions: the same six
  typography options, nine color themes, two grid styles, two thumbnail
  sizes, one spacing slider the Design page already exposes — no theme
  builder, no custom CSS editor, no plugin system.

## F. Production parity

Reviewed for real (not assumed from local dev success):

- `backend/Dockerfile`: `ffmpeg` is installed as a system dependency
  (was already present) — confirmed both `blurhash` and `piexif` (the
  two packages the rewritten pipeline actually imports) are declared in
  `requirements.txt` and get installed by the existing
  `pip install -r requirements.txt` step — no Dockerfile change needed.
- `docker-compose.yml`: `celery_worker`/`celery_beat` build from the
  same `./backend` image as the `backend` web service, so they get
  `ffmpeg`/`blurhash`/`piexif` too — video/image processing runs in the
  worker process, so this matters. All three services already share one
  `DJANGO_SETTINGS_MODULE` source (`backend/.env`) per a Phase 0 fix —
  confirmed still consistent, untouched this phase.
- `config/settings/production.py`: `manage.py check --deploy
  --settings=production` run for real (fake-but-present AWS/DB/SECRET_KEY
  env vars, since production intentionally refuses to boot without
  them) — **passes cleanly** (one expected warning about the
  deliberately-weak test `SECRET_KEY` used only for this check, not a
  real issue). Confirms the new per-field storage classes
  (`PrivateMediaStorage`/`PublicMediaStorage`) don't break the
  production settings module's existing `STORAGES`/AWS validation.
- `frontend/nginx.conf`: SPA-fallback-only, never touches
  `/media/`/`/static/` — confirmed unaffected by any Phase 2 media
  change (media is served by Django/S3, not this nginx layer).
- No new environment variables were introduced. No Windows/Linux
  path-casing risk in the new code — all new storage/derivative paths
  are built with Django's own `os.path`/f-string conventions already
  used throughout the existing codebase, on the same pattern as the
  pre-existing `get_*_path()` functions.

## G. Real media-path tests added

- `apps/photos/tests/test_image_pipeline.py` (new, 9/9 passing): GPS
  stripped/preserved-when-absent, all three derivative tiers'
  dimensions/content-type/aspect-ratio, deterministic/idempotent output,
  no-upscale-of-small-images, full upload→READY integration via the
  real API + `captureOnCommitCallbacks`, auto-cover-assignment,
  retry-on-already-READY no-op, corrupt image → FAILED + original
  preserved.
- `apps/photos/tests/test_video_pipeline.py` (new, 9/9 passing): poster
  + H.264/AAC/yuv420p playback derivative generation (verified via real
  ffprobe re-inspection of the output), the short-video-under-2s poster
  regression this phase fixes, scale-down-only-never-upscales,
  MOV-container input, video-without-audio-track, full upload→READY
  integration, storage-class boundary
  (`PrivateMediaStorage`/`PublicMediaStorage`), retry no-op, corrupt
  video → FAILED + original preserved.
- `apps/clients/tests/test_delivery_and_pagination.py` (new, 16/16
  passing): a password-protected gallery's original-file endpoints
  (photo download, video stream, the new paginated-photos endpoint) all
  require a valid unlocked session and reject an invalid token; the
  public gallery/photos payload never surfaces a raw `original_file`
  path; an open (non-protected) gallery's derivatives and photo download
  need no token; `original_file` vs. the derivative fields genuinely use
  different storage classes at the model level; `PublicGalleryView`'s
  `photos_count`/`photos_has_more`/`photos_page_size` behave correctly
  both under and over one page (tested with `page_size*2 + 7` assets,
  simulating the large-gallery requirement at a fast-to-build scale);
  `PublicGalleryPhotosView` serves the correct non-overlapping next page
  with a proper `{count, next, previous, results}` envelope, excludes
  non-READY assets, and 404s for a nonexistent gallery.
- Full backend suite: **75/75 passing** (41 pre-existing + 18 new
  image/video pipeline tests + 16 new delivery/pagination tests), run
  against a real embedded PostgreSQL instance with `development`
  settings and **no fake AWS credentials** (see "Real bugs found and
  fixed" — fake creds falsely activate real S3Boto3Storage against a
  nonexistent bucket and mask a real test bug). This is a cleaner
  baseline than Phase 1's accepted "36/41 with 5 known S3-environment
  failures" — those 5 are gone, and the on_commit bug that was hiding
  behind them is fixed (see below).
- Frontend production build (`vite build`) — **PASS**, 2403 modules
  transformed cleanly, only the same pre-existing >500kB chunk-size
  advisory noted in the Phase 1 doc (unrelated, not a Phase 2
  regression).

## H. Storage / cost safety

Per-image-upload object count: **1 original + 3 derivatives (display/
medium/thumbnail WebP) + 1 blurhash string (stored inline on the model
row, not a file)** = 4 stored objects, down from what a naive "add a
tier" approach could have produced, and with the old broken
placeholder-blurhash bug fixed so the blurhash itself now costs nothing
extra (it was already being "generated" — just wrong — before).
Per-video-upload object count: **1 original + 1 poster JPEG + 1 H.264/
AAC MP4 playback derivative** = 3 stored objects, down from 4 previously
(the removed WebM hover-preview). No variant was added without a
concrete MVP purpose named in the instructions; the medium (1280px)
image tier is the one net-new derivative introduced this phase, and it
directly replaces what would otherwise have been the full 2048px
display image downloaded into an ordinary in-page grid column —
smaller total bytes transferred per grid view in practice, not more.
`Cache-Control: immutable, max-age=1yr` on every derivative (item C)
means a CDN absorbs essentially all repeat-view bandwidth after first
load, which matters more for cost at scale than trimming the derivative
count further.

## I. Validation run

- `manage.py check --settings=development` — **PASS**
- `manage.py check --deploy --settings=production` — **PASS** (1 expected
  warning from a deliberately-weak test-only `SECRET_KEY`)
- `manage.py makemigrations --check --dry-run` — **PASS** (no drift)
- `manage.py migrate` (fresh DB) — **PASS**
- Full backend test suite — **75/75 PASS**
- Frontend production build (`vite build`) — **PASS**
- `npm`/pip dependency installs — both already resolve correctly
  (`blurhash==1.1.5` added to `requirements.txt`; no new frontend
  dependencies were needed — `srcset`/`sizes` and the design-settings
  work use only plain React/DOM APIs already available)
- **Docker status: NOT RUN.** No `docker`/`docker-compose` binary is
  available in this sandboxed execution environment (`which docker` /
  `which docker-compose` both return nothing) — confirmed, not assumed.
  Every other production-parity check that doesn't strictly require the
  Docker daemon (Dockerfile/compose file inspection, a real
  `manage.py check --deploy` run against production settings, migration
  application against a real Postgres instance) was run for real
  instead. **A real `docker build` / `docker compose build` / `docker
  compose up` pass against this repo is still pending** and should be
  the first thing run in an environment that has Docker available,
  before this phase's production-parity claim is treated as fully
  closed.

## Real bugs found and fixed (not hypothetical — reproduced before fixing)

1. **FFmpeg poster generation silently failed on any video under 2
   seconds.** The old code hardcoded `-ss 00:00:02`; reproduced directly
   with a real 1-second synthetic video (`Output file is empty, nothing
   was encoded`) before writing the fix (`poster_ts =
   max(0, min(2, duration/2))`).
2. **Video poster stored as `.webp` with JPEG bytes.**
   `get_video_poster_path()` returned a `.webp` extension for a file
   FFmpeg always writes as JPEG — content-type/extension mismatch on
   every video ever uploaded. Fixed to `.jpg`.
3. **BlurHash was never actually being generated.** The `blurhash`
   package was never listed in `requirements.txt` (so `import blurhash`
   always raised `ImportError`), and even installed, the old call used
   `x_components=`/`y_components=` keyword arguments that don't exist on
   the real package (actual signature: `components_x=`/`components_y=`)
   and passed a PIL Image directly where the package requires a plain
   3D `[y][x][r,g,b]` list. Every image ever uploaded silently got the
   exact same hardcoded placeholder hash. Fixed on all three counts;
   verified against the real `blurhash==1.1.5` package.
4. **`piexif.insert()` was being called without its required 3rd
   argument** when operating on in-memory bytes (`ValueError: Give a 3rd
   argument to 'insert' to output file`) — GPS-stripping would have
   crashed (caught by the pipeline's own exception fallback, so it
   silently fell back to *not* stripping GPS rather than visibly
   failing). Fixed by supplying an `io.BytesIO()` output buffer.
5. **A pre-existing, previously-masked `transaction.on_commit()` test
   bug** in `test_async_uploads.py`: `TestCase`'s wrapping transaction
   never commits, so `on_commit()` callbacks (the view's real
   `process_photo_asset.delay(...)` dispatch) never fired in that test.
   This was always broken but hidden behind an unrelated fake-S3-creds
   failure that failed the same test at an earlier assertion first.
   Fixed with `self.captureOnCommitCallbacks(execute=True)`; also
   determined that removing fake `AWS_*` test-environment env vars
   (which otherwise falsely activate real S3Boto3Storage against a
   nonexistent bucket) eliminates 5 failures that were being carried
   forward as "pre-existing, accepted" since Phase 1 — they were an
   artifact of the verification script's own env setup, not the
   application.

## Remaining issues / explicitly out of scope for Phase 2

- **Docker build/compose run** — pending a Docker-capable environment
  (see item I).
- **Dashboard gallery-manager list pagination** — deliberately not
  added; see item D for the reorder-feature conflict this would create.
  If a dashboard-side large-gallery problem is reported later, the fix
  belongs with a redesign of `PhotoReorderView`'s full-list contract
  (e.g. relative/delta reordering instead of a full resubmitted list),
  not a bolt-on page param.
- Photo sets, favorites, slideshow, card payments, advanced sharing,
  wildcard subdomains — untouched, per instructions.
- `apps/photos/tests/test_bulk_actions.py`'s async-upload-adjacent tests
  were not revisited beyond confirming they're unaffected by Phase 2 (no
  behavior change in bulk delete/reorder this phase).
- The Design page's own dashboard-side `CoverPreview.jsx` was refactored
  (constants extracted to the shared module) but its own behavior was
  verified unchanged (same class/theme values, same conditional overlay
  logic) — not a redesign.

## Exact next phase

Per the verified execution plan's ordering, Phase 2 (media delivery +
video + large-gallery performance) is now the completed foundation.
Photo sets, favorites, and slideshow are the next unblocked feature
phase. Before that, or alongside it, worth revisiting: a Docker-capable
environment to close out item I's one pending check, and — only if a
dashboard-side large-gallery complaint is actually reported — a
reorder-contract redesign that would unblock dashboard pagination
without breaking drag-and-drop.

---

## Post-Phase-2 hotfix (2026-09-30): GET/POST /api/v1/galleries/ 500

### Symptom
- `GET /api/v1/galleries/` → 500 (once any gallery row existed for the user)
- `POST /api/v1/galleries/` → 500 (always)
- `GET /api/v1/galleries/dashboard/stats/` and `OPTIONS /api/v1/galleries/`
  stayed healthy (200) because neither one touches a `Gallery` queryset —
  `DashboardStatsView` reads `MediaAsset`/`UserSubscription` aggregates, and
  `OPTIONS` never executes the view body.

### Root cause
Two migrations generated during Phase 2 were **never applied** to the
running database:
- `apps/galleries/migrations/0005_gallery_design_settings.py`
  (`Gallery.design_settings`)
- `apps/photos/migrations/0002_mediaasset_medium_file_mediaasset_playback_file_and_more.py`
  (`MediaAsset.medium_file`, `MediaAsset.playback_file`, plus storage-backend
  `AlterField`s on the other derivative fields)

`models.py` already declared `design_settings`, so every ORM-generated
`SELECT`/`INSERT` against `galleries` included that column. The database
table didn't have it (`manage.py showmigrations` showed both migrations as
`[ ]`, unapplied). Confirmed via full traceback (`APIClient` + `force_authenticate`,
not the one-line access log):

```
django.db.utils.ProgrammingError: column "design_settings" of relation "galleries" does not exist
```

- **POST** hit this on every call: `GalleryCreateSerializer.create()` →
  `Gallery.objects.create(...)` → `INSERT INTO galleries (..., design_settings, ...)`.
- **GET** hit this only once a gallery row actually existed: with zero
  galleries, DRF's `PageNumberPagination` short-circuits on the `COUNT(*)`
  query (which doesn't reference `design_settings`) and never issues the
  main `SELECT`, so an empty account looked healthy. The instant one
  `Gallery` row existed, `GalleryListSerializer`'s backing `SELECT`
  (including `select_related('cover_photo')`, which pulls every `MediaAsset`
  column too) hit the missing column and 500'd.

Both failures are **the same root cause**, not two separate bugs: an
unapplied migration state, not an application-code defect. This is a
deploy/ops gap (`makemigrations` was run at some point in the Phase 2
session; `migrate` against the actual dev database was not), not something
introduced by a code change to `views.py`/`serializers.py`/`models.py`
themselves — those files were already correct and internally consistent.

### Fix
```
python manage.py migrate galleries
python manage.py migrate photos
```
No application code was changed. `manage.py check` and
`manage.py makemigrations --check --dry-run` both report clean after the
migration state is caught up. The API response contract is unchanged, so no
frontend changes were needed.

### Files changed
- `backend/apps/galleries/tests/test_gallery_list_create.py` (new) —
  focused regression coverage for GET/POST `/api/v1/galleries/`.
- No production code files were modified. `galleries/migrations/0005_...`
  and `photos/migrations/0002_...` already existed on disk (untracked/
  uncommitted from the Phase 2 session) and were applied, not authored,
  by this fix.

### Tests run
- New: `apps/galleries/tests/test_gallery_list_create.py` — 5/5 passing
  (empty list, list with an existing gallery, list with a `cover_photo`
  join, create, create→list round trip).
- Existing: `python manage.py test apps.galleries apps.clients` — 45/45
  passing.
- `python manage.py check` — no issues.
- `python manage.py makemigrations --check --dry-run` — no changes
  detected (model/migration state now consistent).

### Verification (real endpoints, not just unit tests)
Ran the actual golden path end to end against the dev Postgres database
via `APIClient` (equivalent to opening the galleries page, listing, and
creating a collection):
`GET /api/v1/galleries/` (200) → `POST /api/v1/galleries/` (201) →
`GET /api/v1/galleries/` (200, new gallery present in `results`) →
`GET /api/v1/galleries/dashboard/stats/` (200). All confirmed passing.

### Phase 2 impact
None. No Phase 0/1/2 functionality was reverted, and no locked product
decisions (NPR, manual payments, `/g/:username/:slug`, subdomains
post-MVP, 3 GB / 10 galleries, real persisted `design_settings`) were
touched. `design_settings` remains a real, persisted, applied field —
this hotfix is what makes it actually reach the database.

---

## Phase 3 — Core Client Experience — COMPLETE (backend) / functional (frontend)

Scope per the Phase 3 instruction: Photo Sets, Favorites, Download PIN +
resolution, Download Activity, Slideshow, and the client/photographer UX
integration for all five. No media/CDN/video pipeline work, no Stripe, no
wildcard subdomains, no full redesign — all respected.

### 1. Photo Sets

**Backend**
- New model `apps/photos/models.py::PhotoSet` — `gallery` FK, `name`,
  fractional-decimal `order` (same pattern as `MediaAsset.order`).
  `UniqueConstraint(gallery, name)`; index on `(gallery, order)`.
- `MediaAsset.photo_set` — nullable FK to `PhotoSet`, `on_delete=SET_NULL`
  (deleting a set never deletes its photos — they fall back to
  "unsorted"). Index on `(photo_set, order)` for the set-filtered query.
- Migration: `photos/migrations/0003_photoset_mediaasset_photo_set_and_more.py`.
- Photographer API (`apps/photos/views.py`, tenant-scoped by
  `gallery.photographer=request.user` on every endpoint):
  - `GET/POST /api/v1/photos/{gallery_slug}/sets/` — list (with live
    `photo_count` via one annotated `Count()`, no N+1) / create.
  - `PATCH/DELETE /api/v1/photos/{gallery_slug}/sets/{set_id}/` — rename /
    delete.
  - `PATCH /api/v1/photos/{gallery_slug}/sets/reorder/` — full ordered-id
    list, same fractional-renumbering pattern as `PhotoReorderView`.
  - `PATCH /api/v1/photos/{gallery_slug}/sets/assign/` — bulk move photos
    into a set (or `set_id: null` to unsort), one `UPDATE ... WHERE id IN
    (...)` — no per-photo query.
- Client-facing (`apps/clients/`):
  - `PublicGallerySerializer.photo_sets` — id/name/READY-only
    `photo_count` per set, annotated once by the view.
  - `?set=<id>` filter on both `PublicGalleryView` (embedded first page)
    and `PublicGalleryPhotosView` (pagination continuation) — always
    AND-ed with `gallery=gallery`, so a foreign set id yields zero
    results rather than leaking another gallery's photos.
- Full-gallery ordering (`MediaAsset.order` / the "All Photos" view) is
  untouched — set membership is a separate, orthogonal field.

**Frontend**
- `photosApi.js`: `listSets`, `createSet`, `renameSet`, `deleteSet`,
  `reorderSets`, `assignPhotosToSet`.
- `clientsApi.js`: `getGalleryPhotosBySet` (adds `?set=` to the existing
  pagination call).
- Dashboard (`GalleryPhotosPage.jsx`): a sets bar above the photo grid —
  create/rename/delete, reorder (‹›  buttons — not drag-and-drop, kept
  simple per instructions), a "Select photos" mode (checkbox overlay,
  reusing `PhotoGrid.jsx`'s new optional `selectable`/`selectedIds`/
  `onToggleSelect` props) and a "Move N selected to: [set buttons]" bulk
  action. Drag-reorder (`onReorder`) is disabled whenever a set tab other
  than "All" is active, since reordering a filtered subset would corrupt
  the full-gallery order.
- Client gallery (`ClientGalleryPage.jsx`): set tabs above the grid;
  switching tabs re-fetches that set's own first page (not a client-side
  filter of the "All" page, since sets are meant to hold their own full
  contents).

### 2. Favorites

**Backend**
- New model `apps/clients/models.py::Favorite` — `gallery`, `media_asset`,
  `client_session` (nullable), `client_key`, `email` (nullable).
  `UniqueConstraint(gallery, media_asset, client_key)` — the idempotency
  guarantee IS the DB constraint, not application logic.
- **Identity model** (see the model's own docstring for the full
  rationale): a password-protected gallery's `client_key` is the same
  `ClientSession.access_token` already issued at unlock (so identity is
  tied to something server-verified, never client-supplied); an open
  gallery has no session concept at all, so `client_key` is a random id
  the frontend generates once per browser and persists in the same
  sessionStorage-backed store as the existing unlock tokens
  (`clientStore.js`'s new `clientUids` map / `getOrCreateClientUid()`).
- Endpoints (`apps/clients/views.py::GalleryFavoritesView`):
  - `GET /api/v1/public/{username}/{slug}/favorites/?client_uid=...` —
    batch-fetch every favorited `media_asset_id` in ONE request.
  - `POST` / `DELETE` same path, body `{media_asset_id, client_uid?}` —
    idempotent add/remove (`get_or_create` / plain `filter().delete()`).
  - For protected galleries, identity is resolved from the
    `Authorization: Bearer <token>` header against a real
    `ClientSession` row — a client cannot fabricate an identity or
    favorite through a gallery it hasn't actually unlocked.
  - Tenant scoping: the target `MediaAsset` must belong to the gallery in
    the URL — a foreign asset id 404s.
- Photographer-facing: `GET /api/v1/galleries/{slug}/favorites/`
  (`GalleryFavoriteActivityView`, paginated, `PhotographerFavoriteSerializer`
  — thumbnail, title, email, timestamp; never the raw `client_key`).

**Frontend**
- `clientsApi.js`: `getFavorites`, `addFavorite`, `removeFavorite`.
- `PublicMasonryGrid.jsx` / `PhotoLightbox.jsx`: heart icon, optimistic
  toggle with rollback on failure (`ClientGalleryPage.jsx::handleToggleFavorite`).
- Favorites are batch-loaded once per gallery view (not per-photo) right
  after the gallery itself loads.
- `ActivitiesWorkspace.jsx`'s "Favorite Activity" tab now renders real,
  paginated data from `galleriesApi.getFavoriteActivity()`.

### 3. Download PIN + Resolution

**Backend**
- `Gallery.download_pin_hash` (nullable `CharField`, bcrypt hash only —
  never plaintext) — a SECOND gate, independent of the existing gallery
  access password. Migration: `galleries/0006_gallery_download_pin_hash.py`.
- `POST /api/v1/galleries/{slug}/set-download-pin/`
  (`GallerySetDownloadPinView`) — set/change/clear, 4–8 digit validation,
  same bcrypt pattern as `GallerySetPasswordView`.
- Both download endpoints now verify the PIN when one is configured:
  - `PublicGalleryDownloadView` (ZIP): PIN in the JSON body; missing/wrong
    PIN → 401 with `code: pin_required` / `invalid_pin`, logged nowhere
    (no `DownloadLog` row on a failed attempt).
  - `PublicPhotoDownloadView` (single photo/video): PIN as a `?pin=`
    query param (it's a plain `<a href>` GET, same convention as
    `?token=`).
- **Resolution** (`web` | `original`, default `original` for backward
  compatibility): `web` serves the already-generated derivative — the
  2048px WebP `display_file` for an image, the H.264 `playback_file` for
  a video — never regenerates or stores a new file. Falls back to the
  original if no derivative exists yet (still processing). The
  single-file endpoint's `Content-Disposition` filename matches whichever
  file is actually served (`.webp`/`.mp4` vs the original extension).
- `DownloadLog.email` is now nullable — the single-file endpoint is
  deliberately frictionless (no email capture), so it can still log
  activity. Migration: `clients/0005_alter_downloadlog_email.py`.

**Frontend**
- `galleriesApi.js`: `setDownloadPin`.
- `GallerySettingsPage.jsx`: a "Download PIN" control in the Download tab,
  alongside (but independent of) the gallery password.
- `DownloadPage.jsx`: a Web Size / High Resolution choice, and a PIN
  field that only renders when the gallery has one configured (passed via
  router state from `ClientGalleryPage.jsx`). Wrong/missing PIN is
  surfaced as a recoverable inline form error, not a dead-end screen.
- **Known scope gap**: per-photo/video hover-download and lightbox-download
  buttons are plain `<a href>` GETs with no inline PIN-entry UI. Rather
  than let them silently 401 with a raw JSON error page, `ClientGalleryPage.jsx`
  hides those single-item download affordances whenever the gallery has a
  PIN configured (`displayPhotos` strips `download_url`) — the bulk
  "Download Full Gallery" / "Download Selected" flow (which DOES have a
  real PIN form) remains the supported path. A per-photo PIN-prompt
  modal is a reasonable follow-up, not built this phase.

### 4. Download Activity

**Backend**
- `DownloadLog` extended: `media_asset` (nullable FK, `SET_NULL`),
  `photo_set` (nullable FK, `SET_NULL`), `download_type`
  (`gallery`/`photo`/`video`), `resolution`, `pin_verified`. Migration:
  `clients/0004_downloadlog_download_type_downloadlog_media_asset_and_more.py`.
- `GET /api/v1/galleries/{slug}/download-logs/`
  (`GalleryDownloadLogsView`) — paginated (`StandardResultsSetPagination`,
  20/page), tenant-scoped, `select_related('media_asset', 'photo_set')`
  (no N+1), newest first.
- Every log write happens only AFTER every authorization gate (allow_download,
  password session, PIN) has already passed — a failed/blocked attempt
  never creates a row.
- No export endpoint — judged not practical to add well within this
  phase's scope; noted here as a deferred, not forgotten, item.

**Frontend**
- `galleriesApi.js`: `getDownloadLogs`.
- `ActivitiesWorkspace.jsx`'s "Download Activity" tab now renders real,
  paginated data (email, type, resolution, set, PIN-verified, date)
  instead of the previous permanently-empty stub.

### 5. Slideshow

Implemented as an autoplay mode on the EXISTING `PhotoLightbox.jsx`
rather than a new component — it already had next/prev, swipe, keyboard
nav, and neighbor-only preloading (never the whole gallery), so a
from-scratch slideshow would have duplicated all of that.
- New `slideshowMode` prop starts autoplay immediately; a play/pause
  button (header) and the spacebar (when the current slide isn't a
  video) toggle it anytime.
- Autoplay loops back to photo 1 at the end (a real slideshow, not one
  that just stops) and auto-pauses itself while the current slide is a
  video (no fixed-timer interruption of video playback).
- Uses `display_url`/`medium_url` (the same optimized derivatives the
  grid already uses) — never `original_url`. Preloading is still only
  the immediate neighbors (±1), unchanged from the existing lightbox
  behavior — a slideshow over a 500-photo gallery never preloads more
  than 3 images at a time.
- `ClientGalleryPage.jsx` adds a "Slideshow" button (shown whenever the
  gallery has more than one photo) that opens the lightbox at index 0
  with `slideshowMode` on.

### 6–7. Client UX integration / Photographer UX

- Client gallery flow is now: Cover → Gallery → Set tabs → Favorite (heart
  icon) → Download (PIN + resolution aware) → Slideshow — all real,
  backend-verified functionality, no placeholder buttons.
- Loading/empty/error states extended for the new surfaces: a
  set-switch shows its own spinner and a set-specific "No photos in this
  set yet" empty state (distinct from the gallery-wide empty state); a
  gallery with a download PIN hides download affordances it can't
  actually serve rather than showing a broken one.
- Dashboard: `GallerySettingsPage.jsx` reflects `has_download_pin` from
  the real backend field after refresh (no hardcoded state);
  `ActivitiesWorkspace.jsx`'s two real tabs replace their previous
  permanently-empty placeholders; `GalleryPhotosPage.jsx`'s set counts
  come from the live `photo_count` annotation, never a client-side guess.

### 8–9. Query performance / Security

- No N+1 introduced: every new list endpoint uses exactly one annotated
  `Count()` (sets, favorite counts) or one `select_related()`
  (download logs), regardless of row count.
- All new list endpoints are paginated (`StandardResultsSetPagination`
  for download logs/favorite activity, the existing `GalleryMediaPagination`
  for set-filtered photo pages).
- New index: `idx_set_assets_order` on `MediaAsset(photo_set, order)` —
  the one new lookup path (set-filtered, ordered photo queries) that
  didn't already have index coverage. No other indexes added — the rest
  reuse `idx_gallery_assets_order`/existing FK indexes.
- Writes are idempotent where the domain calls for it: favorite add/remove
  (`get_or_create` / `filter().delete()`), PhotoSet assign (a plain bulk
  `UPDATE`, safe to retry).
- Tenant/authorization boundaries added and regression-tested (see
  Testing below): PhotoSet CRUD/reorder/assign all scope by
  `gallery.photographer=request.user`; Favorites scope by `gallery` and
  validate the asset belongs to it; download PIN cannot be bypassed by
  omitting it, sending an empty string, or guessing (bcrypt-verified,
  same pattern as the gallery password); private originals are still
  only ever reached through the existing authorized download views —
  no new direct-file-URL exposure was introduced anywhere in this phase.

### 10. Migrations / deployment safety

New migrations this phase (all applied to the dev DB and verified with
zero drift both before and after):
- `galleries/0006_gallery_download_pin_hash.py`
- `photos/0003_photoset_mediaasset_photo_set_and_more.py`
- `clients/0004_downloadlog_download_type_downloadlog_media_asset_and_more.py`
- `clients/0005_alter_downloadlog_email.py`

Verification performed (not just claimed):
- `python manage.py makemigrations --check --dry-run` → "No changes
  detected", both before writing tests and again at the end.
- Migrations applied to a genuinely FRESH database
  (`phase3_fresh_check`, created via `psycopg2`, migrated end-to-end,
  `check`/`makemigrations --check` both clean, then dropped) — confirms
  the full migration history (not just these four files) replays cleanly
  from zero, not only incrementally on top of already-migrated state.
- Migrations applied to the EXISTING dev database (`Kyapture_DB`) —
  `showmigrations` shows zero unapplied migrations across every app,
  `makemigrations --check --dry-run` clean.

**Deployment gap identified (not fixed this phase, per instructions):**
Neither `backend/Dockerfile` (gunicorn `CMD`) nor `docker-compose.yml`
(`command: python manage.py runserver`) runs `manage.py migrate` before
the web/worker processes start serving traffic. This is the exact
mechanism behind the pre-Phase-3 gallery-500 regression (see the hotfix
section above) — migrations existing on disk but never applied to the
database the running process actually talks to. **This remains an open
production-deployment requirement**: a real deploy pipeline must run
`manage.py migrate` (typically as a release/init step, or an entrypoint
script run once before gunicorn starts) before new code that depends on
new schema is allowed to serve traffic. Recording this here rather than
redesigning the deployment process, per this phase's explicit scope
boundary.

### 11. Testing

New test files (all passing):
- `apps/photos/tests/test_photo_sets.py` — 17 tests: create/rename/
  delete/reorder/assign, duplicate-name rejection, tenant isolation on
  every operation, full-gallery order untouched by set assignment.
- `apps/clients/tests/test_favorites.py` — 14 tests: open-gallery
  `client_uid` flow, protected-gallery session-token flow (including that
  a client cannot fabricate an identity via a forged `client_uid` on a
  protected gallery), idempotent add/remove, cross-gallery isolation,
  photographer-facing activity view tenant scoping.
- `apps/clients/tests/test_download_pin_resolution.py` — 23 tests: PIN
  set/clear/validation, missing/wrong/empty-string PIN rejection on both
  download endpoints, correct-PIN success + `pin_verified` logging,
  web vs original resolution (asserted against actual served bytes, not
  just the field value), download-logs endpoint pagination + tenant
  scoping.
- `apps/clients/tests/test_public_photo_sets.py` — 5 tests: `photo_sets`
  metadata with correct READY-only counts, `?set=` filtering on both the
  embedded first page and the pagination continuation endpoint, a
  foreign gallery's set id yielding zero photos (not a 404 or a leak).

Total new tests: **59**, all passing (confirmed individually per file
above — each new test file was run in isolation and passed before being
combined with the rest of the suite).

Full suite run: `python manage.py test apps.galleries apps.clients
apps.photos apps.users apps.core` — **139 tests, all passing** (0
failures, 0 errors), run to completion twice: once mid-phase (134 tests —
before `test_public_photo_sets.py` existed) and once at the very end with
every Phase 3 file in place (139 tests). No regressions in any Phase
0/1/2 test.

Also run and clean: `manage.py check`, `manage.py makemigrations --check
--dry-run` (both before and after the fresh-DB verification above),
`npm run build` (frontend production build — succeeds, one pre-existing
"chunk larger than 500kB" warning, not a Phase 3 regression — the bundle
was already large before this phase and code-splitting it is a separate,
non-urgent concern).

**Not performed**: live browser/manual interaction testing of the new
client-facing flows (set tabs, favorite persistence across an actual
refresh, slideshow autoplay) — verified at the code/contract level
(backend tests + a clean production build) but not clicked through in a
running browser this session. Flagging this explicitly rather than
claiming an untested "it works."

### Files changed (Phase 3)

Backend:
- `apps/photos/models.py`, `apps/photos/serializers.py`,
  `apps/photos/views.py`, `apps/photos/urls.py`
- `apps/galleries/models.py`, `apps/galleries/serializers.py`,
  `apps/galleries/views.py`, `apps/galleries/urls.py`
- `apps/clients/models.py`, `apps/clients/serializers.py`,
  `apps/clients/views.py`, `apps/clients/urls.py`
- New migrations listed above
- New test files listed above

Frontend:
- `api/photosApi.js`, `api/clientsApi.js`, `api/galleriesApi.js`
- `store/clientStore.js`
- `components/shared/PhotoGrid.jsx`, `PublicMasonryGrid.jsx`,
  `PhotoLightbox.jsx`
- `pages/dashboard/GalleryPhotosPage.jsx`, `GallerySettingsPage.jsx`,
  `ActivitiesWorkspace.jsx`
- `pages/client/ClientGalleryPage.jsx`, `DownloadPage.jsx`

### Unresolved / explicitly deferred items

- Per-photo/video single-download PIN entry UX (see section 3's "Known
  scope gap" above) — currently hidden rather than broken when a PIN is
  set; a proper inline prompt is future work.
- Download-log CSV/export — judged impractical to add well within this
  phase.
- Deployment pipeline `migrate`-before-serve step — identified, not
  built (explicitly out of this phase's scope per instructions).
- Live browser verification of the new client-facing UX — not performed
  this session (see Testing above).
- Drag-and-drop set reordering — implemented instead as simple ‹›
  move-earlier/move-later controls, functionally equivalent but not the
  same interaction as photo drag-reorder.

### Exact next phase (superseded — see Phase 4 below)

~~Per the original locked scope, photo sets / favorites / slideshow /
download PIN+resolution / download activity — the core client-experience
gap — are now closed. The next unblocked phase is either:
(a) closing the deployment-pipeline migration gap identified in section
10 (a real production-readiness item, small in scope), or
(b) the next feature phase per whatever product priority follows this
one (not specified in the Phase 3 instruction) — card payments and
wildcard subdomains remain explicitly out of scope per the locked
product decisions until a future MVP-graduation decision changes them.~~

Item (a) above is exactly what Phase 4 (immediately below) does first.

---

## Phase 4 — Production Hardening + Remaining Server-Side Correctness — COMPLETE

Scope per the Phase 4 instruction: close the remaining production risks
identified by prior audits (many pre-dating Phase 0) before final launch
QA — deployment migration safety, storage/quota integrity, download
hardening, auth/security hardening, the private-original-vs-public-
derivative question, and DB cleanup. No new features, no UI redesign, no
Stripe/subdomains/social features, no redoing the media/CDN pipeline or
Phase 3's own features.

### 1. Deployment migration safety (HIGH PRIORITY) — DONE, Docker execution PENDING

**Root cause context**: the exact regression this closes is the one from
the post-Phase-2 hotfix earlier in this file — migrations existing in
the repo but never applied to the database the running process actually
talks to. Neither `backend/Dockerfile`'s gunicorn `CMD` nor
`docker-compose.yml`'s `celery_worker`/`celery_beat` ran `manage.py
migrate` before starting.

**What was built**: `backend/docker-entrypoint.py` — a shared entrypoint
for every container built from the backend image (web, worker, beat all
build the same image in `docker-compose.yml` and only override `CMD`,
never `ENTRYPOINT`). Enforces, in order:

1. **Database available** — polls Postgres via `psycopg2.connect()`
   with a bounded retry loop (`DB_WAIT_TIMEOUT_SECONDS`, default 60s);
   exits non-zero (container fails to start) if the DB never becomes
   reachable, rather than hanging forever or half-starting.
2. **Migrations applied successfully** — runs `manage.py migrate
   --noinput` under a **Postgres session advisory lock**
   (`pg_advisory_lock`/`pg_advisory_unlock`, fixed key) so that web,
   worker, and beat starting concurrently (the normal `docker-compose up`
   case) never race `CREATE TABLE`/`ALTER TABLE` statements against each
   other — whichever container acquires the lock first actually runs
   migrate; the others block, then run migrate too (now a fast idempotent
   no-op, since Django migrations are idempotent by design) once the lock
   releases.
3. **Failed migration prevents an unsafe deployment** — if `migrate`
   exits non-zero, the entrypoint exits non-zero too and **never execs**
   the real command (gunicorn / celery worker / celery beat). No
   container can come up "successfully" and serve traffic or process
   tasks against a schema that failed to migrate.
4. **Backend starts serving traffic / Celery worker+beat start against
   the same schema** — only after 1–3 above succeed does
   `os.execvp(*sys.argv[1:])` hand off to the real `CMD`.

`backend/Dockerfile` now sets `ENTRYPOINT ["python",
"docker-entrypoint.py"]` (previously none) and keeps its existing
gunicorn `CMD` as the default. `docker-compose.yml` also gained a
`pg_isready` healthcheck on `db` and `depends_on: condition:
service_healthy` for `backend`/`celery_worker`/`celery_beat` — an
orchestration-level guarantee on top of (not instead of) the
entrypoint's own independent retry loop.

An escape hatch (`SKIP_ENTRYPOINT_MIGRATIONS=true`) exists for one-off
debugging containers (`docker run ... bash`) where waiting on the DB /
running migrate makes no sense.

**Verified (without a Docker daemon — none is available in this
environment, confirmed via `docker --version` → command not found)**:
- Ran `docker-entrypoint.py` directly against the real dev Postgres
  (`Kyapture_DB`) with a real command (`python manage.py check`):
  successfully waited for the DB, acquired the lock, ran migrate
  (idempotent no-op — already migrated), released the lock, and exec'd
  the real command, which printed its own output and exited 0.
- Ran it against a deliberately wrong `DB_NAME` (nonexistent database):
  correctly retried, then exited 1 after the timeout, without ever
  reaching migrate or exec — confirms the fail-loud path.
- Ran **two concurrent invocations** of the entrypoint against the same
  real database simultaneously (backgrounded shell processes): both
  completed successfully, both exited 0, confirming the advisory lock
  correctly serializes concurrent migration attempts instead of
  racing/erroring.
- `docker-compose.yml` validated as syntactically correct YAML (parsed
  with PyYAML) with the expected `depends_on`/`healthcheck` structure.

**Explicitly NOT verified (Docker unavailable in this environment)**:
`docker build ./backend`, `docker build ./frontend`, and `docker-compose
up` end-to-end were **not run** — no Docker daemon exists here. This
matches `docs/KYAPTURE_PHASE0_STATUS.md`'s own prior finding (same
environment limitation, not new to this phase). **Recommend running
`docker-compose build && docker-compose up` once on a machine with
Docker available as the literal final sign-off step before this phase
counts as validated end-to-end**, not just at the logic/script level
verified here.

**Documented deployment sequence for production** (not docker-compose,
which is explicitly dev-only per its own file-level comment): a real
production deployment should build the `backend/Dockerfile` image and
run it with `DJANGO_SETTINGS_MODULE=config.settings.production` plus
real `SECRET_KEY`/`DB_*`/`AWS_*`/`DEFAULT_FROM_EMAIL` values for THREE
container roles from the SAME image — a web role (default `CMD`,
gunicorn), a worker role (`CMD` overridden to `celery -A config worker
-l info`), and a beat role (`CMD` overridden to `celery -A config beat
-l info`) — exactly as `docker-compose.yml` already models for
local dev. All three now go through `docker-entrypoint.py` automatically
(it's the image's `ENTRYPOINT`, not something each role has to remember
to invoke), so the migration-safety sequence above applies identically
regardless of which orchestrator (ECS/k8s/systemd/plain `docker run`)
ultimately runs them.

### 2. Storage + quota integrity (F-30 fix)

- **Free tier limits** (locked product decision #5): `get_user_subscription_metrics()`'s
  `default_limits["max_galleries"]` changed from `None` (unlimited) to
  `10`. Storage was already 3 GB. A free-tier user's 11th gallery now
  correctly 403s with `gallery_limit_reached`.
- **Trash/purge lifecycle** — closes the actual leak (soft-delete
  removed the gallery from view but never actually freed anything, ever,
  at zero counted cost):
  - `Gallery.trashed_at` (nullable `DateTimeField`) — set by
    `GalleryDetailView.delete()` alongside the existing `is_active =
    False`. Migration `galleries/0007_...` (schema) +
    `galleries/0008_backfill_trashed_at.py` (data migration: backfills
    `trashed_at = updated_at` for any ALREADY-trashed row from before
    this field existed, using the last-write timestamp as the best
    available signal — never invents an immediate-purge timestamp for
    old data, and a row with no `updated_at` signal at all — impossible
    here since it's `auto_now` — would simply stay `NULL`/never-eligible
    rather than guessed).
  - **The actual fix**: `get_user_subscription_metrics()` no longer
    filters by `is_active=True` for either the gallery count or the
    storage-bytes aggregation — every gallery row that still exists
    (active OR trashed-pending-purge) counts toward quota. Deleting a
    gallery no longer frees quota until the data is actually gone
    (purged), closing the "delete+reupload indefinitely at zero cost"
    loophole.
  - `GALLERY_TRASH_RETENTION_DAYS` (default 30, env-overridable).
  - `apps/galleries/tasks.py::purge_trashed_galleries` (new Celery Beat
    task, daily at 03:00) — hard-deletes any gallery with
    `is_active=False AND trashed_at IS NOT NULL AND trashed_at <= now -
    RETENTION_DAYS`. `Gallery.delete()` cascades to `MediaAsset`
    (CASCADE) which cascades to the EXISTING `post_delete` signal
    (`apps/photos/signals.py`, untouched) that purges each asset's
    actual S3/disk files — one hard-delete call removes the DB rows AND
    the underlying storage objects, no separate S3-cleanup step needed.
    Idempotent (re-querying the same criteria after a purge simply
    matches nothing) and retry-safe (each gallery is purged inside its
    own try/except so one bad row can't block the batch; a query-level
    failure retries the whole task via Celery's own retry). Never
    touches an active gallery (`is_active=False` is required) or a
    trashed-but-recent one (window check) or a trashed row with no
    timestamp (NULL-safe by construction).
  - New index `idx_gallery_trash_purge` on `Gallery(is_active,
    trashed_at)` for the purge sweep's own query.

### 3. Download hardening

All in `apps/clients/views.py` (`PublicGalleryDownloadView`,
`PublicPhotoDownloadView`) + a new shared helper in `apps/core/utils.py`:

- **Malformed asset IDs never reach a raw queryset filter** —
  `asset_ids` is now validated through a real
  `serializers.ListField(child=serializers.UUIDField())`, exactly like
  `PhotoBulkDeleteSerializer`/`PhotoReorderSerializer` already validate
  similar id lists elsewhere in this codebase. A malformed UUID (or a
  non-list value) now 400s with a clear message instead of raising an
  uncaught `django.core.exceptions.ValidationError` → 500 (the F-27
  finding this closes).
- **Single-file downloads stream instead of loading into RAM** —
  `PublicPhotoDownloadView` now returns `FileResponse(source_field,
  as_attachment=True, filename=...)` instead of `.read()`-ing the whole
  file into memory first. Works identically for local disk (dev) and
  S3Boto3StorageFile (prod) — neither needs the full file resident in
  RAM, which matters far more for a multi-GB video original than it ever
  did for a photo.
- **`sanitize_download_filename()`** (new, `apps/core/utils.py`) —
  strips directory components (`os.path.basename`, defends against zip
  slip / path traversal via a crafted `original_name`), control
  characters and CR/LF (HTTP header injection), and embedded quotes/
  backslashes (breaking out of a quoted `Content-Disposition` value).
  Applied to both the ZIP's per-entry names and the single-file
  download's `Content-Disposition` filename. Verified against an actual
  path-traversal filename (`../../../etc/passwd.jpg`) and an actual
  CRLF-header-injection filename in tests — both produce a safe archive
  entry / header with no traversal and no injected header.
- **Duplicate filenames de-duplicated in the ZIP** — two assets sharing
  an `original_name` previously produced two same-named ZIP entries,
  which most unzip tools silently resolve by keeping only one (real,
  silent data loss for the client). Now suffixed (`_1`, `_2`, ...) so
  both survive extraction.
- **ZIP compression avoids re-compressing already-compressed media** —
  every format this pipeline accepts/produces (`ALREADY_COMPRESSED_EXTS`
  in `apps/core/utils.py`: jpg/jpeg/png/webp/gif/heic/heif/mp4/mov/m4v/
  webm) now gets `zipfile.ZIP_STORED` per-entry instead of blanket
  `ZIP_DEFLATED` — no CPU wasted re-compressing already-entropic bytes.
- **`DownloadLog` written only after success** — the ZIP endpoint's log
  write moved from BEFORE ZIP compilation to AFTER it succeeds (a
  compilation failure now raises out to the existing error-handling
  `except` block and never reaches the log-write line). The single-file
  endpoint's log write already happened after a successful file-open;
  now also gated on the file actually being confirmed openable first.
- **Synchronous-ZIP size guard** — `SYNC_ZIP_MAX_ASSET_COUNT` (default
  500) and `SYNC_ZIP_MAX_TOTAL_BYTES` (default 5 GB), both
  env-overridable. A request exceeding either gets a clear 400
  (`code: download_too_large`) instead of tying up a gunicorn worker for
  an unbounded amount of time. **Decision on sync vs. async**: kept
  synchronous with these limits rather than building an async job
  system — the existing 1MB-chunked-to-disk-then-streamed-back
  compilation was already reasonably memory-safe (confirmed accurate by
  the verified execution plan's own audit trail), and 500 assets / 5 GB
  is a generous technical ceiling for the MVP's realistic gallery sizes,
  not a business limit. Documented here as the sensible-limits answer
  the Phase 4 instruction explicitly allows in place of a rewrite.
- Preserved unchanged: download permission checks, the download PIN
  gate (Phase 3), Web Size / High Resolution resolution behavior (Phase
  3), and the original-files-stay-private guarantee (no new direct-file
  exposure was introduced anywhere in this phase).

### 4. Auth / security hardening

**A. Refresh token rotation (F-36 fix)** — `CookieTokenRefreshView.post()`
previously did `new_refresh_token = str(refresh)`, re-serializing the
SAME `RefreshToken` object (same `jti`) — despite
`ROTATE_REFRESH_TOKENS`/`BLACKLIST_AFTER_ROTATION` both being `True` in
`SIMPLE_JWT` settings, nothing was ever actually rotated or blacklisted.
Now: when rotation is enabled, the user is resolved from the verified
refresh token's own payload (`USER_ID_CLAIM`) — `request.user` isn't
available here (this view is intentionally unauthenticated, working
only from the refresh cookie) — a genuinely NEW `RefreshToken.for_user(user)`
is minted, and the OLD token is blacklisted via `refresh.blacklist()`.
Verified: rotating actually changes the cookie value; reusing the
pre-rotation refresh token afterward correctly 401s; the newly-minted
token still works for a subsequent refresh.

**B. Password change/reset invalidation** — neither
`ChangePasswordSerializer.save()` nor `PasswordResetConfirmView.post()`
previously touched any issued token. New shared helper
`apps/users/utils.py::blacklist_all_outstanding_tokens_for_user()`
(kept in its own module specifically to avoid a circular import between
`views.py` and `serializers.py`) walks every `OutstandingToken` for that
user and blacklists each one — "logout everywhere" on both a
self-service password change and an email-token password reset.
Documented limitation (fundamental to JWT, not something this fix can
close): a bare access token can't be revoked this way (simplejwt's
blacklist only covers refresh tokens) — the existing 15-minute
`ACCESS_TOKEN_LIFETIME` is what actually bounds how long an
already-issued access token can outlive this call. Verified both paths
end-to-end: log in, change/reset the password, confirm the pre-change
refresh token now 401s on refresh.

**C. ClientSession lifecycle** — sessions previously never expired at
all. New `ClientSessionQuerySet.not_expired()` (`apps/clients/models.py`)
enforces `CLIENT_SESSION_TTL_DAYS` (default 30); **all six** session-
validation call sites across `apps/clients/views.py` (gallery view,
paginated photos, favorites identity resolution, the ZIP download gate,
the video stream gate, the single-photo download gate) now go through
it, closing what would otherwise have been an easy-to-miss inconsistency
if the TTL were checked in only one place. `apps/clients/tasks.py::purge_expired_client_sessions`
(new Celery Beat task, weekly) removes expired rows — verified idempotent,
verified it never touches a still-valid session, verified a fresh
session still grants access and an expired one correctly 401s.

**D. Public portfolio privacy (F-35 fix)** — `PublicPhotographerPortfolioView`:
(1) now excludes `is_password_protected=True` galleries from the public
listing entirely — "protected" means private by product intent, so a
protected gallery's title/cover must not be discoverable there even
though its content is itself gated; its own direct link is unaffected.
(2) now excludes `is_staff=True`/`is_superuser=True` accounts from
matching a username at all (404, same "don't distinguish why"
convention this app already uses everywhere for tenant scoping) —
internal/admin accounts were never meant to be discoverable as public
photographer portfolios. Verified: an open gallery still appears; a
protected gallery's title appears nowhere in the response at all
(not just missing from the list — checked the full serialized payload);
a staff and a superuser account both 404 on their own username.

**E. Public endpoint throttling (F-41 fix)** — `PublicGalleryView`,
`PublicGalleryPhotosView`, `PublicVideoStreamView`,
`PublicPhotoDownloadView`, `GalleryFavoritesView`,
`PublicPhotographerPortfolioView`, and `TotalUsersView` previously fell
through to the blanket `anon: 100/day` scope — too tight for a real
visitor (one gallery view already generates far more than 100 requests/
day on its own before counting CGNAT/shared-IP visitors sharing one
bucket). New dedicated `public_gallery_browse` scope (120/minute,
`PublicGalleryBrowseThrottle`/`PublicMetricsRateThrottle`) applied to
all of them — generous enough that no ordinary visitor ever notices it,
while still bounding a genuine scraping burst. `password_unlock`/
`password_reset`/`login` (already correctly tight and dedicated) and
the ZIP download's own `password_unlock`-scoped throttle are untouched,
per the instruction to retain what was already correct. Uses the
already-established `NUM_PROXIES`/`SECURE_PROXY_SSL_HEADER` real-IP
configuration from `production.py` (Phase 0) — no new proxy config
needed. Verified: a tight override of the new scope's own rate (patched
directly on the throttle class — `override_settings(REST_FRAMEWORK=...)`
doesn't work here, see the test file's own comment on why: DRF binds
`THROTTLE_RATES` as a plain class attribute at import time, not a live
settings read) does correctly throttle past its limit; ten ordinary
requests at the real default rate never throttle.

**F. Upload/input security** — investigated and verified, mostly
already correctly protected:
- **Decompression bomb**: crafted a real (but minimal, ~45-byte) PNG
  with a valid `IHDR` chunk declaring 50000×50000 (2.5 billion) pixels
  and no real pixel data, and ran it through the actual upload
  serializer. Confirmed Pillow's default `MAX_IMAGE_PIXELS`
  (~89.5 million) is intact — not disabled anywhere in this codebase —
  and that DRF/Django's own `ImageField` validation layer already
  rejects it with a clean `ValidationError` (400), before this
  serializer's own custom Pillow re-open logic even runs. **No code
  change was needed here** — this was a verify-first item, and it
  verified clean. Added a regression test so this stays true.
- **Path traversal via `original_name`**: verified by direct
  `os.path.splitext()` testing that the extension-extraction step
  `get_original_asset_path()` relies on is inherently path-separator-
  aware (a string like `innocent.jpg/../../../evil` yields an EMPTY
  extension, never a path fragment) — combined with the actual storage
  key being built from `instance.id` (a UUID) plus a hardcoded folder
  template, user input can only ever influence a short suffix string,
  never the path structure. Django's own `safe_join`/`validate_file_name`
  at the storage layer is a second, independent layer of the same
  protection. No code change needed; verified correct by inspection +
  a targeted Python test of the actual splitext behavior.
- **Filename/title length**: `MediaAsset.original_name`
  (max_length=255) and `.title` (max_length=200) previously received
  the raw, unbounded browser-supplied filename directly — an
  excessively long one would reach Postgres as a raw `INSERT` and
  surface as an unhandled `DataError` string via this view's existing
  broad exception handler (F-29's territory, not itself fixed here,
  but this specific symptom is). New `_safe_text_field()` helper
  (`apps/photos/views.py`) strips embedded NUL bytes and truncates to
  fit before the `MediaAsset.objects.create()` call. Verified: a
  400-character filename uploads successfully with a properly
  truncated `original_name`/`title`.

**G. Security headers / production hardening** — inspected
`config/settings/production.py` (Phase 0's own work: HSTS, X-Frame-
Options, nosniff, XSS filter, SSL redirect, proxy headers — all already
correct, confirmed, left untouched) and `frontend/nginx.conf` (serves
the SPA on a separate origin from Django, so Django's own security
headers never covered it). Added, conservatively: `X-Content-Type-Options:
nosniff`, `X-Frame-Options: DENY` (mirrors the backend's own choice),
`Referrer-Policy: strict-origin-when-cross-origin`, `Permissions-Policy:
camera=(), microphone=(), geolocation=()` — repeated in all three
`location` blocks individually (nginx's `add_header` does NOT inherit
into a location block that defines its own `add_header` — a well-known
nginx quirk; verified by inspection of nginx's documented behavior, not
guessed). CSP was subsequently implemented and browser-verified as an
enforced header; see “CSP decision and verification” below. `nginx.conf`
was checked for brace-balance (4/4) but **not** run through `nginx -t` in
this earlier environment (same limitation Phase 0 already documented).

### 5. Private original vs. public derivative security — investigated, decision documented, no code change

**The question**: can a password-protected gallery's derivative assets
(thumbnails, display/medium WebP, video posters/playback MP4) be
fetched directly without an unlocked session?

**Verified by architecture inspection (not guessable-vs-unguessable
hand-waving)**: yes. `PublicMediaStorage` (`apps/core/storage.py`,
Phase 2) deliberately uses `public-read` ACL with `querystring_auth =
False` — permanent, unsigned, CDN-cacheable-forever URLs, by design, for
performance. There is **no view or route in the request path at all**
for these URLs in production (S3/CDN serves them directly) or in dev
(`django.conf.urls.static.static()`, Django's zero-auth static file
server) — meaning there is structurally no code that COULD check a
`ClientSession` for these specific requests, regardless of the gallery's
password-protection state. Even `PublicVideoStreamView`'s existing
session gate only protects the FIRST request for a given URL — in
production it just `HttpResponseRedirect`s to the same public, unsigned
`playback_file` URL, which is exactly as permanently fetchable
afterward as any other derivative once that URL is known.

**Severity analysis**: bounded, not equivalent to "the gallery is fully
public." (1) The sensitive, sellable, full-resolution original is
unaffected — genuinely private, signed, 1-hour-expiring, only ever
reached through an authorized download view; this finding is about
DERIVATIVES only. (2) Exploiting this requires already possessing a
specific derivative's exact UUID-based URL — never sent to any client
who hasn't already passed the password gate — so the realistic attack is
"a legitimately-unlocked client forwards/leaks one specific image link,"
not "anyone can enumerate the gallery." (3) `watermark_enabled`
(verified end-to-end wired: `apps/photos/tasks.py` → `process_image_pipeline`
→ every image derivative) is a real, working, already-available
mitigation a photographer can turn on for a protected gallery, reducing
a leaked derivative to a low-value watermarked preview.

**Decision: accepted as a documented MVP tradeoff, no code change.** A
proper fix (conditional private ACLs based on `is_password_protected`,
re-ACL-on-toggle logic, a new authenticated proxy view for protected-
gallery derivatives, losing CDN caching specifically for protected
galleries) is a genuine, multi-day storage-architecture project — the
Phase 4 instruction's own boundaries ("do not redo CDN architecture...
only if genuinely required," "implement the SIMPLEST production-safe
solution," "do not destroy CDN caching benefits unnecessarily") argue
against building it disproportionately inside this hardening phase, and
the instruction explicitly allows concluding the current strategy is
"acceptable for MVP" as a valid outcome. This is also consistent with
how comparable photo-delivery products in this category generally
behave (a "capability URL" model for in-gallery preview images).
**Flagged as a candidate for a real fix** (CloudFront signed
cookies/URLs scoped specifically to protected galleries) in a future
phase if a customer's threat model requires stronger guarantees than
"the link isn't sent to anyone who hasn't unlocked the gallery."

### 6. Database / cleanup safety

Reviewed every category the instruction lists:
- **Orphaned `MediaAsset` records**: structurally impossible — every
  `MediaAsset.gallery` FK is `on_delete=CASCADE`, so a `MediaAsset` can't
  outlive its `Gallery`. No cleanup needed.
- **Orphaned storage objects**: already handled by the pre-existing
  `post_delete` signal (`apps/photos/signals.py`, untouched) on every
  `MediaAsset` deletion, now reachable in bulk via the new gallery purge
  task's cascade (section 2).
- **Deleted galleries**: `purge_trashed_galleries` (section 2).
- **Expired galleries** (`Gallery.expires_at` passed): reviewed,
  deliberately left alone — client-facing access is already correctly
  gated on this (`PublicGalleryView`'s own `Q(expires_at__isnull=True) |
  Q(expires_at__gt=now)` filter, pre-existing). No product decision
  requests auto-trashing/purging an expired gallery — the photographer
  may want to re-extend it or just view it later — so no destructive
  action was added here without one. Recorded as reviewed, not
  overlooked.
- **Expired `ClientSession`s**: section 4C.
- **`DownloadLog` retention**: new `DOWNLOAD_LOG_RETENTION_DAYS`
  (default 365) + `apps/clients/tasks.py::purge_old_download_logs`
  (weekly). Purely operational trim, no relationship to any active
  security control (unlike ClientSession) — deleting an old log row
  never affects a current or future download.
- **Token blacklist growth**: `rest_framework_simplejwt`'s
  `OutstandingToken`/`BlacklistedToken` tables previously had zero
  cleanup and grow with every login/refresh/logout forever — more so
  now that refresh rotation (section 4A) actually mints a new row on
  every refresh instead of reusing one. New
  `apps/users/tasks.py::flush_expired_jwt_tokens` (weekly) wraps
  simplejwt's own built-in `flushexpiredtokens` management command —
  confirmed it exists and runs cleanly in this environment.

All four new scheduled tasks (`purge_trashed_galleries`,
`purge_expired_client_sessions`, `purge_old_download_logs`,
`flush_expired_jwt_tokens`) registered in `config/celery.py`'s
`beat_schedule` and confirmed discoverable by Celery's own task registry
(`app.tasks.keys()`) alongside the three pre-existing tasks.

### 7. Testing

New test files (8), 40 new tests, all passing:
- `apps/users/tests/test_auth_hardening.py` (5) — refresh rotation mints
  a new token / blacklists the old one / the new one still works;
  password change and password reset each blacklist the pre-change
  refresh token.
- `apps/clients/tests/test_client_session_expiry.py` (4) — fresh session
  grants access, expired session 401s, purge task removes only expired
  rows, purge is idempotent.
- `apps/clients/tests/test_portfolio_privacy.py` (4) — open gallery
  listed, protected gallery's title appears nowhere in the payload,
  staff and superuser accounts both 404.
- `apps/galleries/tests/test_trash_purge_and_quota.py` (10) — default
  free-tier cap is 10, 11th gallery blocked, soft-delete sets
  `trashed_at`, trashed gallery still counts toward BOTH gallery-count
  and storage-byte quota, purge respects the retention window in both
  directions (purges past it, leaves recent trash alone), never purges
  an active gallery, never purges a trashed-with-no-timestamp row, purge
  cascades to `MediaAsset`, purge is idempotent.
- `apps/clients/tests/test_download_hardening.py` (10) — malformed UUID
  → 400 not 500 (plus non-list, plus valid-but-nonexistent, all with no
  `DownloadLog` written), path-traversal filename can't escape a ZIP
  entry, CRLF filename can't break response headers, duplicate filenames
  de-duplicated with both files' actual bytes verified intact, the
  asset-count and total-bytes sync-ZIP guards both reject with a clear
  code and a within-limits request still succeeds.
- `apps/photos/tests/test_upload_security.py` (3) — the crafted
  decompression-bomb PNG is rejected cleanly (400, no `MediaAsset`
  row created), a normal image still uploads, a 400-character filename
  is truncated rather than raising a DB error.
- `apps/clients/tests/test_public_throttling.py` (3) — confirms the
  dedicated scope name, confirms it actually throttles once its own
  (patched) limit is exceeded, confirms ordinary browsing at the real
  default rate is never throttled.

Also fixed 3 pre-existing test-writing mistakes caught by an actual test
run (not assumed correct): two portfolio-privacy tests used a mixed-case
username that could never match the view's own lowercased lookup (the
view's behavior was already correct — `RegisterSerializer` already
lowercases usernames at registration; the test fixture was wrong, not
the code), and the throttle-behavior test's original approach
(`override_settings(REST_FRAMEWORK=...)`) doesn't work against an
already-imported DRF throttle class (documented in the test file itself
once discovered) — switched to `patch.dict` on the throttle's own
`THROTTLE_RATES`.

**Full suite run**: `python manage.py test apps.galleries apps.clients
apps.photos apps.users apps.subscriptions apps.core` — **179 tests, all
passing** (0 failures, 0 errors): confirmed at 139/139 immediately before
adding this phase's new test files, the 40 new tests confirmed passing
together as their own run, and the complete combined suite re-confirmed
at 179/179 as this phase's final check. No regressions in any Phase
0/1/2/3 test.

Also run and clean:
- `python manage.py check` — 0 issues.
- `python manage.py check --settings=config.settings.production`
  (with placeholder `SECRET_KEY`/`AWS_*`/`DEFAULT_FROM_EMAIL` env vars,
  matching the Dockerfile's own build-time pattern) — 0 issues.
- `python manage.py makemigrations --check --dry-run` — clean, both
  before and after the fresh-DB verification below.
- Migrations applied to a genuinely FRESH database
  (`phase4_fresh_check`, created via `psycopg2`, migrated end-to-end,
  re-checked clean, then dropped).
- Migrations applied to the EXISTING dev database (`Kyapture_DB`) —
  `showmigrations` shows zero unapplied across every app.
- Migrations applied to the existing dev database under **production**
  settings — surfaced a real, useful finding: `production.py` adds
  `django_ses` to `INSTALLED_APPS`, which carries its OWN two migrations
  never applied under `development.py` (dev never installs that app).
  Applying them was clean and idempotent (confirmed by running twice).
  This is exactly the class of drift `docker-entrypoint.py` (section 1)
  now handles automatically for a real production container, since it
  runs `manage.py migrate` under whatever `DJANGO_SETTINGS_MODULE` the
  container actually has — recorded here as a verified, not just
  theoretical, production-parity difference (see section 8).
- Frontend: **no `npm run build` was run this phase.** The only
  frontend-tree file touched was `frontend/nginx.conf` (security
  headers, section 4G), which is a static config file copied into the
  Docker image — not part of the Vite build pipeline, not processed or
  bundled — and no `.jsx`/`.js` file changed. Re-running the JS build
  would not exercise anything this phase actually changed.

### 8. Production parity

Differences identified between Windows dev / Linux build / Docker /
staging / production, this session:

- **Settings-module migration drift (new finding, verified above)**:
  `config.settings.production` requires `django_ses`'s own migrations
  that `config.settings.development` never applies. Any environment
  that has only ever run under development settings (like this session's
  dev DB, before this check) is NOT actually migration-parity-clean for
  a production cutover until `migrate` is run at least once under
  production settings. `docker-entrypoint.py` (section 1) makes this
  automatic for any real deployment, but it's worth this session's
  explicit record that dev and prod settings do NOT imply the same
  applied-migration set.
- **Path casing / OS**: this development environment is Windows; the
  Docker image is `python:3.12-slim` (Linux). No path-casing-sensitive
  code was touched this phase (`os.path.basename`/`os.path.splitext`
  behave identically cross-platform for the ASCII paths this app
  generates). Not a new risk surfaced this phase.
- **FFmpeg / Python dependencies**: unchanged this phase — already
  verified present in `backend/Dockerfile` per Phase 0's own findings.
  Not re-verified here (out of this phase's scope — no video/FFmpeg code
  was touched).
- **S3 vs. local disk storage**: unchanged this phase, except that the
  new download-hardening code (section 3) was written and tested to
  behave identically against both (`FileResponse` streams from either
  backend's file-like object the same way; verified against local-disk-
  backed `ContentFile` fixtures in tests, matching how `PublicVideoStreamView`
  already branches on `video_field.storage.__class__.__name__` for the
  same local-vs-S3 distinction).
- **nginx**: `frontend/nginx.conf` changed (security headers, section
  4G) but was not validated with a real `nginx -t` — no nginx binary in
  this environment. Syntax inspected (brace-balanced) only.
- **Docker itself**: still cannot be validated end-to-end in this
  environment (section 1). This remains the single biggest gap between
  "verified in this session" and "verified in the real deployment
  target," and is called out explicitly rather than implied to be done.

### Files changed (Phase 4)

Backend:
- `Dockerfile`, `docker-entrypoint.py` (new), `docker-compose.yml`
- `config/celery.py`, `config/settings/base.py`
- `apps/galleries/models.py`, `serializers.py`, `views.py`, `urls.py`,
  `tasks.py` (new)
- `apps/clients/models.py`, `views.py`, `tasks.py` (new)
- `apps/photos/views.py`
- `apps/core/utils.py`
- `apps/users/views.py`, `serializers.py`, `utils.py` (new), `tasks.py`
  (new)
- New migrations: `galleries/0007_...`, `galleries/0008_backfill_trashed_at.py`
  (data migration)
- New test files listed in section 7 above

Frontend:
- `frontend/nginx.conf` only (security headers) — no `.jsx`/`.js` files
  touched this phase.

### Unresolved / explicitly deferred items

- **Docker end-to-end validation** (section 1) — the one item this
  phase could not verify directly; recommend as the literal final
  sign-off step on a machine with a Docker daemon.
- **Content-Security-Policy for the frontend** (section 4G) — considered,
  deliberately not added without real browser verification.
- **Protected-gallery derivative URL exposure** (section 5) — accepted
  as a documented MVP tradeoff; flagged for a future phase if a
  customer's threat model needs stronger guarantees.
- **F-29** (raw internal-error-string leakage in `PhotoListUploadView`'s
  broad exception handler) — noted where directly relevant (section 4F's
  filename-length fix removes ONE trigger of it) but not fixed wholesale;
  out of this phase's explicit scope (not one of the enumerated Phase 4
  items) and flagged here so it isn't lost.
- **Expired-gallery auto-cleanup** — reviewed, deliberately not built
  (section 6) pending an actual product decision to trash/purge on
  expiry rather than just gating client access.

### Exact next phase

With deployment migration safety, storage/quota integrity, download
hardening, auth hardening, and DB cleanup all closed, the concrete
remaining pre-launch items are: (a) the literal Docker end-to-end
build/run validation this environment couldn't perform, (b) a real
browser-based QA pass (visual/interaction testing was out of scope for
every backend-focused phase so far, including this one), and (c)
whatever UI/launch QA phase was already implied by this phase's own
title ("...before final UI/launch QA"). No further backend production-
risk items are known to remain open beyond what's explicitly listed as
deferred above.

---

## Phase 5 — Real production-parity + browser QA (2026-09-30)

### Status

**COMPLETE for the repository's local Linux/Docker runtime.** The Compose
manifest is intentionally dev-shaped (`runserver`, live mounts, local disk),
so this validates the real containerized application path and service
communication; a credentialed staging deployment using production settings and
S3/CDN remains environment-specific work.

### Docker result

- Docker CLI 29.8.1 and Docker Compose v5.5.1 were available, and the daemon
  was reachable.
- `docker compose config`, `docker compose build`, and `docker compose up -d`
  succeeded from the repository.
- Backend, Celery worker, Celery beat, and frontend images built successfully.
- PostgreSQL and Redis became healthy; backend and nginx frontend became
  healthy; the worker connected to `redis://redis:6379/0` and registered the
  media-processing tasks; beat started with the same broker.
- Backend `/health/` returned HTTP 200. Nginx served both `/dashboard` and a
  deep SPA route with HTTP 200 and the expected `index.html` fallback.

### Migration safety

- The first startup used a fresh named PostgreSQL volume and ran migrations
  through the container entrypoint before the services started.
- Backend, worker, and beat each ran the entrypoint migration path against the
  same database. The current database contains 51 applied migration records.
- A service restart and a full `docker compose down`/`up -d` restart both
  reported `No migrations to apply`; all services returned successfully.
- `manage.py check` passed and `makemigrations --check --dry-run` remained
  clean.
- Production-settings `manage.py check` passed with non-production placeholder
  values. Without `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, and
  `AWS_STORAGE_BUCKET_NAME`, production settings correctly refuse to start;
  real S3 credentials were not available for this local validation.

### Real media/runtime smoke tests

Inside the backend container, Pillow 12.2.0, blurhash, piexif, Celery 5.6.3,
and FFmpeg 7.1.5 were available. Real HTTP upload flows returned 202 and
completed asynchronously:

- Image: upload → Celery processing → READY → thumbnail/display derivatives;
  original, display, and thumbnail files were present in the shared media
  volume.
- Video: upload → processing → READY → poster and playback derivatives;
  original, poster, and playback files were present.
- Originals were retained for authorized photographer/download paths and were
  not exposed as the public gallery serializer's media URLs.

### Real HTTP/API golden paths

Verified against the running stack with actual HTTP responses and database
state: register/login, gallery create/update, image upload and processing,
gallery list, public gallery, photo sets, assignment and reorder, favorites,
download PIN enforcement, web-size ZIP download, single-photo download,
download activity, expiration returning 404, trash/delete, and free-tier
quota enforcement. The observed quota flow allowed the first 10 galleries and
rejected the 11th with HTTP 403.

### Browser QA result

Rendered QA passed using the in-app browser against `http://localhost:3000`:

- Photographer login, dashboard, gallery management, design settings, upload,
  sets/reorder controls, activity views, download settings, and trash controls
  rendered and navigated.
- Client cover, gallery grid, real image loading, lazy-loaded grid behavior,
  favorites control, download entry points, slideshow controls, and protected
  gallery password states rendered.
- Invalid/expired-style public gallery state showed the expected not-found
  message; wrong password showed the expected inline error.
- Mobile viewport (390×844) rendered without visible horizontal overflow.
- Browser console error/warning collection was empty after a gallery reload.
- Using `127.0.0.1` while the built frontend is configured for `localhost`
  reproduced a cookie-origin mismatch; the configured localhost pair passed.
  This is a development host-pair constraint, not a production hostname
  defect.

### Fixes made during Phase 5

- Compose now uses container service names and health-gated dependencies for
  PostgreSQL and Redis, with matching non-eager Celery settings for web,
  worker, and beat.
- Added the database-backed backend health endpoint and frontend/backend
  healthchecks.
- Added port-3000 CORS/CSRF development origins.
- Removed build-time AWS placeholder values from the runtime image so local
  Compose correctly uses filesystem storage.
- Corrected container `MEDIA_ROOT`/`STATIC_ROOT` resolution so `/app/media`
  is shared by web and worker and collected static files use `/app/staticfiles`.
- Fixed F-29 upload exception leakage: validation errors now use safe
  structured responses; database/system failures are logged server-side and
  return stable public error codes without storage paths or provider details.

### Known issues and launch classification

- **F-29 upload exception leakage — FIX BEFORE MVP: fixed and rechecked.**
- **Content-Security-Policy — FIX BEFORE MVP: fixed and verified.** An
  enforced, browser-verified allowlist is configured in `frontend/nginx.conf`.
- **Protected-gallery public derivative URL exposure — REQUIRES PRODUCT AND
  STORAGE ARCHITECTURE DECISION.** The current API gate and download/stream
  endpoints were preserved; signed-CDN/proxy derivative protection was not
  introduced because it could break the current client flow.
- **Per-photo download PIN UX — SAFE TO DEFER / REQUIRES PRODUCT DECISION.**
  Full-gallery and selected downloads expose the PIN form. Per-photo links
  are intentionally hidden when a gallery PIN is configured rather than
  presenting a dead unauthenticated link; deciding whether to add an inline
  PIN flow is deferred.
- **Expired-gallery cleanup policy — SAFE TO DEFER.** The existing 30-day
  trash retention and daily Celery beat purge task are present and registered;
  the access gate is already verified by the 404 smoke test.
- **Frontend large chunk — SAFE TO DEFER.** The clean Docker Vite build passed
  with one advisory 657.83 kB pre-gzip JavaScript chunk warning. No clear
  production failure was demonstrated, so no bundler rewrite or speculative
  code split was made.

### Remaining launch blockers

No new P0/P1 issue remains in the validated Docker/local stack. The remaining
items are the explicitly classified protected-derivative/per-photo-PIN
decisions and a credentialed staging verification of production settings,
S3/CDN URLs, TLS cookies, and the production process manager.

### Exact next phase

**Phase 6 — Launch hardening and decision closure:** CSP is enforced and
browser-verified; choose the protected-derivative storage policy and per-photo
PIN UX, then run
credentialed staging smoke tests with production settings/S3/CDN. Do not begin
UI redesign until those launch decisions are closed.

---

## Phase 6 — Launch hardening + decision closure (2026-09-30)

### Status

**COMPLETE for local Docker launch hardening; production release sign-off is
still conditional on credentialed staging/S3/TLS verification.** No UI redesign
or unrelated product feature work was started.

### CSP decision and verification

The actual frontend/runtime inventory found:

- same-origin Vite/nginx scripts and CSS;
- inline React style attributes, requiring `style-src 'unsafe-inline'`;
- Google Fonts CSS and font files from `fonts.googleapis.com` and
  `fonts.gstatic.com`;
- API/media traffic to local `http://localhost:8000` in Compose and the
  production API hostname `https://api.kyapture.com`;
- public S3 derivative URLs using the configured default `us-east-1` region;
- `data:` and `blob:` image sources for BlurHash/preview behavior;
- no production WebSocket, plugin, iframe, object, or inline-script source.

Implemented a narrow enforced CSP in `frontend/nginx.conf`:

```text
default-src 'self'; base-uri 'self'; object-src 'none'; frame-ancestors 'none';
form-action 'self'; script-src 'self';
style-src 'self' 'unsafe-inline' https://fonts.googleapis.com;
font-src 'self' https://fonts.gstatic.com data:;
img-src 'self' data: blob: http://localhost:8000 https://api.kyapture.com
  https://*.s3.amazonaws.com https://*.s3.us-east-1.amazonaws.com;
media-src 'self' http://localhost:8000 https://api.kyapture.com
  https://*.s3.amazonaws.com https://*.s3.us-east-1.amazonaws.com;
connect-src 'self' http://localhost:8000 https://api.kyapture.com;
```

Verification passed: clean frontend Docker build, `nginx -t`, HTTP 200 with the
CSP header, rendered cover and API-backed grid image in the real browser, and
zero browser error/warning diagnostics. A production deployment using a
different S3 region or custom media domain must add that exact host to the
policy before deployment; no such staging domain was available here.

### Protected-gallery derivative decision

Rechecked with a disposable published password-protected gallery:

- unauthenticated gallery metadata returned the password gate;
- after unlock, the public serializer returned a stable derivative URL;
- the derivative itself returned HTTP 200 without the gallery token;
- the original download endpoint returned HTTP 401 without the unlocked
  session.

**Final MVP decision: retain the existing public-derivative capability-URL
tradeoff; do not rewrite storage/CDN architecture in Phase 6.** This preserves
stable cacheable CDN derivatives and keeps full-resolution originals behind
the session/download authorization path. The residual risk is explicit: a
client who has already unlocked a gallery can forward an exact derivative URL.
If the product promise changes to “password-protected previews cannot be
forwarded,” this becomes a launch blocker requiring private protected-gallery
derivatives or signed-cookie/proxy architecture; that is not a safe one-line
patch and was not invented here.

### Per-photo download PIN decision

Verified with a disposable PIN-enabled gallery and the real browser/API:

- the browser renders `Download Full Gallery`, but no single-photo download
  button when a PIN is configured;
- missing or incorrect bulk PIN returns HTTP 401;
- correct bulk PIN returns HTTP 200 ZIP;
- missing single-photo PIN returns HTTP 401;
- correct single-photo PIN returns HTTP 200 media.

**Final MVP decision: keep the current minimal UX.** The client must use the
existing bulk/selected download PIN form; hiding per-photo/video links avoids a
dead link and raw JSON error page. An inline per-photo PIN modal is deferred
until product explicitly requires that interaction.

### Credentialed staging verification

Available and verified locally in the actual Docker runtime:

- production Django settings system check with non-production placeholder
  values;
- PostgreSQL readiness, Redis readiness, Celery worker/beat startup;
- migrations-before-command through the real production-settings Compose
  entrypoint;
- development and production migration drift checks;
- local filesystem media processing for image/video derivatives;
- nginx syntax, frontend build, SPA fallback, browser rendering, cookies,
  CORS/CSRF behavior on the configured localhost pair.

The production-settings entrypoint initially found two pending `django_ses`
migrations, applied them before the command ran, and a subsequent production
`migrate --plan` reported no planned operations. The database then contained
53 migration records.

Unavailable and intentionally not faked:

- real S3 credentials/bucket, so S3 ACLs, signed original URLs, public S3/CDN
  derivative URLs, and S3-backed media processing were not verified;
- real TLS termination/reverse proxy, so Secure-cookie behavior and forwarded
  HTTPS CSRF behavior were inspected in settings but not exercised through a
  live HTTPS staging proxy;
- production process manager/gunicorn and deployment DNS/certificate wiring.

### Final checks

- Backend suite: **179/179 passed** in an isolated test container with Celery
  eager mode enabled for deterministic task tests. The running Compose stack
  remains correctly non-eager; the same suite without test eager mode had five
  expected async-test isolation failures because those tests dispatch to the
  live Redis worker instead of the test database.
- Frontend production Docker build: **PASS**; existing 657.83 kB chunk advisory
  remains, with no speculative bundler rewrite.
- `makemigrations --check --dry-run`: **PASS**; production `migrate --plan`:
  **no planned operations** after the entrypoint migration check.
- Production Django system check with placeholder environment values: **PASS**.
- Browser CSP/media/PIN smoke checks: **PASS**, with no console errors or
  warnings.
- nginx configuration test and `git diff --check`: **PASS**.

### Fixes made in Phase 6

- Added and verified the enforced CSP in `frontend/nginx.conf`.
- Added the generated Celery beat schedule file pattern to `.gitignore`.
- No protected-derivative architecture or per-photo PIN modal was added;
  both decisions intentionally preserve the current MVP behavior.

### Remaining blockers

1. **Credentialed staging verification is the only operational launch blocker:**
   real S3/CDN, TLS/proxy cookies/CSRF, production hostname, and production
   process-manager behavior still need a staging environment with real
   credentials.
2. The protected-derivative tradeoff is an accepted MVP risk, not a hidden
   defect. It becomes a blocker only if product requires strict non-forwardable
   protected previews.
3. The CSP must be adjusted before production if the real S3 region/media host
   differs from the verified allowlist.

### Exact next phase

**Phase 7 — Credentialed staging sign-off:** run the same checks against the
real production-like hostname, TLS proxy, PostgreSQL/Redis, S3 bucket/CDN, and
process manager; validate signed original URLs and the finalized CSP host list.
Do not begin UI redesign until staging sign-off or an explicit launch-risk
acceptance is recorded.

### Phase 7 — Photo Sets V2, cover, and client-gallery completion (local)

- **Runtime root cause and containment:** local create-set requests originally
  hit an unapplied `photos.0004_photoset_v2_delta` migration (the database
  lacked `photo_sets.description`), yielding Django DEBUG HTML. The migration
  is now applied; unexpected `/api/` exceptions are returned as a safe JSON
  error and the frontend normalizes any non-JSON/HTML response before surfacing
  its normal toast/modal message.
- **Photo Sets V2:** the workspace owns the single real set list and active
  ID, synchronizes `?set=<id>` with valid-first-set fallback, and supplies it
  to the sidebar/content page. The sidebar uses real names/counts with
  create/rename/description/delete/reorder controls; the duplicate content
  set-management bar is gone. Active-set uploads send `set_id` and refresh
  sidebar counts.
- **Default cover:** the existing race-safe conditional update remains
  `cover_photo IS NULL`. READY retry/replay paths for both images and videos
  now also call it, backfilling historic missing covers without ever replacing
  a manually selected cover. Image and video regressions cover backfill,
  first-winner behavior, and manual-cover preservation.
- **Client gallery:** real cover/title/shop metadata and URL-backed real set
  navigation feed a larger, responsive editorial masonry grid while retaining
  favorites, download permission/PIN behavior, the existing lightbox, and
  slideshow path. No placeholder set names/counts or fake action controls were
  introduced.
- **Browser smoke verification:** local photographer flow verified real
  create/rename/description selection, URL persistence, active-set uploads,
  count refresh, empty-to-grid transition, default cover assignment, manual
  cover override, and READY replay protection. Public-gallery verification
  covered real cover/title/shop data, set filtering/counts, 390px navigation
  without horizontal overflow, favorites and the lightbox/slideshow path; no
  Photo Sets console errors were observed. The automation provider could
  activate the dropzone chooser but not the header file chooser; the normal
  header wiring remains unchanged. Destructive sidebar deletion was covered by
  the API suite rather than deleting local smoke data through automation.
- **Final local validation:** full Django suite **192/192 passed** (eager local
  settings); targeted video cover regressions **10/10 passed**;
  `makemigrations --check --dry-run` passed; Vite production build passed;
  `git diff --check` passed. The existing Vite >500 kB chunk advisory remains
  non-blocking.
