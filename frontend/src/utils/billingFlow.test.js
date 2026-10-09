import test from 'node:test'
import assert from 'node:assert/strict'
import {
  billingState, describeSubmitError, expiryNotice, livePlanOf, paymentDetail, proofProblem, referenceProblem,
} from './billingFlow.js'

const httpError = (status, data = {}) => Object.assign(new Error(String(status)), { response: { status, data, headers: {} } })
const MB = 1024 * 1024
const file = (name, type, size = 1000) => ({ name, type, size })

test('a transaction ID is 4-64 plain characters with no spaces', () => {
  assert.equal(referenceProblem('FT24-ABC/9'), '')
  assert.equal(referenceProblem('  0009XYZ  '), '')
  for (const bad of ['', '   ', 'ab', 'x'.repeat(65), 'has space', '<script>', '-lead', 'trail-', undefined]) {
    assert.notEqual(referenceProblem(bad), '', String(bad))
  }
})

test('a proof is an image or a PDF within the size limit', () => {
  assert.equal(proofProblem(file('a.png', 'image/png')), '')
  assert.equal(proofProblem(file('scan.PDF', 'application/pdf')), '')
  assert.equal(proofProblem(file('shot.jpeg', '')), '', 'the extension counts when the browser gives no type')
  assert.match(proofProblem(file('a.gif', 'image/gif')), /PNG, JPEG or WEBP/)
  assert.match(proofProblem(file('a.exe', 'application/octet-stream')), /PNG, JPEG or WEBP/)
  assert.match(proofProblem(file('big.png', 'image/png', 5 * MB + 1)), /5 MB or smaller/)
  assert.equal(proofProblem(file('edge.png', 'image/png', 5 * MB)), '')
  assert.match(proofProblem(file('big.png', 'image/png', 3 * MB), 2), /2 MB or smaller/)
  assert.match(proofProblem(file('empty.png', 'image/png', 0)), /empty/)
  assert.match(proofProblem(null), /Choose/)
})

test('the live plan is an active subscription whose period has not ended', () => {
  const plan = { id: 'p', name: 'Pro' }
  assert.equal(livePlanOf({ status: 'active', is_expired: false, plan }), plan)
  assert.equal(livePlanOf({ status: 'active', is_expired: true, plan }), null, 'a lapsed period is Free even if the row still says active')
  assert.equal(livePlanOf({ status: 'expired', is_expired: true, plan }), null)
  assert.equal(livePlanOf({ status: 'no_subscription', plan: null }), null)
  assert.equal(livePlanOf(null), null)
})

test('billing state: free, active, lapsed, pending and rejected', () => {
  const plan = { id: 'p', name: 'Pro' }
  assert.equal(billingState({ subscription: { status: 'no_subscription', plan: null }, payments: [] }).kind, 'free')
  assert.equal(billingState({ subscription: { status: 'active', is_expired: false, plan }, payments: [] }).kind, 'active')
  assert.equal(billingState({ subscription: { status: 'active', is_expired: true, plan }, payments: [] }).kind, 'lapsed')
  assert.equal(billingState({ subscription: { status: 'expired', is_expired: true, plan }, payments: [] }).kind, 'lapsed')
  const rejected = { id: '2', status: 'rejected', rejection_reason: 'Wrong amount' }
  const pending = { id: '3', status: 'pending' }
  assert.deepEqual(billingState({ subscription: null, payments: [rejected] }).rejected, rejected)
  assert.equal(billingState({ subscription: null, payments: [pending, rejected] }).rejected, null, 'a newer payment replaces the rejection notice')
  assert.deepEqual(billingState({ subscription: null, payments: [pending, rejected] }).pending, [pending])
  assert.deepEqual(billingState({ subscription: null, payments: undefined }), { kind: 'free', pending: [], rejected: null })
})

test('a history row says why it was rejected or how long the plan runs', () => {
  const format = (value) => `<${value}>`
  assert.equal(paymentDetail({ status: 'rejected', rejection_reason: 'Wrong amount' }, format), 'Wrong amount')
  assert.equal(paymentDetail({ status: 'rejected', rejection_reason: '' }, format), 'Not approved.')
  assert.equal(paymentDetail({ status: 'approved', period_end: '2026-11-01' }, format), 'Plan runs until <2026-11-01>')
  assert.equal(paymentDetail({ status: 'approved' }, format), 'Approved')
  assert.equal(paymentDetail({ status: 'pending' }, format), 'Waiting for review')
})

test('a refused submit shows the server sentence and its field messages', () => {
  const error = httpError(400, {
    error: 'This transaction ID was already submitted.', code: 'reference_taken',
    errors: { reference: ['This transaction ID was already submitted.'] },
  })
  const described = describeSubmitError(error)
  assert.equal(described.message, 'This transaction ID was already submitted.')
  assert.equal(described.fieldErrors.reference, 'This transaction ID was already submitted.')
  assert.equal(described.code, 'reference_taken')
  assert.match(describeSubmitError(httpError(429)).message, /Too many/)
  assert.match(describeSubmitError({}).message, /Network error/)
})

test('the expiry notice words the server lifecycle block: days, today, expired, nothing', () => {
  assert.deepEqual(expiryNotice({ state: 'active', days_left: 20 }), { state: 'active', label: 'Expires in 20 days', banner: false })
  assert.deepEqual(expiryNotice({ state: 'expiring', days_left: 3 }), { state: 'expiring', label: 'Expires in 3 days', banner: true })
  assert.equal(expiryNotice({ state: 'expiring', days_left: 1 }).label, 'Expires in 1 day')
  assert.equal(expiryNotice({ state: 'expiring', days_left: 0 }).label, 'Expires today')
  assert.deepEqual(expiryNotice({ state: 'expired', days_left: -2 }), { state: 'expired', label: 'Expired', banner: true })
  for (const none of [null, undefined, {}, { state: 'none' }, { state: 'active', days_left: null }, { state: 'active', days_left: -1 }]) {
    assert.equal(expiryNotice(none), null, JSON.stringify(none))
  }
})
