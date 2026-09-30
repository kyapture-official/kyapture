# KYAPTURE — Locked Product Decisions

**Status:** Locked. These are the current MVP source of truth as of 2026-09-30, superseding any conflicting recommendation in `KYAPTURE_FORENSIC_AUDIT_2026-09-29.md.md` or `KYAPTURE_VERIFIED_EXECUTION_PLAN.md`. Any future change to one of these decisions should be recorded here, not silently implemented in code.

---

## 1. Currency: NPR

All pricing, plan display, invoices, and billing UI use NPR. Backend plan seed data (`seed_plans.py`) and any user-facing `$` symbols (including in error/log messages) should be brought in line with this over time — not a Phase 0 concern, but do not introduce any *new* USD-formatted user-facing text going forward.

## 2. Payment processor: manual only for MVP

Keep the existing manual-payment flow (screenshot upload, staff approval via API/Django admin). Stripe or any other card processor is explicitly deferred post-MVP. Do not build processor integration during Phase 0 or the MVP gap-closing phases.

## 3. Client gallery URLs: path-based only

Canonical, and only, client gallery URL scheme for MVP:

```
/g/:username/:slug
```

This matches `frontend/src/App.jsx`'s existing router already. `frontend/src/utils/formatters.js`'s `buildClientGalleryUrl()` currently builds a **subdomain** URL in production (`https://{username}.{domain}/{slug}`), which does not match any route the app actually serves — that function (and any other URL builder that disagrees with it, e.g. in `TopNavBar.jsx`/`GalleriesPage.jsx`/`ClientHomePage.jsx`) should be consolidated onto the path-based scheme as part of the F-14 cleanup. Not done in Phase 0; recorded here so it isn't re-broken later.

## 4. Subdomain gallery URLs: post-MVP

Wildcard-subdomain tenancy (`{username}.kyapture.com`) is explicitly out of scope for MVP. It requires wildcard DNS, wildcard TLS, subdomain-aware CORS, and cookie-domain scoping that the current architecture does not have and should not grow prematurely. `ALLOWED_HOSTS = [".kyapture.com"]`'s wildcard fallback in `production.py` is pre-existing infrastructure headroom, not an implementation commitment — no subdomain-routing code should be added during MVP work.

## 5. Free tier: 3 GB storage, 10 galleries maximum

- `storage_bytes_limit`: 3 GB (unchanged from current default).
- `max_galleries`: **10** (currently `None`/unlimited in `get_user_subscription_metrics()`'s `default_limits` — this must be changed to `10` when free-tier limits are implemented).
- `max_photos_per_gallery`: not specified by this decision; left at existing behavior (`None`/unlimited) unless a future decision sets it.

Not implemented in Phase 0 (it lives in Phase 4 of the verified execution plan, alongside the soft-delete/storage-leak fix it interacts with). Recorded here as the target value for that work.

## 6. Design is a real MVP feature — persisted and applied, kept simple

`design_settings` is not a stub to silently drop. For MVP:

- **Persist** a `design_settings` JSON field on `Gallery` (cover selection, typography choice, color, grid behavior/density).
- **Apply** the selected cover, typography, color, and grid behavior on the client-facing gallery (`ClientGalleryPage.jsx` / public gallery rendering) — not just in the photographer's dashboard preview.
- **Keep it focused.** This is a fixed set of a few discrete choices (e.g. a small palette, 2–3 typography options, 2–3 grid layouts), not an open-ended theme builder, custom CSS, or a plugin system. No drag-and-drop layout editor, no arbitrary color picker beyond the existing branding-color pattern already in the model, no per-block styling.

This decision directly resolves the P0-1 crash (F-01: `design_settings` referenced in `GalleryUpdateSerializer` with no backing model field) in favor of **building the field properly**, not stripping it — that implementation is scheduled in Phase 1 of the execution plan, immediately after the Phase 0 foundation work in this document's companion, `docs/KYAPTURE_VERIFIED_EXECUTION_PLAN.md`.

---

## How this doc relates to the others

- `KYAPTURE_FORENSIC_AUDIT_2026-09-29.md.md` — original static audit (Project Files).
- `docs/KYAPTURE_VERIFIED_EXECUTION_PLAN.md` — audit findings verified against the live repository, phased implementation order.
- `docs/KYAPTURE_PRODUCT_DECISIONS.md` (this file) — the product-level answers that unblock implementation of that plan. Where the execution plan lists an "unknown requiring your decision," this file is the resolution.
