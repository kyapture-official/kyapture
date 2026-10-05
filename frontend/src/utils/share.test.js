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

test('card Share submenu: same labels/order as the client gallery popover, every entry has a real handler', async () => {
  const { buildShareMenuChildren } = await import('./share.js')
  const calls = []
  const args = { url: 'http://localhost:3000/g/u/s', title: 'Hari', onLink: () => calls.push('link'), onQr: () => calls.push('qr'), onNative: () => calls.push('native') }

  const without = buildShareMenuChildren(args)
  assert.deepEqual(without.map((item) => item.label), ['Share by email', 'Get direct link', 'Get QR code'])
  assert.ok(without[0].href.startsWith('mailto:?subject=Hari'))
  assert.match(decodeURIComponent(without[0].href), /http:\/\/localhost:3000\/g\/u\/s$/)
  without[1].onSelect()
  without[2].onSelect()
  assert.deepEqual(calls, ['link', 'qr'])

  const original = Object.getOwnPropertyDescriptor(globalThis, 'navigator')
  Object.defineProperty(globalThis, 'navigator', { value: { share: () => {} }, configurable: true })
  try {
    const withNative = buildShareMenuChildren(args)
    assert.deepEqual(withNative.map((item) => item.label), ['Share by email', 'Get direct link', 'Get QR code', 'Share…'])
    withNative[3].onSelect()
    assert.equal(calls.at(-1), 'native')
  } finally {
    if (original) Object.defineProperty(globalThis, 'navigator', original)
    else delete globalThis.navigator
  }
})
