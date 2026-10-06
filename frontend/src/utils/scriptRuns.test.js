// Run with: npm test   (node's built-in test runner — no extra dependency)
import test from 'node:test'
import assert from 'node:assert/strict'
import { hasDevanagari, splitDevanagari } from './scriptRuns.js'

test('a Latin-only title has no Devanagari run (nothing to wrap, no font request)', () => {
  assert.equal(hasDevanagari('Sarah & Tom, Summer 2026 ₹ é ñ'), false)
  assert.deepEqual(splitDevanagari('Sarah & Tom'), [{ text: 'Sarah & Tom', deva: false }])
})

test('a Devanagari title is one run, spaces between words included', () => {
  assert.equal(hasDevanagari('सारी र रवि'), true)
  assert.deepEqual(splitDevanagari('सारी र रवि'), [{ text: 'सारी र रवि', deva: true }])
})

test('mixed text keeps order and splits at the script change', () => {
  assert.deepEqual(splitDevanagari('Sari र रवि Wedding'), [
    { text: 'Sari ', deva: false }, { text: 'र रवि', deva: true }, { text: ' Wedding', deva: false },
  ])
  assert.deepEqual(splitDevanagari('A सारी B रवि'), [
    { text: 'A ', deva: false }, { text: 'सारी', deva: true }, { text: ' B ', deva: false }, { text: 'रवि', deva: true },
  ])
})

test('joiners stay inside the run, the danda and Devanagari digits count as Devanagari', () => {
  assert.deepEqual(splitDevanagari('क्‍ष'), [{ text: 'क्‍ष', deva: true }])
  assert.equal(hasDevanagari('॥'), true)
  assert.equal(hasDevanagari('२०२६'), true)
})

test('empty or non-string input gives nothing', () => {
  for (const bad of [undefined, null, '', 5, {}]) assert.deepEqual(splitDevanagari(bad), [], String(bad))
  assert.equal(hasDevanagari(undefined), false)
})
