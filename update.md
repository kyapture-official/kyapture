# Kyapture Frontend — Update Log

## Date: 15 September 2026

---

## What Was Done Today

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
├── vite.config.js                (14 lines)   Vite dev/build config
│
└── src/
    ├── main.jsx                  (10 lines)   React root mount
    ├── App.jsx                   (78 lines)   Route definitions, providers
    │
    ├── api/                                   HTTP clients (Axios wrappers)
    │   ├── axiosInstance.js       (107 lines)  Axios instance, CSRF, 401 refresh
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
    │   │   ├── CollectionSidebar.jsx (124 lines) Gallery workspace nav
    │   │   └── ClientLayout.jsx    (27 lines)  Public client header/footer
    │   │
    │   ├── shared/                            Feature components
    │   │   ├── CreateGalleryModal.jsx (370 lines) Gallery creation form
    │   │   ├── GalleryCard.jsx     (218 lines)  Gallery card with actions
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
        │   ├── GalleriesPage.jsx   (352 lines)  Gallery list + search + create
        │   ├── GalleryWorkspaceLayout.jsx (208 lines) Gallery shell + breadcrumbs
        │   ├── GalleryPhotosPage.jsx (519 lines) Upload, grid, reorder, delete
        │   ├── GallerySettingsPage.jsx (398 lines) Gallery config + password
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

**Total:** 58 source files, ~10,400 lines of code (excluding `node_modules`, `dist`, lockfile).
