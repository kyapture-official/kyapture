import test from 'node:test'
import assert from 'node:assert/strict'
import {
  buildFeedbackPayload,
  isWorkspacePath,
  describeFeedbackError,
  MESSAGE_MAX,
  pathOnly,
  SUBJECT_MAX,
  validateFeedback,
  widgetVisibleOn,
} from './feedbackFlow.js'
import { APP_VERSION } from './appVersion.js'

const httpError = (status, data = {}, headers = {}) => Object.assign(new Error(String(status)), { response: { status, data, headers } })

test('the widget shows on the dashboard and workspace only, never on public, auth or landing routes', () => {
  for (const ok of ['/dashboard', '/dashboard/', '/dashboard/galleries', '/dashboard/galleries/my-slug/design', '/dashboard/feedback']) {
    assert.equal(widgetVisibleOn(ok), true, ok)
  }
  for (const no of ['/', '/login', '/register', '/forgot-password', '/pricing', '/g/user', '/g/user/slug', '/g/user/slug/download',
    '/g/user/slug/download/file/abc', '/dashboardx', '/auth/password/reset/confirm/a/b', '', null, undefined]) {
    assert.equal(widgetVisibleOn(no), false, String(no))
  }
})

test('workspace paths (which have the phone bottom bars) are told apart from the dashboard pages', () => {
  assert.equal(isWorkspacePath('/dashboard/galleries/my-slug'), true)
  assert.equal(isWorkspacePath('/dashboard/galleries/my-slug/settings'), true)
  for (const no of ['/dashboard', '/dashboard/galleries', '/dashboard/galleries/', '/dashboard/feedback', '/dashboard/settings/general']) {
    assert.equal(isWorkspacePath(no), false, no)
  }
})

test('pathOnly drops query, fragment and anything that is not a plain path', () => {
  assert.equal(pathOnly('/dashboard/galleries/x?token=abc&pin=1234#frag'), '/dashboard/galleries/x')
  assert.equal(pathOnly('https://kyapture.com/dashboard?token=1'), '')
  assert.equal(pathOnly('//evil.example/x'), '')
  assert.equal(pathOnly(undefined), '')
})

test('the submit body is the form plus path and version only; an empty subject is omitted', () => {
  const body = buildFeedbackPayload({ category: 'bug', subject: '   ', message: '  It broke  ' }, '/dashboard/galleries/x?set=1', '9.9.9')
  assert.deepEqual(body, { category: 'bug', message: 'It broke', route: '/dashboard/galleries/x', app_version: '9.9.9' })
  const withSubject = buildFeedbackPayload({ category: 'other', subject: ' Hi ', message: 'm' }, '/dashboard')
  assert.equal(withSubject.subject, 'Hi')
  assert.equal(withSubject.app_version, APP_VERSION)
  assert.deepEqual(Object.keys(withSubject).sort(), ['app_version', 'category', 'message', 'route', 'subject'])
})

test('the build version defaults to the backend default ("dev") when no build value is set', () => {
  assert.equal(APP_VERSION, 'dev')
})

test('validation: category and message are required, lengths are limited, subject is optional', () => {
  assert.deepEqual(validateFeedback({ category: 'bug', subject: '', message: 'x' }), {})
  assert.ok(validateFeedback({ category: '', subject: '', message: 'x' }).category)
  assert.ok(validateFeedback({ category: 'praise', subject: '', message: 'x' }).category)
  assert.ok(validateFeedback({ category: 'bug', subject: '', message: '   ' }).message)
  assert.ok(validateFeedback({ category: 'bug', subject: '', message: 'a'.repeat(MESSAGE_MAX + 1) }).message)
  assert.deepEqual(validateFeedback({ category: 'bug', subject: 's'.repeat(SUBJECT_MAX), message: 'a'.repeat(MESSAGE_MAX) }), {})
  assert.ok(validateFeedback({ category: 'bug', subject: 's'.repeat(SUBJECT_MAX + 1), message: 'x' }).subject)
})

test('errors: 429 says to retry later (with minutes from Retry-After), 403 is a clear permission message', () => {
  const limited = describeFeedbackError(httpError(429, { detail: 'throttled' }, { 'retry-after': '1800' }), 'submit')
  assert.equal(limited.status, 429)
  assert.match(limited.message, /in about 30 minutes/)
  assert.match(limited.message, /kept/)
  assert.match(describeFeedbackError(httpError(429), 'inbox').message, /a little later/)
  assert.match(describeFeedbackError(httpError(403, { detail: 'Staff access required.' }), 'inbox').message, /Staff access is required/)
  assert.match(describeFeedbackError(httpError(403), 'status').message, /Staff access is required/)
  assert.match(describeFeedbackError(httpError(403), 'submit').message, /not allowed to send feedback/)
})

test('errors: a field error from the server is surfaced by field; a network failure reads as one', () => {
  const bad = describeFeedbackError(httpError(400, { error: 'Invalid', details: { message: ['This field may not be blank.'] } }), 'submit')
  assert.equal(bad.fieldErrors.message, 'This field may not be blank.')
  const offline = describeFeedbackError(new Error('Network Error'), 'submit')
  assert.match(offline.message, /Network error/)
})
