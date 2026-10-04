import test from 'node:test'
import assert from 'node:assert/strict'
import { buildShareEmailHref, toCanonicalShareUrl } from './share.js'

test('canonical share URL drops query string, hash and trailing slash — no secret can ride along', () => {
  assert.equal(toCanonicalShareUrl('https://kyapture.com/g/u/s/?pin=1234&token=abc#frag'), 'https://kyapture.com/g/u/s')
})

test('non-http(s) URLs are refused', () => {
  assert.equal(toCanonicalShareUrl('javascript:alert(1)'), '')
  assert.equal(toCanonicalShareUrl('data:text/html,hi'), '')
})

test('share-by-email puts the gallery title in the subject and the link in the body', () => {
  const href = buildShareEmailHref({ url: 'http://localhost:3000/g/u/s', title: 'Hari & Devi' })
  assert.ok(href.startsWith('mailto:?subject='))
  const params = new URLSearchParams(href.slice('mailto:?'.length))
  assert.equal(params.get('subject'), 'Hari & Devi')
  assert.match(params.get('body'), /http:\/\/localhost:3000\/g\/u\/s$/)
})

test('share-by-email still works without a title', () => {
  const params = new URLSearchParams(buildShareEmailHref({ url: 'http://x/g/u/s', title: '' }).slice('mailto:?'.length))
  assert.equal(params.get('subject'), 'A gallery for you')
})
