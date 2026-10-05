import test from 'node:test'
import assert from 'node:assert/strict'
import { gateNeeds, initialStep, photoGateIntro } from './downloadFlow.js'
import { copyText } from './share.js'
import { nextFavoriteIds } from './favoriteFlow.js'

test('download dialog moves from required access to choose, then skips access after a grant', () => {
  const needs = gateNeeds({ policy: { require_email: true }, hasPin: true, access: null })
  assert.deepEqual(needs, { needsEmail: true, needsPin: true, needsGate: true })
  assert.equal(initialStep(needs), 'auth')
  assert.match(photoGateIntro({ ...needs, studio: 'Kroman' }), /email and the download PIN/)
  assert.equal(initialStep({ needsGate: false }), 'choose')
})

test('share modal copy uses the browser clipboard and reports a real success', async () => {
  const originalNavigator = Object.getOwnPropertyDescriptor(globalThis, 'navigator')
  const originalWindow = Object.getOwnPropertyDescriptor(globalThis, 'window')
  const copied = []
  Object.defineProperty(globalThis, 'navigator', { configurable: true, value: { clipboard: { writeText: async (value) => copied.push(value) } } })
  Object.defineProperty(globalThis, 'window', { configurable: true, value: { isSecureContext: true } })

  try {
    assert.equal(await copyText('http://localhost:3000/g/u/s'), true)
    assert.deepEqual(copied, ['http://localhost:3000/g/u/s'])
  } finally {
    if (originalNavigator) Object.defineProperty(globalThis, 'navigator', originalNavigator)
    else delete globalThis.navigator
    if (originalWindow) Object.defineProperty(globalThis, 'window', originalWindow)
    else delete globalThis.window
  }
})

test('share modal falls back to legacy copy when async clipboard is unavailable', async () => {
  const originalNavigator = Object.getOwnPropertyDescriptor(globalThis, 'navigator')
  const originalWindow = Object.getOwnPropertyDescriptor(globalThis, 'window')
  const originalDocument = Object.getOwnPropertyDescriptor(globalThis, 'document')
  let copied = null
  const textarea = { value: '', style: {}, setAttribute() {}, select() {}, setSelectionRange() {}, remove() {} }
  const document = {
    createElement: () => textarea,
    body: { appendChild() {} },
    execCommand: (command) => { copied = command; return true },
  }
  Object.defineProperty(globalThis, 'navigator', { configurable: true, value: {} })
  Object.defineProperty(globalThis, 'window', { configurable: true, value: { isSecureContext: false } })
  Object.defineProperty(globalThis, 'document', { configurable: true, value: document })

  try {
    assert.equal(await copyText('gallery-link'), true)
    assert.equal(copied, 'copy')
    assert.equal(textarea.value, 'gallery-link')
  } finally {
    if (originalNavigator) Object.defineProperty(globalThis, 'navigator', originalNavigator)
    else delete globalThis.navigator
    if (originalWindow) Object.defineProperty(globalThis, 'window', originalWindow)
    else delete globalThis.window
    if (originalDocument) Object.defineProperty(globalThis, 'document', originalDocument)
    else delete globalThis.document
  }
})

test('favorites heart toggles optimistically and can roll back the same photo', () => {
  const before = new Set(['already-favorite'])
  const afterAdd = nextFavoriteIds(before, 'photo-1', false)
  assert.deepEqual([...afterAdd], ['already-favorite', 'photo-1'])
  const afterRollback = nextFavoriteIds(afterAdd, 'photo-1', true)
  assert.deepEqual([...afterRollback], ['already-favorite'])

  const afterRemove = nextFavoriteIds(before, 'already-favorite', true)
  assert.deepEqual([...afterRemove], [])
  assert.deepEqual([...nextFavoriteIds(afterRemove, 'already-favorite', false)], ['already-favorite'])
})
