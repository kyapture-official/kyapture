// File Location: frontend/src/utils/colorHelper.js
// VERSION: Production-Grade Hex Helper — Week 10
// Safe, browser-compliant color translucent utility.

/**
 * WHAT: Appends an alpha channel hex byte to standard color strings.
 * WHY:  Enforces defensive color formatting, falling back to brand accent 
 *       on invalid strings, and provides translucent layout highlights.
 *
 * @param {string} hexColor - 6-digit hex color string (e.g., '#4a7c6f')
 * @param {string} alphaHex - 2-digit hex alpha channel byte (e.g., '14' for ~8% opacity)
 * @returns {string} 8-digit RGBA hex color string (e.g., '#4a7c6f14')
 */
export function getAlphaBrandingColor(hexColor, alphaHex = 'ff') {
  const FALLBACK = '#c17f3e' // Kyapture accent matching index.css --accent
  
  const isValidHex = typeof hexColor === 'string' && /^#[0-9a-fA-F]{6}$/.test(hexColor)
  const base = isValidHex ? hexColor : FALLBACK
  
  return `${base}${alphaHex}`
}