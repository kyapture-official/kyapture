# KYAPTURE — Execution State

_Last updated: Phase 1 completion (this session)._

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
- `get_user_subscription_metrics()`'s free-tier `max_galleries` default is
  still `None`, not the locked decision's `10` — noted in the verified
  plan as Phase 4 work, untouched here.
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
