// frontend/src/utils/typography.js

/**
 * WHAT: Turns the SERVER's typography style (apps/core/typography.py, via
 *       GET /galleries/typography-styles/ and the public payload's
 *       `typography_style`) into the CSS custom properties that `.ky-type`
 *       (styles/index.css) reads.
 *
 * WHY:  The stored value (`design_settings.typography`) is only ever an id.
 *       Nothing here builds CSS from it: callers pass a style object that the
 *       server resolved from its own table, and `typographyVars` copies only
 *       the five known presentation fields, each re-checked against a strict
 *       pattern, so even a bad response can never inject a declaration.
 *       No style (not loaded yet / request failed) gives {} and `.ky-type`
 *       falls back to the app default look in the stylesheet.
 */

// Same six ids and default as the backend table (DESIGN_CHOICES['typography']).
export const TYPOGRAPHY_IDS = ["sans", "serif", "modern", "timeless", "bold", "subtle"];
export const DEFAULT_TYPOGRAPHY_ID = "serif";

export const isTypographyId = (value) => typeof value === "string" && TYPOGRAPHY_IDS.includes(value);

const SAFE = {
  fontFamily: /^[A-Za-z0-9 ,"'-]+$/,
  weight: /^[1-9]00$/,
  fontStyle: /^(normal|italic)$/,
  letterSpacing: /^-?\d+(\.\d+)?em$/,
  textTransform: /^(none|uppercase)$/,
};

/** CSS custom properties for one server style, or {} when it is missing or malformed. */
export function typographyVars(style) {
  if (!style || typeof style !== "object") return {};
  const family = String(style.font_family ?? "");
  const weight = String(style.weight ?? "");
  const fontStyle = String(style.font_style ?? "");
  const spacing = String(style.letter_spacing ?? "");
  const transform = String(style.text_transform ?? "");
  if (
    !SAFE.fontFamily.test(family) ||
    !SAFE.weight.test(weight) ||
    !SAFE.fontStyle.test(fontStyle) ||
    !SAFE.letterSpacing.test(spacing) ||
    !SAFE.textTransform.test(transform)
  ) {
    return {};
  }
  return {
    "--ky-font-family": family,
    "--ky-font-weight": weight,
    "--ky-font-style": fontStyle,
    "--ky-letter-spacing": spacing,
    "--ky-text-transform": transform,
  };
}

/** The style for an id from the server list; an invalid or missing id gives the app default's style. */
export function pickStyle(styles, id) {
  if (!Array.isArray(styles)) return null;
  const wanted = isTypographyId(id) ? id : DEFAULT_TYPOGRAPHY_ID;
  return styles.find((style) => style?.id === wanted) || null;
}
