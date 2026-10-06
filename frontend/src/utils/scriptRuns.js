// frontend/src/utils/scriptRuns.js

/**
 * WHAT: Splits a title into Devanagari runs and everything else, so the title
 *       component can give the Devanagari runs their own spacing and line height
 *       (`.ky-deva`, styles/index.css).
 *
 * WHY:  Collection typography adds letter-spacing to some styles (0.02em-0.12em).
 *       In Devanagari that spacing cuts the continuous headline (shirorekha) into
 *       dashes, and the tall vowel marks above and below need more line height
 *       than Latin. CSS cannot select by script, so the runs are wrapped.
 *       Nothing here touches a font name: the family stack comes from the server.
 *
 * The range matches the unicode-range of the Devanagari @font-face rules in
 * styles/fonts.css (U+0900-097F, U+1CD0-1CF9, U+A8E0-A8FF, plus ZWJ/ZWNJ inside a word).
 */

const DEVA = "\\u0900-\\u097F\\u1CD0-\\u1CF9\\uA8E0-\\uA8FF";
const RUN = `[${DEVA}\\u200C\\u200D]+`;
// A run is Devanagari letters, plus plain spaces that sit between two Devanagari words
// (so a phrase like "सारी र रवि" is one run and keeps one continuous rhythm).
const RUN_RE = new RegExp(`(${RUN}(?:[ \\u00A0]+${RUN})*)`, "u");
const HAS_RE = new RegExp(`[${DEVA}]`, "u");

export const hasDevanagari = (text) => typeof text === "string" && HAS_RE.test(text);

/** [{ text, deva }] in order; empty or non-string input gives []. */
export function splitDevanagari(text) {
  if (typeof text !== "string" || text === "") return [];
  return text
    .split(RUN_RE)
    .map((part, index) => ({ text: part, deva: index % 2 === 1 }))
    .filter((run) => run.text !== "");
}
