// Run with: npm test   (node's built-in test runner — no extra dependency)
import test from 'node:test'
import assert from 'node:assert/strict'
import { DEFAULT_TYPOGRAPHY_ID, TYPOGRAPHY_IDS, isTypographyId, pickStyle, typographyVars } from './typography.js'
import { DEFAULT_DESIGN_SETTINGS, normalizeDesignSettings, resolveDesignSettings } from './designSettings.js'

// Shape and values the server sends (apps/core/typography.py).
const TIMELESS = {
  id: 'timeless', family_key: 'cormorant-garamond',
  font_family: '"Cormorant Garamond", Georgia, "Times New Roman", Times, serif',
  weight: 300, font_style: 'italic', letter_spacing: '0.02em', text_transform: 'none',
}
const BOLD = {
  id: 'bold', font_family: '"Oswald", Impact, "Arial Narrow Bold", system-ui, -apple-system, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif',
  weight: 600, font_style: 'normal', letter_spacing: '0.02em', text_transform: 'uppercase',
}

test('the six ids and the app default match the backend table', () => {
  assert.deepEqual(TYPOGRAPHY_IDS, ['sans', 'serif', 'modern', 'timeless', 'bold', 'subtle'])
  assert.equal(DEFAULT_TYPOGRAPHY_ID, 'serif')
  assert.equal(DEFAULT_DESIGN_SETTINGS.typography, 'serif')
})

test('typographyVars maps the server style to the five CSS variables', () => {
  assert.deepEqual(typographyVars(TIMELESS), {
    '--ky-font-family': TIMELESS.font_family,
    '--ky-font-weight': '300',
    '--ky-font-style': 'italic',
    '--ky-letter-spacing': '0.02em',
    '--ky-text-transform': 'none',
  })
  assert.equal(typographyVars(BOLD)['--ky-text-transform'], 'uppercase')
})

test('a missing or malformed style yields no variables (the stylesheet fallback applies)', () => {
  for (const bad of [null, undefined, 'serif', 5, [], {}]) assert.deepEqual(typographyVars(bad), {}, String(bad))
})

test('a value that could break out of a declaration is never emitted', () => {
  for (const patch of [
    { font_family: 'Inter; background:url(//evil)' },
    { font_family: '"Inter"}</style><script>' },
    { weight: '400; color:red' },
    { font_style: 'italic; x:y' },
    { letter_spacing: '0em; display:none' },
    { letter_spacing: 'url(x)' },
    { text_transform: 'uppercase; y:z' },
  ]) assert.deepEqual(typographyVars({ ...TIMELESS, ...patch }), {}, JSON.stringify(patch))
})

test('pickStyle finds the id, and an invalid or missing id gives the app default style', () => {
  const styles = [{ id: 'serif', label: 'Serif' }, TIMELESS, BOLD]
  assert.equal(pickStyle(styles, 'bold'), BOLD)
  for (const bad of [undefined, null, '', 'comic', 'SERIF', 7, 'bold; x']) assert.equal(pickStyle(styles, bad).id, 'serif', String(bad))
  assert.equal(pickStyle([], 'bold'), null)
  assert.equal(pickStyle(null, 'bold'), null)
  assert.ok(isTypographyId('modern') && !isTypographyId('Modern') && !isTypographyId(undefined))
})

test('an invalid or missing stored value shows the app default and the next save is valid', () => {
  const stale = { typography: 'comic-sans', layout: 'zigzag', colorPalette: 9, thumbSize: null, gridStyle: 'x', gridSpacing: 99, coverPhoto: 12 }
  assert.deepEqual(normalizeDesignSettings(stale), { ...DEFAULT_DESIGN_SETTINGS })
  assert.deepEqual(normalizeDesignSettings(undefined), { ...DEFAULT_DESIGN_SETTINGS })
  assert.deepEqual(normalizeDesignSettings('nope'), { ...DEFAULT_DESIGN_SETTINGS })
})

test('valid stored values are kept, key by key', () => {
  const good = { typography: 'bold', layout: 'frame', colorPalette: 'dark', thumbSize: 'large', gridStyle: 'horizontal', gridSpacing: 24, coverPhoto: 'abc' }
  assert.deepEqual(normalizeDesignSettings(good), good)
  assert.equal(normalizeDesignSettings({ typography: 'bold', layout: 'nope' }).typography, 'bold')
  assert.equal(normalizeDesignSettings({ gridSpacing: 4.5 }).gridSpacing, 16)
})

test('resolveDesignSettings no longer carries a Tailwind typography class', () => {
  const resolved = resolveDesignSettings({ typography: 'timeless' })
  assert.equal(resolved.typography, 'timeless')
  assert.equal('typographyClass' in resolved, false)
  assert.ok(resolved.theme.bg && resolved.layoutClass)
})
