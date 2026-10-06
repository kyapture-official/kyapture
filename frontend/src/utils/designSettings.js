// frontend/src/utils/designSettings.js

/**
 * WHAT: Shared design-settings vocabulary — the same layout/typography/
 *       color/grid option sets the photographer's Design page
 *       (GalleryDesignPage.jsx / CoverPreview.jsx) lets them choose from,
 *       now also consumed by the PUBLIC client gallery
 *       (ClientGalleryPage.jsx / PublicMasonryGrid.jsx) so a gallery's
 *       persisted design_settings actually changes what a guest sees —
 *       not just the photographer's own live preview.
 *
 * WHY a shared module instead of two copies: CoverPreview.jsx previously
 * defined LAYOUT_CLASSES/COLOR_THEMES locally with no public-side
 * equivalent, so design_settings was persisted (Phase 1) but silently
 * ignored by the actual client gallery (Phase 2, item E). Both sides now
 * read the exact same option → class/theme mapping, so a "gold" palette
 * looks the same in the builder's preview and the real gallery.
 *
 * Typography is NOT a class mapping any more: the six styles come from the
 * server (utils/typography.js, chunk 6.2-B).
 *
 * Scope is deliberately small and fixed — six typography options, nine
 * color themes, two grid styles, two thumbnail sizes, one spacing slider
 * — matching the locked MVP decision: no theme builder, no custom CSS,
 * no plugin system.
 */

import { DEFAULT_TYPOGRAPHY_ID, isTypographyId } from "./typography.js";

export const LAYOUT_CLASSES = {
  center: "items-center text-center",
  left: "items-start text-left pl-10",
  novel: "items-center text-center",
  vintage: "items-center text-center",
  frame: "items-center text-center",
  stripe: "items-center text-center",
};

export const COLOR_THEMES = {
  light: { bg: "bg-surface-light", text: "text-ink", sub: "text-muted", accent: "bg-ink" },
  gold: { bg: "bg-amber-50", text: "text-amber-900", sub: "text-amber-700/60", accent: "bg-amber-600" },
  rose: { bg: "bg-rose-50", text: "text-rose-900", sub: "text-rose-700/60", accent: "bg-rose-500" },
  terracotta: { bg: "bg-orange-50", text: "text-orange-900", sub: "text-orange-700/60", accent: "bg-orange-600" },
  sand: { bg: "bg-stone-100", text: "text-stone-900", sub: "text-stone-600", accent: "bg-stone-500" },
  olive: { bg: "bg-lime-50", text: "text-lime-900", sub: "text-lime-700/60", accent: "bg-lime-700" },
  agave: { bg: "bg-brand-green-50", text: "text-brand-green-900", sub: "text-brand-green-700/60", accent: "bg-brand-green-600" },
  sea: { bg: "bg-sky-50", text: "text-sky-900", sub: "text-sky-700/60", accent: "bg-sky-600" },
  dark: { bg: "bg-slate-900", text: "text-white", sub: "text-white/50", accent: "bg-white/20" },
};

export const DEFAULT_DESIGN_SETTINGS = {
  layout: "center",
  typography: DEFAULT_TYPOGRAPHY_ID,
  colorPalette: "light",
  thumbSize: "regular",
  gridSpacing: 16,
  gridStyle: "vertical",
  coverPhoto: null,
};

const GRID_STYLES = ["vertical", "horizontal"];
const THUMB_SIZES = ["regular", "large"];
const GRID_SPACING_RANGE = [4, 32];

const pick = (value, allowed, fallback) => (typeof value === "string" && allowed.includes(value) ? value : fallback);

/**
 * A gallery's stored presentation settings with every key checked against the
 * same fixed vocabulary the server enforces on save (apps/users/
 * collection_defaults.py). A missing, legacy or out-of-vocabulary value
 * becomes the app default, so the Design page shows the default as selected
 * and the next save sends only valid values (it re-sends every key).
 */
export function normalizeDesignSettings(settings) {
  const s = settings && typeof settings === "object" ? settings : {};
  const d = DEFAULT_DESIGN_SETTINGS;
  const spacing = s.gridSpacing;
  return {
    layout: pick(s.layout, Object.keys(LAYOUT_CLASSES), d.layout),
    typography: isTypographyId(s.typography) ? s.typography : d.typography,
    colorPalette: pick(s.colorPalette, Object.keys(COLOR_THEMES), d.colorPalette),
    thumbSize: pick(s.thumbSize, THUMB_SIZES, d.thumbSize),
    gridStyle: pick(s.gridStyle, GRID_STYLES, d.gridStyle),
    gridSpacing:
      Number.isInteger(spacing) && spacing >= GRID_SPACING_RANGE[0] && spacing <= GRID_SPACING_RANGE[1]
        ? spacing
        : d.gridSpacing,
    coverPhoto: typeof s.coverPhoto === "string" ? s.coverPhoto : d.coverPhoto,
  };
}

/**
 * Resolves a gallery's persisted (possibly partial/legacy/missing)
 * design_settings object into the concrete classes/values a component
 * needs, falling back to DEFAULT_DESIGN_SETTINGS field-by-field, never a
 * blank/crashed render. Typography is only the validated id here; the look
 * itself comes from the server's style (utils/typography.js).
 */
export function resolveDesignSettings(settings) {
  const normalized = normalizeDesignSettings(settings);
  return {
    ...normalized,
    layoutClass: LAYOUT_CLASSES[normalized.layout],
    theme: COLOR_THEMES[normalized.colorPalette],
  };
}
