// Run with: npm test   (node's built-in test runner — no extra dependency)
// CHUNK 6.2-C: the Devanagari faces must stay behind unicode-range so a Latin-only page never fetches them.
import test from 'node:test'
import assert from 'node:assert/strict'
import { existsSync, readFileSync } from 'node:fs'

const root = new URL('../../', import.meta.url)
const css = readFileSync(new URL('src/styles/fonts.css', root), 'utf8')
const faces = css.match(/@font-face\s*\{[^}]*\}/g).map((block) => ({
  family: /font-family:\s*'([^']+)'/.exec(block)[1],
  style: /font-style:\s*(\w+)/.exec(block)[1],
  weight: Number(/font-weight:\s*(\d+)/.exec(block)[1]),
  swap: /font-display:\s*swap/.test(block),
  file: /url\('\.\.\/assets\/fonts\/([^']+)'\)/.exec(block)[1],
  range: (/unicode-range:\s*([^;]+);/.exec(block) || [])[1] || '',
}))
const deva = faces.filter((face) => face.family.endsWith('Devanagari'))

test('exactly the weights the six styles use are declared (sans 300/400/600, serif 300/400 + 300 italic)', () => {
  const key = (face) => `${face.family}|${face.weight}|${face.style}`
  assert.deepEqual(deva.map(key).sort(), [
    'Noto Sans Devanagari|300|normal', 'Noto Sans Devanagari|400|normal', 'Noto Sans Devanagari|600|normal',
    'Noto Serif Devanagari|300|italic', 'Noto Serif Devanagari|300|normal', 'Noto Serif Devanagari|400|normal',
  ])
})

test('every Devanagari face is woff2, font-display swap, an existing file, and limited by a Devanagari-only unicode-range', () => {
  for (const face of deva) {
    assert.ok(face.swap, face.file)
    assert.match(face.file, /-devanagari-\d{3}-normal\.woff2$/)
    assert.ok(existsSync(new URL(`src/assets/fonts/${face.file}`, root)), face.file)
    assert.match(face.range, /^U\+0900-097F/, face.file)
    // nothing from the Latin blocks, general punctuation or currency may trigger the download
    for (const part of face.range.split(',')) {
      const start = parseInt(part.replace('U+', '').split('-')[0], 16)
      assert.ok(start >= 0x0900, `${face.file} ${part}`)
      assert.ok(!(start >= 0x2010 && start <= 0x20ff && start !== 0x200c), `${face.file} ${part}`)
    }
  }
})

test('every Latin face keeps its Latin-only range (no Devanagari in it, so Devanagari falls through the stack)', () => {
  for (const face of faces.filter((f) => !f.family.endsWith('Devanagari'))) {
    assert.match(face.range, /^U\+0000-00FF/, face.file)
    assert.ok(!/U\+09/.test(face.range), face.file)
  }
})

test('the OFL licence text of both Devanagari families ships in public/font-licenses', () => {
  for (const name of ['noto-sans-devanagari', 'noto-serif-devanagari']) {
    const text = readFileSync(new URL(`public/font-licenses/OFL-${name}.txt`, root), 'utf8')
    assert.match(text, /SIL OPEN FONT LICENSE Version 1\.1/)
  }
})

test('the stylesheet fallback stack for no style (app default look) has the serif Devanagari family', () => {
  const index = readFileSync(new URL('src/styles/index.css', root), 'utf8')
  assert.match(index, /"Libre Baskerville", "Noto Serif Devanagari", Georgia/)
})
