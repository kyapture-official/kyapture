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
 * defined LAYOUT_CLASSES/TYPOGRAPHY_CLASSES/COLOR_THEMES locally with no
 * public-side equivalent, so design_settings was persisted (Phase 1) but
 * silently ignored by the actual client gallery (Phase 2, item E). Both
 * sides now read the exact same option → class/theme mapping, so a
 * "gold" palette or "bold" typography choice looks the same in the
 * builder's preview and the real gallery.
 *
 * Scope is deliberately small and fixed — six typography options, nine
 * color themes, two grid styles, two thumbnail sizes, one spacing slider
 * — matching the locked MVP decision: no theme builder, no custom CSS,
 * no plugin system.
 */

export const LAYOUT_CLASSES = {
  center: "items-center text-center",
  left: "items-start text-left pl-10",
  novel: "items-center text-center",
  vintage: "items-center text-center",
  frame: "items-center text-center",
  stripe: "items-center text-center",
};

export const TYPOGRAPHY_CLASSES = {
  sans: "font-sans",
  serif: "font-serif",
  modern: "font-sans tracking-tight",
  timeless: "font-serif italic",
  bold: "font-sans font-bold",
  subtle: "font-sans font-light tracking-wide",
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
  typography: "serif",
  colorPalette: "light",
  thumbSize: "regular",
  gridSpacing: 16,
  gridStyle: "vertical",
  coverPhoto: null,
};

/**
 * Resolves a gallery's persisted (possibly partial/legacy/missing)
 * design_settings object into the concrete classes/values a component
 * needs, falling back to DEFAULT_DESIGN_SETTINGS field-by-field — a
 * gallery saved before a given option existed, or with an unrecognized
 * value, degrades to the same default the Design page itself falls back
 * to (see GalleryDesignPage.jsx's `saved.x || <default>` initialization),
 * never a blank/crashed render.
 */
export function resolveDesignSettings(settings) {
  const s = settings && typeof settings === "object" ? settings : {};
  const layout = s.layout || DEFAULT_DESIGN_SETTINGS.layout;
  const typography = s.typography || DEFAULT_DESIGN_SETTINGS.typography;
  const colorPalette = s.colorPalette || DEFAULT_DESIGN_SETTINGS.colorPalette;
  const thumbSize = s.thumbSize || DEFAULT_DESIGN_SETTINGS.thumbSize;
  const gridStyle = s.gridStyle || DEFAULT_DESIGN_SETTINGS.gridStyle;
  const gridSpacing =
    typeof s.gridSpacing === "number" ? s.gridSpacing : DEFAULT_DESIGN_SETTINGS.gridSpacing;

  return {
    layout,
    typography,
    colorPalette,
    thumbSize,
    gridStyle,
    gridSpacing,
    coverPhoto: s.coverPhoto ?? DEFAULT_DESIGN_SETTINGS.coverPhoto,
    layoutClass: LAYOUT_CLASSES[layout] || LAYOUT_CLASSES[DEFAULT_DESIGN_SETTINGS.layout],
    typographyClass:
      TYPOGRAPHY_CLASSES[typography] || TYPOGRAPHY_CLASSES[DEFAULT_DESIGN_SETTINGS.typography],
    theme: COLOR_THEMES[colorPalette] || COLOR_THEMES[DEFAULT_DESIGN_SETTINGS.colorPalette],
  };
}
