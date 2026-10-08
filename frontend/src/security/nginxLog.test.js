// 7F (reviewer F3): the SPA's nginx access log never records a query string.
import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'

const conf = readFileSync(new URL('../../nginx.conf', import.meta.url), 'utf8')
const live = conf.split('\n').filter((line) => !line.trim().startsWith('#')).join('\n')

test('the server block logs with the query-free format only', () => {
  const logs = [...live.matchAll(/access_log\s+([^;]+);/g)].map((m) => m[1].trim())
  assert.deepEqual(logs, ['/var/log/nginx/access.log kyapture_noquery'])
})

test('the format holds no variable that carries a query string', () => {
  const format = live.match(/log_format kyapture_noquery ([^;]+);/)[1]
  for (const leaky of ['$request ', '$request"', '$request_uri', '$args', '$query_string', '$is_args', '$http_referer', '$uri']) {
    assert.ok(!format.includes(leaky), leaky)
  }
  assert.ok(format.includes('$kyapture_log_path'))
  assert.ok(format.includes('$kyapture_log_referer'))
})

test('the path and Referer are cut at the first ? or #', () => {
  for (const name of ['kyapture_log_path', 'kyapture_log_referer']) {
    const block = live.match(new RegExp(`map \\$\\S+ \\$${name} \\{([^}]+)\\}`))[1]
    assert.match(block, /\[\^\?#\]\*/)
  }
})
