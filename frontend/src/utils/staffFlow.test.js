import test from 'node:test'
import assert from 'node:assert/strict'
import {
  AUDIT_ACTIONS, canChangeStatus, describeStaffError, looksLikeEmail, planOptions, reasonProblem,
  REASON_MAX, storageSummary, statusLabel,
} from './staffFlow.js'

const httpError = (status, data = {}, headers = {}) => Object.assign(new Error(String(status)), { response: { status, data, headers } })

test('the search box accepts one complete address only', () => {
  assert.equal(looksLikeEmail('a@b.com'), true)
  assert.equal(looksLikeEmail('  a@b.com '), true)
  for (const bad of ['', 'a', 'a@', '@b.com', 'a@b', 'a b@c.com', 'a@b.com, c@d.com', '%', `${'x'.repeat(300)}@b.com`]) {
    assert.equal(looksLikeEmail(bad), false, bad)
  }
})

test('a reason is one to 300 characters of plain text', () => {
  assert.equal(reasonProblem(''), 'Enter a reason.')
  assert.equal(reasonProblem('  \n\t '), 'Enter a reason.')
  assert.equal(reasonProblem(undefined), 'Enter a reason.')
  assert.equal(reasonProblem('x'.repeat(REASON_MAX)), '')
  assert.match(reasonProblem('x'.repeat(REASON_MAX + 1)), /under 300/)
  assert.equal(reasonProblem('two\nlines'), '')
  assert.equal(reasonProblem('<script>alert(1)</script>'), '', 'text is allowed; the page renders it escaped')
})

test('storage reads against the plan limit and never exceeds 100%', () => {
  assert.deepEqual(storageSummary({ storage_used_bytes: 0, storage_limit_bytes: 1073741824 }), { percent: 0, label: '0 B of 1.00 GB', full: false })
  assert.equal(storageSummary({ storage_used_bytes: 536870912, storage_limit_bytes: 1073741824 }).percent, 50)
  const over = storageSummary({ storage_used_bytes: 3 * 1073741824, storage_limit_bytes: 1073741824 })
  assert.deepEqual([over.percent, over.full], [100, true])
  assert.equal(storageSummary({}).percent, 0)
  assert.equal(storageSummary({ storage_used_bytes: 5, storage_limit_bytes: 0 }).full, false)
})

test('staff rows cannot be suspended from the page', () => {
  assert.equal(canChangeStatus({ is_staff: true }), false)
  assert.equal(canChangeStatus({ is_staff: false }), true)
})

test('errors are readable and use the server codes', () => {
  assert.equal(describeStaffError(httpError(400, { error: 'x', code: 'invalid_email_query' })).message, 'Search needs one complete email address.')
  assert.equal(describeStaffError(httpError(409, { error: 'x', code: 'already_suspended' })).code, 'already_suspended')
  assert.match(describeStaffError(httpError(403, { error: 'Staff access required.', code: 'permission_denied' })).message, /Staff access/)
  assert.equal(describeStaffError(httpError(403, { error: 'no', code: 'cannot_change_staff' })).message, 'Staff accounts are managed in the admin, not here.')
  assert.match(describeStaffError(httpError(429, {}, { 'retry-after': '120' })).message, /about 2 minutes/)
  assert.match(describeStaffError(httpError(429)).message, /a little later/)
  assert.match(describeStaffError({}).message, /Network error/)
})

test('plan options start with Free and never repeat a plan', () => {
  const options = planOptions([{ key: 'free', name: 'Free' }, { key: 'pro', name: 'Pro' }, { key: 'pro', name: 'Pro' }, { name: 'no key' }])
  assert.deepEqual(options.map((o) => o.value), ['', 'free', 'pro'])
  assert.deepEqual(planOptions(undefined).map((o) => o.value), ['', 'free'])
})

test('labels cover the server actions and statuses', () => {
  assert.equal(statusLabel('suspended'), 'Suspended')
  assert.equal(statusLabel('active'), 'Active')
  assert.ok(AUDIT_ACTIONS.some((a) => a.value === 'account.suspend'))
  assert.equal(new Set(AUDIT_ACTIONS.map((a) => a.value)).size, AUDIT_ACTIONS.length)
})
