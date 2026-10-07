import { test } from 'node:test'
import assert from 'node:assert/strict'

import { forgotErrorMessage, readResetToken, resetErrorState } from './resetFlow.js'

const TOKEN = 'Zq3_x-9aB4cD5eF6gH7iJ8kL9mN0oP1qR2sT3uV4wX5'

test('reads the token from the fragment', () => {
  assert.equal(readResetToken(`#token=${TOKEN}`), TOKEN)
  assert.equal(readResetToken(`token=${TOKEN}`), TOKEN)
  assert.equal(readResetToken(`#foo=1&token=${TOKEN}`), TOKEN)
})

test('no token, a short one or a malformed one reads as none', () => {
  for (const hash of ['', '#', '#token=', '#token=short', '#token=<script>alert(1)</script>xxxxxxxxxx',
    `#token=${'a'.repeat(129)}`, null, undefined, 42]) {
    assert.equal(readResetToken(hash), '', String(hash))
  }
})

test('maps an invalid or expired link', () => {
  assert.deepEqual(resetErrorState({ response: { status: 400, data: { code: 'reset_link_invalid', error: 'x' } } }),
    { kind: 'invalid' })
})

test('maps refused passwords to field messages', () => {
  const state = resetErrorState({ response: { status: 400, data: {
    new_password: ['This password is too common.', "Your password can't be your email address."] } } })
  assert.deepEqual(state, {
    kind: 'fields', password: ['This password is too common.', "Your password can't be your email address."], confirm: '',
  })
  assert.equal(resetErrorState({ response: { status: 400, data: { new_password2: ['Passwords do not match.'] } } }).confirm,
    'Passwords do not match.')
})

test('maps throttling and anything else', () => {
  assert.equal(resetErrorState({ response: { status: 429, data: {} } }).kind, 'throttled')
  assert.equal(resetErrorState({}).kind, 'error')
  assert.equal(resetErrorState({ response: { status: 500, data: 'oops' } }).kind, 'error')
})

test('forgot page messages', () => {
  assert.equal(forgotErrorMessage({ response: { status: 400, data: { code: 'email_invalid' } } }), 'Enter a valid email address.')
  assert.match(forgotErrorMessage({ response: { status: 429 } }), /Too many reset requests/)
  assert.match(forgotErrorMessage({}), /Something went wrong/)
})
