// Run with: npm test   (node's built-in test runner — no extra dependency)
import test from 'node:test'
import assert from 'node:assert/strict'
import { buildGalleryLink, normalizeAppOrigin, resolveAppOrigin } from './appUrl.js'

test('uses the origin the app is actually served from — docker port 3000', () => {
  assert.equal(
    buildGalleryLink('kb789', 'hari-and-devi', { configured: undefined, locationOrigin: 'http://localhost:3000' }),
    'http://localhost:3000/g/kb789/hari-and-devi',
  )
})

test('follows whatever port the dev server is on — nothing is hard-coded', () => {
  for (const origin of ['http://localhost:5173', 'http://localhost:4173', 'http://127.0.0.1:8080', 'https://app.kyapture.com']) {
    assert.equal(buildGalleryLink('u', 's', { configured: '', locationOrigin: origin }), `${origin}/g/u/s`)
  }
})

test('a configured public app URL wins over the browser origin', () => {
  assert.equal(
    buildGalleryLink('u', 's', { configured: 'https://kyapture.com', locationOrigin: 'http://localhost:3000' }),
    'https://kyapture.com/g/u/s',
  )
})

test('a configured URL is reduced to its origin: trailing slash, path, query and hash are dropped', () => {
  assert.equal(normalizeAppOrigin('https://kyapture.com/'), 'https://kyapture.com')
  assert.equal(normalizeAppOrigin('https://kyapture.com/app/?pin=1234#x'), 'https://kyapture.com')
  assert.equal(normalizeAppOrigin('  http://localhost:3000  '), 'http://localhost:3000')
})

test('an unusable configured URL falls back to the browser origin', () => {
  for (const configured of ['', '   ', 'not a url', 'javascript:alert(1)', 'ftp://example.com', null, 42]) {
    assert.equal(resolveAppOrigin({ configured, locationOrigin: 'http://localhost:3000' }), 'http://localhost:3000')
  }
})

test('the link never carries a query string, hash or credential', () => {
  const link = buildGalleryLink('u', 's', { configured: 'https://kyapture.com/?token=abc#pin=1234', locationOrigin: 'http://x' })
  assert.equal(link, 'https://kyapture.com/g/u/s')
  assert.ok(!/[?#]/.test(link))
})

test('path parts are encoded, so a slug can never break out of the path', () => {
  assert.equal(
    buildGalleryLink('u', 'a/b?c#d', { configured: '', locationOrigin: 'http://localhost:3000' }),
    'http://localhost:3000/g/u/a%2Fb%3Fc%23d',
  )
})

test('returns an empty string until username and slug are both known', () => {
  const options = { configured: '', locationOrigin: 'http://localhost:3000' }
  assert.equal(buildGalleryLink('', 's', options), '')
  assert.equal(buildGalleryLink('u', '', options), '')
  assert.equal(buildGalleryLink(undefined, undefined, options), '')
})

test('returns an empty string when no origin can be determined at all', () => {
  assert.equal(buildGalleryLink('u', 's', { configured: '', locationOrigin: '' }), '')
})
