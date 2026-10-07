// 7-D: the app never claims that photos cannot be copied, saved or captured.
// The gallery's right-click / drag deterrence and the watermark only make casual
// saving harder; a screenshot, the network tab and an allowed download all still
// work. This scans every shipped source file for wording that would say otherwise.
import test from 'node:test'
import assert from 'node:assert/strict'
import { readdirSync, readFileSync, statSync } from 'node:fs'
import { join } from 'node:path'
import { fileURLToPath } from 'node:url'

const SRC = fileURLToPath(new URL('..', import.meta.url))

function sources(dir) {
  return readdirSync(dir).flatMap((name) => {
    const path = join(dir, name)
    if (statSync(path).isDirectory()) return sources(path)
    return /\.(jsx?|html)$/.test(name) && !/\.test\.js$/.test(name) ? [path] : []
  })
}

const CLAIMS = [
  /capture[- ]proof/i,
  /screenshot[- ]proof/i,
  /copy[- ]proof/i,
  /theft[- ]proof/i,
  /tamper[- ]proof/i,
  /(prevent|stop|block)s? (all )?(screenshots?|screen captures?|saving|copying|stealing|theft)/i,
  /(can(no|')t|cannot|can not|impossible to) (be )?(copied|saved|screenshot|screen[- ]?shotted|captured|stolen|downloaded)/i,
  /protected from (copying|saving|theft|screenshots?)/i,
  /(protect|secure|safeguard)s? (the |your |all )?(photos?|images?|pictures?|work|gallery|galleries) (from|against)/i,
  /asset[- ]theft protection/i,
  /unauthorized (copying|saving|downloads?)/i,
]

// A negation shortly before the phrase on the same sentence.
const NEGATED = /\b(not|never|nor|no|without|isn't|doesn't|don't|won't|cannot)\b[^.!?]*$/i

test('no shipped source claims capture-proof, copy-proof or screenshot-blocking', () => {
  const found = []
  for (const file of sources(SRC)) {
    const text = readFileSync(file, 'utf8')
    for (const claim of CLAIMS) {
      for (const match of text.matchAll(new RegExp(claim.source, 'gi'))) {
        // "does not stop screenshots" / "never ... capture-proof" are the honest wording.
        const before = text.slice(Math.max(0, match.index - 40), match.index)
        if (NEGATED.test(before)) continue
        found.push(`${file.slice(SRC.length)}: "${match[0]}"`)
      }
    }
  }
  assert.deepEqual(found, [])
})

test('the watermark text says it only makes casual saving harder', () => {
  const text = readFileSync(join(SRC, 'components/shared/WatermarkSettings.jsx'), 'utf8').replace(/\s+/g, ' ')
  assert.match(text, /makes casual saving harder/)
  assert.match(text, /does not stop screenshots or downloads/)
  assert.ok(!/Protect the photos/.test(text))
})

test('the landing feature badge does not say "Secure"', () => {
  const text = readFileSync(join(SRC, 'components/landing/Features.jsx'), 'utf8')
  assert.ok(!/'Secure'/.test(text))
})
