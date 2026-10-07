// 7-B (debt rows 120, 37): the SPA's Content-Security-Policy in nginx.conf.
import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'

const conf = readFileSync(new URL('../../nginx.conf', import.meta.url), 'utf8')
const policies = [...conf.matchAll(/add_header Content-Security-Policy "([^"]+)"/g)].map((m) => m[1])

test('every response block carries the same CSP', () => {
  assert.equal(policies.length, 3)
  assert.equal(new Set(policies).size, 1)
})

test('no Google font host is allowed any more (fonts are self-hosted)', () => {
  for (const policy of policies) {
    assert.ok(!policy.includes('fonts.googleapis.com'), policy)
    assert.ok(!policy.includes('fonts.gstatic.com'), policy)
  }
  assert.match(policies[0], /font-src 'self'( data:)?;/)
  assert.match(policies[0], /style-src 'self' 'unsafe-inline';/)
})

test('the header comment no longer says that no CSP is set', () => {
  assert.ok(!/No\s+#?\s*Content-Security-Policy is added/.test(conf))
})
