// 7-D: casual-save deterrence on the public client gallery (utils/mediaDeterrence.js).
import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { guardMediaEvent, shouldGuardMediaEvent } from './mediaDeterrence.js'

// A tiny DOM stand-in: a node knows its tag, attributes and parent, and
// `closest` understands the handful of selectors the module uses.
function node(tag, attrs = {}, parent = null) {
  const el = {
    tag,
    attrs,
    parent,
    closest(selector) {
      const parts = selector.split(',').map((part) => part.trim())
      for (let cur = el; cur; cur = cur.parent) {
        if (parts.some((part) => matches(cur, part))) return cur
      }
      return null
    },
  }
  return el
}

function matches(el, selector) {
  const attr = selector.match(/^\[([\w-]+)(?:="([^"]*)")?\]$/)
  if (attr) {
    const [, name, value] = attr
    return name in el.attrs && (value === undefined || el.attrs[name] === value)
  }
  const anchor = selector.match(/^a\[href\]$/)
  if (anchor) return el.tag === 'a' && 'href' in el.attrs
  return el.tag === selector
}

const tile = () => node('div', { 'data-ky-media-guard': '' })

function eventOn(target) {
  const event = { target, defaultPrevented: false, preventDefault() { this.defaultPrevented = true } }
  guardMediaEvent(event)
  return event
}

test('right-click and drag on a photo inside a guarded tile are cancelled', () => {
  const img = node('img', {}, tile())
  assert.equal(shouldGuardMediaEvent(img), true)
  assert.equal(eventOn(img).defaultPrevented, true)
})

test('the tile itself and a video inside the lightbox stage are guarded', () => {
  const stage = tile()
  assert.equal(shouldGuardMediaEvent(stage), true)
  assert.equal(shouldGuardMediaEvent(node('video', {}, stage)), true)
})

test('buttons inside a tile keep the browser menu (heart, download, share, keyboard menu key)', () => {
  const button = node('button', {}, tile())
  const icon = node('svg', {}, button)
  assert.equal(eventOn(button).defaultPrevented, false)
  assert.equal(eventOn(icon).defaultPrevented, false)
})

test('links, inputs, text areas, labels and role=button are never cancelled', () => {
  const region = tile()
  const cases = [
    node('a', { href: '/x' }, region),
    node('input', {}, region),
    node('textarea', {}, region),
    node('select', {}, region),
    node('label', {}, region),
    node('div', { role: 'button' }, region),
    node('div', { contenteditable: 'true' }, region),
  ]
  for (const target of cases) assert.equal(eventOn(target).defaultPrevented, false, target.tag)
})

test('anything outside a guarded region is left alone (dashboard, titles, forms, download pages)', () => {
  const page = node('div')
  for (const target of [node('img', {}, page), node('p', {}, page), node('h1', {}, page), node('video', {}, page)]) {
    assert.equal(shouldGuardMediaEvent(target), false, target.tag)
    assert.equal(eventOn(target).defaultPrevented, false, target.tag)
  }
})

test('a missing or non-element target is a no-op, never a throw', () => {
  assert.equal(shouldGuardMediaEvent(null), false)
  assert.equal(shouldGuardMediaEvent({}), false)
  assert.doesNotThrow(() => guardMediaEvent({}))
  assert.doesNotThrow(() => guardMediaEvent(undefined))
})

// ── wiring: where the deterrence is, and is not, switched on ────────────────
const read = (path) => readFileSync(new URL(path, import.meta.url), 'utf8')

test('the public grid, favorites tiles and both client lightboxes carry the guard', () => {
  const grid = read('../components/shared/PublicMasonryGrid.jsx')
  assert.match(grid, /data-ky-media-guard=""/)
  assert.match(grid, /onContextMenu=\{guardMediaEvent\}/)
  assert.match(grid, /onDragStart=\{guardMediaEvent\}/)
  assert.match(grid, /draggable=\{false\}/)

  const favorites = read('../components/client/FavoritesPanel.jsx')
  assert.match(favorites, /data-ky-media-guard=""/)

  const page = read('../pages/client/ClientGalleryPage.jsx')
  assert.equal(page.match(/<PhotoLightbox[\s\S]*?\/>/g).filter((block) => /\bdeterrence\b/.test(block)).length, 2)
})

test('the photographer dashboard never switches the deterrence on', () => {
  for (const path of ['../components/shared/PhotoGrid.jsx', '../pages/dashboard/FavoritesPage.jsx']) {
    assert.ok(!/\bdeterrence\b/.test(read(path)), path)
    assert.ok(!/mediaDeterrence/.test(read(path)), path)
  }
  // the shared lightbox is OFF unless a caller passes it
  assert.match(read('../components/shared/PhotoLightbox.jsx'), /deterrence = false/)
})

test('the guard adds no overlay, no touch-action lock and no keyboard handler', () => {
  const css = read('../styles/index.css')
  const block = css.slice(css.indexOf('.ky-media-guard {'))
  const rules = block.slice(0, block.indexOf('}'))
  assert.match(rules, /user-drag: none/)
  assert.match(rules, /-webkit-touch-callout: none/)
  assert.ok(!/touch-action|pointer-events|position/.test(rules), rules)
  assert.ok(!/key(down|up|press)/i.test(read('./mediaDeterrence.js').replace(/\/\/.*$/gm, '')))
})

test('motion is reduced for visitors who ask for it', () => {
  assert.match(read('../components/shared/PublicMasonryGrid.jsx'), /motion-reduce:transition-none/)
  assert.match(read('../components/shared/PhotoLightbox.jsx'), /motion-reduce:transition-none/)
})
