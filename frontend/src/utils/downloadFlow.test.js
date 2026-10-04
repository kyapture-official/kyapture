import test from 'node:test'
import assert from 'node:assert/strict'
import {
  allSetIds, blockedMessage, defaultSize, formatBytes, gateIntro, gateNeeds, initialStep, isAllSelected, isBlockedCode,
  jobPagePath, jobViewFor, photoLabel, pollDelay, remainingPreparingMs, scopeModel, selectionRequest, sizeOptions, toggleAll, toggleSet,
} from './downloadFlow.js'

const sets = [
  { id: 'a', name: 'Ceremony', photo_count: 4 },
  { id: 'b', name: 'Party', photo_count: 6 },
  { id: 'c', name: 'Empty', photo_count: 0 },
]
const fresh = { token: 't', expiresAt: Date.now() + 60_000 }
const stale = { token: 't', expiresAt: Date.now() - 1 }

test('skip logic: email not required and no PIN goes straight to Page 2', () => {
  const needs = gateNeeds({ policy: { require_email: false }, hasPin: false, access: null })
  assert.equal(needs.needsGate, false)
  assert.equal(initialStep({ needsGate: needs.needsGate }), 'choose')
})

test('skip logic: an email requirement, a PIN, or both put Page 1 first', () => {
  assert.deepEqual(gateNeeds({ policy: { require_email: true }, hasPin: false, access: null }),
    { needsEmail: true, needsPin: false, needsGate: true })
  assert.deepEqual(gateNeeds({ policy: { require_email: false }, hasPin: true, access: null }),
    { needsEmail: false, needsPin: true, needsGate: true })
  assert.equal(gateNeeds({ policy: { require_email: true }, hasPin: true, access: null }).needsGate, true)
  assert.equal(initialStep({ needsGate: true }), 'auth')
  assert.equal(initialStep({ needsGate: false }), 'choose')
})

test('skip logic: access already earned this session skips Page 1; an expired token does not', () => {
  assert.equal(gateNeeds({ policy: { require_email: true }, hasPin: true, access: fresh }).needsGate, false)
  assert.equal(gateNeeds({ policy: { require_email: true }, hasPin: true, access: stale }).needsGate, true)
})

test('Page 1 text: the PIN sentence appears only when a PIN is enabled and names the studio', () => {
  const emailOnly = gateIntro({ needsEmail: true, needsPin: false, studio: 'Kroman' })
  assert.equal(emailOnly, 'Your email will be used to notify you when the files are ready for download.')
  const both = gateIntro({ needsEmail: true, needsPin: true, studio: 'Kroman' })
  assert.equal(both, `${emailOnly} Please enter the download PIN provided by Kroman to download this photo collection.`)
  assert.doesNotMatch(emailOnly, /PIN/)
})

test('only enabled sizes are offered; one enabled size is preselected; High Resolution is the default', () => {
  assert.deepEqual(sizeOptions({ allowed_sizes: ['download', 'web'] }).map((o) => o.label), ['High Resolution', 'Web Size'])
  assert.equal(defaultSize(sizeOptions({ allowed_sizes: ['download', 'web'] })), 'download')
  const webOnly = sizeOptions({ allowed_sizes: ['web'] })
  assert.deepEqual(webOnly.map((o) => o.value), ['web'])
  assert.equal(defaultSize(webOnly), 'web')
  assert.deepEqual(sizeOptions({ allowed_sizes: ['download'] }).map((o) => o.value), ['download'])
})

test('no client-facing size is ever labelled Original', () => {
  const labels = sizeOptions({ allowed_sizes: ['download', 'web', 'original'] }).map((o) => o.label).join(' ')
  assert.doesNotMatch(labels, /original/i)
})

test('unrestricted gallery: every set with photos, "All photos" counts the whole gallery', () => {
  const model = scopeModel({ policy: { sets_enabled: null }, photoSets: sets, photoCount: 12 })
  assert.deepEqual(allSetIds(model), ['a', 'b'])          // the empty set is not offered
  assert.equal(model.allCount, 12)
  assert.equal(model.wholeGallery, true)
})

test('restricted gallery: only the sets enabled in Download > Advanced are listed', () => {
  const model = scopeModel({ policy: { sets_enabled: ['b'] }, photoSets: sets, photoCount: 12 })
  assert.deepEqual(allSetIds(model), ['b'])
  assert.equal(model.allCount, 6)
  assert.equal(model.wholeGallery, false)
})

test('selection -> request: whole gallery, one set, several sets, nothing', () => {
  const open = scopeModel({ policy: { sets_enabled: null }, photoSets: sets, photoCount: 12 })
  assert.deepEqual(selectionRequest(open, ['a', 'b']), {})
  assert.deepEqual(selectionRequest(open, ['b']), { setId: 'b' })
  assert.equal(selectionRequest(open, []), null)

  const three = scopeModel({
    policy: { sets_enabled: null }, photoCount: 12,
    photoSets: [...sets.slice(0, 2), { id: 'd', name: 'Extras', photo_count: 2 }],
  })
  assert.deepEqual(selectionRequest(three, ['a', 'd']), { setIds: ['a', 'd'] })
  assert.deepEqual(selectionRequest(three, ['a', 'b', 'd']), {})
})

test('restricted gallery never asks for the whole gallery — every enabled set is listed by id', () => {
  const model = scopeModel({ policy: { sets_enabled: ['a', 'b'] }, photoSets: sets, photoCount: 12 })
  assert.deepEqual(selectionRequest(model, ['a', 'b']), { setIds: ['a', 'b'] })
  const single = scopeModel({ policy: { sets_enabled: ['a'] }, photoSets: sets, photoCount: 12 })
  assert.deepEqual(selectionRequest(single, ['a']), { setId: 'a' })
})

test('a gallery without sets downloads as a whole', () => {
  const model = scopeModel({ policy: { sets_enabled: null }, photoSets: [], photoCount: 5 })
  assert.deepEqual(selectionRequest(model, []), {})
  assert.equal(isAllSelected(model, []), true)
})

test('"All photos" toggles every set; unchecking a set unchecks All', () => {
  const model = scopeModel({ policy: { sets_enabled: null }, photoSets: sets, photoCount: 12 })
  assert.deepEqual(toggleAll(model, []), ['a', 'b'])
  assert.deepEqual(toggleAll(model, ['a', 'b']), [])
  const afterUncheck = toggleSet(['a', 'b'], 'a')
  assert.equal(isAllSelected(model, afterUncheck), false)
})

test('blocked-case messages name the studio and never carry a contact list', () => {
  assert.equal(blockedMessage('download_limit_reached', 'Kroman'), 'Download limit reached. Contact Kroman.')
  assert.equal(blockedMessage('pin_limit_reached', 'Kroman'), 'Download limit reached. Contact Kroman.')
  assert.equal(blockedMessage('email_not_authorized', 'Kroman'), 'This email is not authorized to download. Contact Kroman.')
  assert.equal(blockedMessage('invalid_pin', 'Kroman', 'x'), 'x')
  assert.equal(isBlockedCode('email_not_authorized'), true)
  assert.equal(isBlockedCode('invalid_pin'), false)
})

test('photo counts read naturally', () => {
  assert.equal(photoLabel(1), '1 photo')
  assert.equal(photoLabel(6), '6 photos')
  assert.equal(photoLabel(0), '0 photos')
})

test('the prepared download lives at its own tokenised page', () => {
  assert.equal(jobPagePath('kb789', 'hari-and-devi', 'j1', 'k.y'), '/g/kb789/hari-and-devi/download/file/j1?key=k.y')
  assert.equal(jobPagePath('u', 's', 'j1'), '/g/u/s/download/file/j1')
})

test('status polling backs off 2s, 5s, then every 10s', () => {
  assert.deepEqual([0, 1, 2, 3, 40].map(pollDelay), [2000, 5000, 10000, 10000, 10000])
})

test('the Preparing page stays at least 1.5s so a fast job does not flash past it', () => {
  assert.equal(remainingPreparingMs(0), 1500)
  assert.equal(remainingPreparingMs(400), 1100)
  assert.equal(remainingPreparingMs(1500), 0)
  assert.equal(remainingPreparingMs(9000), 0)
  assert.equal(remainingPreparingMs(undefined), 1500)
})

test('file sizes read like Pixieset: MB with one decimal, GB above 1024 MB', () => {
  assert.equal(formatBytes(89.6 * 1024 * 1024), '89.6 MB')
  assert.equal(formatBytes(1.9 * 1024 ** 3), '1.9 GB')
  assert.equal(formatBytes(2048), '2 KB')
  assert.equal(formatBytes(10), '1 KB')
})

test('page 3/4 view: preparing, ready, expired (7 days / purged / unknown key), failed, locked, retry', () => {
  assert.equal(jobViewFor({ data: { state: 'preparing' } }), 'preparing')
  assert.equal(jobViewFor({ data: { state: 'ready', files: [] } }), 'ready')
  assert.equal(jobViewFor({ data: { state: 'failed', code: 'download_expired' } }), 'expired')
  assert.equal(jobViewFor({ data: { state: 'failed', code: 'file_missing' } }), 'expired')
  assert.equal(jobViewFor({ data: { state: 'failed', code: 'prepare_failed' } }), 'failed')
  assert.equal(jobViewFor({ error: { status: 404, code: 'download_not_found' } }), 'expired')
  assert.equal(jobViewFor({ error: { status: 410, code: 'download_expired' } }), 'expired')
  assert.equal(jobViewFor({ error: { status: 401, code: 'session_required' } }), 'locked')
  assert.equal(jobViewFor({ error: { status: 503 } }), 'retry')
  assert.equal(jobViewFor({ error: { name: 'Error' } }), 'retry')
})

// ── 1R.5-D single photo ─────────────────────────────────────────────────────

import {
  photoGateIntro, photoPrefsKey, photoSizeOptions, readRememberedSize, writeRememberedSize,
} from './downloadFlow.js'

const memoryStorage = () => {
  const map = new Map()
  return { getItem: (k) => (map.has(k) ? map.get(k) : null), setItem: (k, v) => map.set(k, v), removeItem: (k) => map.delete(k) }
}

test('photo gate intro names exactly what is asked', () => {
  assert.match(photoGateIntro({ needsEmail: true, needsPin: true, studio: 'herry shop' }), /email and the download PIN provided by herry shop to download this photo\.$/)
  assert.match(photoGateIntro({ needsEmail: false, needsPin: true, studio: 'herry shop' }), /^Please enter the download PIN provided by herry shop/)
  assert.equal(photoGateIntro({ needsEmail: true, needsPin: false }), 'Please enter your email to download this photo.')
})

test('photo sizes: only enabled ones, High Resolution first, Web Size states its real px', () => {
  const both = photoSizeOptions({ allowed_sizes: ['download', 'web'], web_px: 1024 })
  assert.deepEqual(both.map((o) => o.value), ['download', 'web'])
  assert.equal(both[0].note, undefined)
  assert.equal(both[1].note, 'Up to 1024 px')
  assert.deepEqual(photoSizeOptions({ allowed_sizes: ['web'], web_px: 640 }).map((o) => o.value), ['web'])
  assert.deepEqual(photoSizeOptions({ allowed_sizes: ['download'] }).map((o) => o.value), ['download'])
  assert.equal(defaultSize(both), 'download')
})

test('remember my selection: stored per gallery, only while still offered', () => {
  const storage = memoryStorage()
  const options = photoSizeOptions({ allowed_sizes: ['download', 'web'] })
  const key = photoPrefsKey('ana', 'wedding')
  assert.notEqual(key, photoPrefsKey('ana', 'other'))
  assert.equal(readRememberedSize(storage, key, options), null)
  writeRememberedSize(storage, key, 'web', true)
  assert.equal(readRememberedSize(storage, key, options), 'web')
  assert.equal(readRememberedSize(storage, photoPrefsKey('ana', 'other'), options), null)
  // the photographer switched Web Size off since: the old choice is ignored
  assert.equal(readRememberedSize(storage, key, photoSizeOptions({ allowed_sizes: ['download'] })), null)
  writeRememberedSize(storage, key, 'web', false)
  assert.equal(readRememberedSize(storage, key, options), null)
})

test('remembered selection survives blocked or corrupt storage', () => {
  const options = photoSizeOptions({ allowed_sizes: ['download', 'web'] })
  const blocked = { getItem() { throw new Error('denied') }, setItem() { throw new Error('denied') }, removeItem() { throw new Error('denied') } }
  assert.equal(readRememberedSize(blocked, 'k', options), null)
  assert.doesNotThrow(() => writeRememberedSize(blocked, 'k', 'web', true))
  assert.equal(readRememberedSize({ getItem: () => '{not json' }, 'k', options), null)
})
