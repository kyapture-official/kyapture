# Kyapture Frontend — Update Log

---

## Date: 21 September 2026

### 1. PixiesetContext — Global Gallery State

Created `context/PixiesetContext.jsx` (247 lines). Centralizes gallery workspace state via
`useReducer` with 13 action types (UPDATE_META, ADD_PHOTOS, SET_PHOTOS, REMOVE_PHOTO,
SET_COVER, UPDATE_SETS, UPDATE_DESIGN, UPDATE_SETTINGS, PUBLISH, UNPUBLISH, ADD_TOAST,
REMOVE_TOAST). Exposes context provider + `usePixieset` hook. Currently consumed by
`TopNavBar.jsx` (publish/unpublish/addToast) and `GalleryWorkspaceLayout.jsx` (dispatch).

**Note:** Over-engineering audit flagged this — only 4 of 13 actions are used. Could be
replaced with zustand atoms or simple props when time permits.

---

### 2. TopNavBar — Collection Header Bar

Created `components/layout/TopNavBar.jsx`. Breadcrumb navigation (← Back / Galleries /
Collection Title), published/draft status badge dropdown, Preview button triggering
`open-preview` custom event, Share dropdown (copy link), More dropdown (Rename, Duplicate,
Download, Delete). Reads publish state from PixiesetContext.

---

### 3. GallerySecondarySidebar — Icon Navigation

Refactored `components/layout/GallerySecondarySidebar.jsx` from a wide text-based sidebar
to a narrow 72px dark icon sidebar. Sections: Photos / Design / Settings / Activities nav
with active state indicators. Back button at top. Matches Pixieset's workspace navigation
pattern.

---

### 4. GalleryWorkspaceLayout — Workspace Shell

Refactored `pages/dashboard/GalleryWorkspaceLayout.jsx`. Wrapped in `PixiesetProvider`.
Syncs gallery data (title, slug, status, photos) into context via useEffect. Listens for
`open-preview` custom event to trigger ClientPreviewModal. Contains TopNavBar +
SecondarySidebar + `<Outlet />` for nested routes.

---

### 5. GalleryDesignPage — 4-Tab Design Builder

Refactored `pages/dashboard/GalleryDesignPage.jsx`. Four tabs: Cover (hero layout, overlay
opacity), Typography (font family, heading/body sizes), Color (branding color, background,
text color), Grid (columns, gap, aspect ratio). Each tab has sub-options with live preview
panel showing changes in real-time.

---

### 6. GallerySettingsPage — 5-Tab Settings

Refactored `pages/dashboard/GallerySettingsPage.jsx`. Five tabs: General (title, slug,
description, event date), Privacy (password protection, hide from search, allow indexing),
Download (allow downloads, require email, watermarks), Favorites (enable favorites, show
count), Store (enable print store, pricing). All toggles, forms, and save buttons wired.

---

### 7. ActivitiesWorkspace — Activity Tracker

Created `pages/dashboard/ActivitiesWorkspace.jsx` (new). Seven tabs: All Activity,
Downloads, Favorites, Shares, Comments, Views, Settings. Download categories (full-res,
web-res, prints). Stats grid with icons. Empty states per tab. Added `/activities` route
under gallery workspace in `App.jsx`.

---

### 8. ClientPreviewModal — Sticky Header & Scroll Behavior

Refactored `components/shared/ClientPreviewModal.jsx`. Key changes:
- **Hero:** Changed from `h-screen` to `h-[85vh]` with `id="hero"` scroll target.
- **Sticky header:** Locks to top when scrolled past hero (`sticky top-0 z-50 bg-white
  border-b border-gray-200 shadow-sm px-6 py-3`). Left: title + photographer stacked.
  Right: Favorite, Download, Share, Grid toggle, Close (`space-x-6`).
- **"BACK TO TOP" button:** Added below photo grid, smooth-scrolls `containerRef` to top.
- Scroll detection via `handleScroll` callback resets `scrolledPastHero` state.

---

### 9. ERR_CONNECTION_REFUSED — API Connectivity Fix

Root cause: `frontend/.env.local` defined `VITE_API_URL` but `axiosInstance.js` reads
`VITE_API_BASE_URL`. Env var was silently ignored, falling back to `/api/v1`. Duplicate
keys in `.env.local` also caused confusion.

**Fixes applied:**
| File | Change |
|------|--------|
| `frontend/.env.local` | Replaced with single `VITE_API_BASE_URL=/api/v1` |
| `frontend/vite.config.js` | Added `/media` proxy target → `localhost:8000` |
| `frontend/src/api/axiosInstance.js` | Falls back to `VITE_API_URL` if `VITE_API_BASE_URL` missing. Added `ERR_NETWORK` interceptor logging startup command. |
| `frontend/src/pages/dashboard/GalleriesPage.jsx` | `handleCreateSubmit` catches `ERR_NETWORK` and shows "Cannot reach the server" toast. |

Backend confirmed running (401 on direct hit to `localhost:8000/api/v1/galleries/`).

---

### 10. Over-Engineering Audit (Updated)

Full codebase re-scan. Previous findings from Sep 15 updated with new state.

**Verified dead code / removable:**

| Tag | What to Cut | Lines | File(s) |
|-----|------------|-------|---------|
| `delete` | PixiesetContext — 13-action reducer, only 4 used by 2 consumers | 247 | `context/PixiesetContext.jsx` |
| `delete` | `_ALLOWED_SIGNATURES` — defined, never referenced | 7 | `core/utils.py:137-143` |
| `delete` | `debug_task` — unregistered Celery stub | 4 | `config/celery.py:44-47` |
| `delete` | `StandardResultsSetPagination` + `LargeResultsSetPagination` — never imported | 14 | `core/pagination.py` |
| `delete` | `IsPhotographer` permission — never imported | 17 | `core/permissions.py` |
| `delete` | `validateSubdomain` — exported, never imported | 29 | `utils/validator.js:15-43` |
| `delete` | `constants.js` — all exports (BASE_URL, MEDIA_URL, PAYMENT_METHODS, SUBSCRIPTION_STATUS_COLORS) never imported | 17 | `utils/constants.js` |
| `delete` | `getPublicGallery` + `verifyPassword` aliases — never called | 2 | `api/clientsApi.js:169,198` |
| `delete` | `photosApi.upload` backward-compat alias — dead | 3 | `api/photosApi.js:244-246` |
| `stdlib` | `generate_secure_token` wrappers — duplicate `secrets` module | 2×5 | `core/utils.py:72-77`, `clients/models.py:7-12` |
| `stdlib` | `hex_color_validator` — identical in two models | 2×4 | `galleries/models.py:8-11`, `users/models.py:11-14` |
| `stdlib` | `assertNonEmptyString` — duplicated in two API modules | 2×8 | `api/photosApi.js:48-57`, `api/clientsApi.js:20-27` |
| `stdlib` | `slugify` in useGalleries — reinvents django slug | 7 | `hooks/useGalleries.js:26-32` |
| `stdlib` | `generateMockUUID` — `crypto.randomUUID()` is native | 7 | `hooks/useGalleries.js:13-19` |
| `shrink` | `DashboardStatsView` — 3 near-identical return blocks | ~50 | `galleries/views.py:269-372` |
| `shrink` | `get_gallery()` — copy-pasted across 5 public views | 5×20 | `clients/views.py` |
| `shrink` | `get_session_token` + `validate_session_token` — duplicated | 2×20 | `clients/views.py:73-95,402-411` |
| `shrink` | `validate_branding_color` — identical in Create + Update serializers | 2×5 | `galleries/serializers.py:152-156,245-249` |
| `shrink` | `_get_client_ip` — duplicated in views + serializers | 2×5 | `clients/views.py:227-231`, `clients/serializers.py:210-217` |
| `shrink` | `getAlphaBrandingColor` — re-defined inline instead of importing | 8 | `pages/client/ClientGalleryPage.jsx:17-24` |
| `shrink` | `triggerGlobalLogout` — manual localStorage surgery vs zustand | 17 | `api/axiosInstance.js:122-138` |

**Net removable:** ~770 lines, 7 duplicate patterns to consolidate, 0 dependencies removable (framer-motion used in 8 files, prop-types in 1).

---

## Date: 15 September 2026

### What Was Done Today

### 1. Design System Migration — Cream → Slate/Teal

Complete palette overhaul across the entire codebase. Replaced the warm cream/gold design
system (`#faf7f2`, `#c17f3e`, `#1e1a16`) with the dark slate/teal language matching the
landing page (`#0f172a`, `#0D9488`, `slate-*` tokens). Zero functional changes — pure
styling refactor.

**Palette Mapping:**

| Old Token | New Token | Usage |
|-----------|-----------|-------|
| `cream-50` `#faf7f2` | `slate-50` `#f8fafc` | Page background |
| `cream-100` `#f3ede3` | `slate-100` `#f1f5f9` | Card hover, subtle fills |
| `cream-200` `#e8ddd0` | `slate-200` `#e2e8f0` | Borders, dividers |
| `cream-300` `#d4c4b0` | `slate-300` `#cbd5e1` | Input borders |
| `ink` `#1e1a16` | `slate-900` `#0f172a` | Primary text, dark bg |
| `muted` `#9a8b7c` | `slate-500` `#64748b` | Secondary text, labels |
| `accent` `#c17f3e` | `teal-600` `#0D9488` | Active states, CTAs |
| `green` `#4a7c6f` | `emerald-500` `#10b981` | Success, published |

**Files Modified (22 files):**

| File | What Changed |
|------|-------------|
| `tailwind.config.js` | Updated `ink`, `muted`, `accent`, `green` token values; updated all `boxShadow` from warm to neutral |
| `src/styles/index.css` | Updated all CSS variables (`:root`), body, scrollbar, buttons, forms, cards, pills, modal, toggle, skeleton, dashboard layout, stats, auth page, navbar, hero, sections, features grid, CTA band, footer |
| `DashboardLayout.jsx` | Mobile nav bar → white with slate borders; mobile drawer → dark slate-900; desktop sidebar → slate-900 with teal accents; topbar → teal glow search; user avatars → teal solid; nav active states → teal |
| `Button.jsx` | Primary → `bg-teal-600`; secondary → `bg-slate-100`; ghost → `hover:bg-slate-100`; outline → `border-slate-300`; focus ring → `ring-teal-500` |
| `Input.jsx` | Border → `border-slate-200`; placeholder → `text-slate-400`; focus ring → `ring-teal-500` |
| `Modal.jsx` | Backdrop → `bg-slate-900/40`; card → `bg-white border-slate-200`; close hover → `bg-slate-100`; focus ring → `ring-teal-500` |
| `Toast.jsx` | Success icon → `text-emerald-500`; info/loading → `bg-slate-50 border-slate-200` |
| `Badge.jsx` | Default → `bg-slate-100 border-slate-200` |
| `DropZone.jsx` | Borders → `slate-*`; icon/text → `slate-*`; dragging → `teal-*`; focus ring → `ring-teal-500` |
| `HomePage.jsx` | Stat card gradients → teal/emerald/blue/violet; greeting hero → slate gradient; subscription card → emerald/slate; gallery cards → slate borders; buttons → teal |
| `GalleriesPage.jsx` | Create button → `bg-teal-600`; search → `slate-200`/teal focus; empty state → slate; gallery grid → `border-slate-200`; spinner → `text-slate-400` |
| `SettingsPage.jsx` | Profile card → `border-slate-200`; icon bg → teal/blue/violet; textarea → teal focus; color input → slate; email → slate bg; logo upload → slate |
| `BillingPage.jsx` | Subscription section → slate; plan cards → slate/teal selected; active badge → emerald; form → slate/teal; file input → slate; submit → `bg-teal-600`; payment table → slate |
| `GallerySettingsPage.jsx` | Card borders → `border-slate-200`; icon bg → teal/blue; form inputs → slate/teal focus; checkboxes → `border-slate-300 text-teal-600`; save button → `bg-teal-600`; badges → emerald/amber |
| `GalleryPhotosPage.jsx` | Card border → `border-slate-200`; icon bg → teal; upload icon → slate; queue items → slate |
| `GalleryWorkspaceLayout.jsx` | Bg → `bg-slate-50`; nav border → `border-slate-200`; publish button → teal/slate; breadcrumb chevron → slate-400 |
| `GalleryCard.jsx` | Card border → `border-slate-200`; cover bg → `bg-slate-100`; badges → emerald/amber; text → slate; action buttons → slate; manage link → slate |
| `SubscriptionGrid.jsx` | Spinner → `text-slate-400`; section borders → `border-slate-200`; label text → `text-slate-500`; progress bg → `bg-slate-100`; plan badge → teal |
| `CollectionSidebar.jsx` | Loading skeleton → `bg-slate-100`; sidebar border → `border-slate-200`; nav active → teal; cover border → `border-slate-200`; back link → slate |
| `ClientLayout.jsx` | Bg → `bg-slate-50`; header border → `border-slate-200`; footer border → `border-slate-200` |
| `ClientHomePage.jsx` | Bg → `bg-slate-50`; avatar ring → `ring-slate-200`; card borders → `border-slate-200`; cover → `bg-slate-100` |
| `ClientGalleryPage.jsx` | Loading/404/error states → `bg-slate-50`; empty state → `border-slate-200 bg-slate-50` |
| `PricingPage.jsx` | Full rewrite: bg → `bg-slate-50`; header → white/slate; logo → teal; nav → slate; pricing cards → slate-900/slate-200; accents → teal; buttons → teal/slate |
| `PasswordModal.jsx` | Card → `border-slate-200`; input → `border-slate-200 bg-slate-50/30 focus:border-teal-500`; toggle → slate; submit → `bg-teal-600`; spinner → `text-slate-400` |
| `PhotoGrid.jsx` | Thumbnails → `bg-slate-100`; focus ring → `ring-teal-500`; broken/processing → `bg-slate-100`; hover → `bg-slate-100` |
| `PublicMasonryGrid.jsx` | Placeholder → `bg-slate-100`; error → `bg-slate-200`; text → `text-slate-400`; lazy load → `bg-slate-100` |
| `ProtectedRoute.jsx` | Loading bg → `bg-slate-50` |
| `colorhelper.js` | Fallback color → `#0D9488` (was `#c17f3e`) |

**Build:** Compiles clean. CSS reduced by ~2.6KB (91KB vs 93KB) from removing unused cream token rules.

---

### 2. Over-Engineering Audit

Full codebase scan for dead code, reinvented utilities, and speculative features.
Audited ~12,000 lines across 58 source files.

**Findings (ranked by cut size):**

| Tag | What to Cut | Lines | Replacement | File(s) |
|-----|------------|-------|-------------|---------|
| `yagni` | `useGalleries` hook — zero imports anywhere | ~311 | Delete file. Pages call API directly | `hooks/useGalleries.js` |
| `delete` | `mockGalleries.js` + all `USE_MOCK_DATA` branches | ~212 | Delete. Live API works | 4 files |
| `native` | Modal hand-rolls focus trap/scroll lock | ~120 | `<dialog>` element | `ui/Modal.jsx` |
| `shrink` | PasswordModal 400 lines — half is focus plumbing | ~200 | `<dialog>` + Lucide icons | `shared/PasswordModal.jsx` |
| `shrink` | DashboardLayout 11 hand-drawn SVG icons | ~55 | Lucide (already installed) | `layout/DashboardLayout.jsx` |
| `native` | Toast 5 hand-drawn SVG icons | ~45 | Lucide (already installed) | `ui/Toast.jsx` |
| `shrink` | PhotoGrid + PublicMasonryGrid duplicate icons | ~40 | Extract shared or use Lucide | 2 files |
| `yagni` | `BrandLogo.jsx` — never imported | full file | Delete | `landing/BrandLogo.jsx` |
| `yagni` | `prop-types` in one file only | ~7 | Delete import + block | `shared/PasswordModal.jsx` |
| `stdlib` | `toDateInputValue` reinvents date slicing | ~5 | `.toISOString().slice(0,10)` | `utils/formatters.js` |
| `delete` | `useAuth.js` — 2-line re-export, zero consumers | ~2 | Delete | `hooks/useAuth.js` |
| `stdlib` | `useIsomorphicLayoutEffect` in Vite-only SPA | ~3 | `useLayoutEffect` | `ui/Toast.jsx` |
| `native` | `react-intersection-observer` for one hook call | -1 dep | Native `IntersectionObserver` | `shared/PublicMasonryGrid.jsx` |

**Net removable:** ~1,000 lines + 1 dependency (`react-intersection-observer`) + 3 files (`useGalleries.js`, `useAuth.js`, `BrandLogo.jsx`)

---

## Design System Reference

| Token | Value | Usage |
|-------|-------|-------|
| `slate-50` | `#f8fafc` | Page background |
| `slate-100` | `#f1f5f9` | Card hover, subtle fills |
| `slate-200` | `#e2e8f0` | Borders, dividers |
| `slate-300` | `#cbd5e1` | Input borders |
| `slate-900` | `#0f172a` | Primary text, dark bg (sidebar) |
| `teal-600` | `#0D9488` | Active states, CTAs, brand |
| `emerald-500` | `#10b981` | Success, published |
| `font-serif` | Cormorant Garamond | Headings, titles |
| `font-sans` | Outfit | Body text, UI elements |

---

## Dependencies (Production)

| Package | Version | Purpose |
|---------|---------|---------|
| react | 18.2 | UI framework |
| react-dom | 18.2 | DOM renderer |
| react-router-dom | 6.x | Client-side routing |
| zustand | 4.x | State management |
| axios | 1.6 | HTTP client |
| lucide-react | 1.44 | Icon library |
| framer-motion | 13.x | Landing page animations |
| blurhash | 2.0 | Image placeholder hashes |

**Removable:** `react-intersection-observer` (native IntersectionObserver suffices)

---

## Frontend Project Structure

```
frontend/
├── .env                          (17 lines)   Environment variables
├── .env.local                    (2 lines)    Local overrides (gitignored)
├── Dockerfile                    (13 lines)   Production container
├── index.html                    (18 lines)   Vite entry HTML
├── package.json                  (30 lines)   Dependencies & scripts
├── postcss.config.js             (7 lines)    PostCSS + Tailwind plugin
├── tailwind.config.js            (77 lines)   Design tokens, animations, shadows
├── vite.config.js                (20 lines)   Vite dev/build config + proxy
│
└── src/
    ├── main.jsx                  (10 lines)   React root mount
    ├── App.jsx                   (78 lines)   Route definitions, providers
    │
    ├── api/                                   HTTP clients (Axios wrappers)
    │   ├── axiosInstance.js       (120 lines)  Axios instance, CSRF, 401 refresh, ERR_NETWORK
    │   ├── authApi.js             (100 lines)  Login, register, logout, profile
    │   ├── galleriesApi.js        (218 lines)  CRUD, publish, password, search
    │   ├── photosApi.js           (226 lines)  Upload, delete, reorder, poll
    │   ├── clientsApi.js          (207 lines)  Public gallery, password unlock
    │   └── subscriptionsApi.js    (64 lines)   Plans, payment history
    │
    ├── store/                                  Zustand state management
    │   ├── authStore.js           (123 lines)  User session, JWT, localStorage
    │   └── clientStore.js         (76 lines)   Client session, sessionStorage
    │
    ├── hooks/                                  Custom React hooks
    │   ├── useAuth.js             (2 lines)    DEAD — zero consumers
    │   ├── useGalleries.js        (277 lines)  DEAD — zero consumers
    │   └── useSubscription.js     (101 lines)  Plan status, limits, billing
    │
    ├── utils/                                  Pure functions, helpers
    │   ├── formatters.js          (80 lines)   Date, currency, bytes, URL builders
    │   ├── validator.js           (64 lines)   Subdomain, email, username validation
    │   ├── colorhelper.js         (20 lines)   Alpha hex color appender
    │   ├── blurhashDataUrl.js     (41 lines)   BlurHash → PNG data URL decoder
    │   ├── constants.js           (15 lines)   DEAD — all exports unused
    │   └── mockGalleries.js       (107 lines)  DEAD — mock data (dev only)
    │
    ├── styles/
    │   └── index.css              (~1100 lines) Global CSS, design tokens, animations
    │
    ├── components/
    │   ├── ui/                                Primitive UI components
    │   │   ├── Badge.jsx          (33 lines)   Status badge (success/warning/danger)
    │   │   ├── Button.jsx         (103 lines)  Button with variants, loading, aria
    │   │   ├── DropZone.jsx       (187 lines)  Drag-and-drop file upload
    │   │   ├── Input.jsx          (77 lines)   Form input with label/hint/error
    │   │   ├── Modal.jsx          (165 lines)  Portal modal with focus trap
    │   │   ├── Spinner.jsx        (54 lines)   SVG arc spinner
    │   │   └── Toast.jsx          (190 lines)  Toast notification system
    │   │
    │   ├── layout/                            Page shells
    │   │   ├── DashboardLayout.jsx (490 lines) Sidebar + topbar + mobile drawer
    │   │   ├── TopNavBar.jsx       (130 lines) Collection breadcrumb + actions bar  ← NEW
    │   │   ├── GallerySecondarySidebar.jsx (95 lines) Narrow icon nav sidebar      ← NEW
    │   │   ├── CollectionSidebar.jsx (124 lines) Gallery workspace nav
    │   │   └── ClientLayout.jsx    (27 lines)  Public client header/footer
    │   │
    │   ├── shared/                            Feature components
    │   │   ├── CreateGalleryModal.jsx (370 lines) Gallery creation form
    │   │   ├── GalleryCard.jsx     (218 lines)  Gallery card with actions
    │   │   ├── ClientPreviewModal.jsx (360 lines) Client preview + sticky header   ← MODIFIED
    │   │   ├── PasswordModal.jsx   (360 lines)  Password entry dialog
    │   │   ├── PhotoGrid.jsx       (358 lines)  Dashboard photo grid + drag reorder
    │   │   ├── PhotoLightbox.jsx   (433 lines)  Full-screen lightbox + video
    │   │   ├── PublicMasonryGrid.jsx (261 lines) Client masonry grid + download
    │   │   ├── SubscriptionGird.jsx (143 lines) Usage progress bars
    │   │   └── ProtectedRoute.jsx  (33 lines)   Auth gate + redirect
    │   │
    │   └── landing/                           Marketing site components
    │       ├── BrandLogo.jsx       (90 lines)   DEAD — never imported
    │       ├── Hero.jsx            (430 lines)  Animated hero + parallax
    │       ├── Features.jsx        (185 lines)  Feature cards + Framer Motion
    │       ├── GalleryGrid.jsx     (216 lines)  Decorative image grid
    │       ├── StatsTestimonials.jsx (165 lines) Stats counters + carousel
    │       ├── Navbar.jsx          (175 lines)  Sticky nav + mobile menu
    │       └── Footer.jsx          (133 lines)  CTA band + links
    │
    ├── context/
    │   └── PixiesetContext.jsx    (247 lines) Global gallery workspace state      ← NEW
    │
    └── pages/                                 Route-level components
        ├── LandingPage.jsx         (19 lines)  Composes landing components
        │
        ├── auth/                              Authentication
        │   ├── LoginPage.jsx       (230 lines)  Email/password login
        │   ├── RegisterPage.jsx    (496 lines)  Registration + subdomain picker
        │   └── ForgotPasswordPage.jsx (122 lines) Password reset request
        │
        ├── dashboard/                         Photographer dashboard
        │   ├── HomePage.jsx        (345 lines)  Greeting, stats, recent galleries
        │   ├── GalleriesPage.jsx   (358 lines)  Gallery list + search + create + error handling
        │   ├── GalleryWorkspaceLayout.jsx (230 lines) Gallery shell + breadcrumbs  ← MODIFIED
        │   ├── GalleryPhotosPage.jsx (519 lines) Upload, grid, reorder, delete
        │   ├── GalleryDesignPage.jsx (420 lines) 4-tab design builder             ← MODIFIED
        │   ├── GallerySettingsPage.jsx (450 lines) 5-tab settings panel           ← MODIFIED
        │   ├── ActivitiesWorkspace.jsx (280 lines) Activity tracker with 7 tabs    ← NEW
        │   └── SettingsPage.jsx    (324 lines)  Profile, branding, logo, password
        │
        ├── subscription/                      Billing
        │   ├── BillingPage.jsx     (338 lines)  Plan selector + receipt upload
        │   └── PricingPage.jsx     (219 lines)  Public pricing comparison
        │
        └── client/                            Public client-facing pages
            ├── ClientHomePage.jsx   (102 lines) Photographer public profile
            ├── ClientGalleryPage.jsx (424 lines) Public gallery + lightbox
            └── DownloadPage.jsx     (323 lines) Download portal
```

**Total:** 63 source files, ~11,600 lines of code (excluding `node_modules`, `dist`, lockfile). New files since Sep 15: `PixiesetContext.jsx`, `TopNavBar.jsx`, `GallerySecondarySidebar.jsx`, `ActivitiesWorkspace.jsx`.
