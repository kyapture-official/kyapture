// 7F (reviewer F7): two tabs refreshing at once must not sign everyone out.
import test from 'node:test'
import assert from 'node:assert/strict'
import { REFRESH_LOCK_NAME, withRefreshLock } from './refreshLock.js'

/** The Web Locks API's exclusive mode, shared by every "tab" in the test like one origin. */
function fakeLocks() {
  const tails = new Map()
  const requested = []
  return {
    requested,
    request(name, options, callback) {
      requested.push(name)
      const previous = tails.get(name) || Promise.resolve()
      const run = previous.then(() => callback())
      tails.set(name, run.catch(() => {}))
      return run
    },
  }
}

/** A server whose refresh token rotates: the token sent is blacklisted, a new cookie is set. */
function rotatingServer() {
  const jar = { refresh: 'r0' }
  let current = 'r0'
  let n = 0
  const blacklisted = new Set()
  return {
    jar,
    async refresh() {
      const sent = jar.refresh                  // the cookie rides along when the request is SENT
      await new Promise((resolve) => setTimeout(resolve, 20))
      if (blacklisted.has(sent) || sent !== current) {
        const error = new Error('401')
        error.status = 401
        throw error
      }
      blacklisted.add(sent)
      n += 1
      current = `r${n}`
      jar.refresh = current                     // Set-Cookie on the response
      return 'ok'
    },
  }
}

test('without a lock, two tabs refreshing at once: the second is refused (the bug)', async () => {
  const server = rotatingServer()
  const results = await Promise.allSettled([server.refresh(), server.refresh()])
  assert.deepEqual(results.map((r) => r.status), ['fulfilled', 'rejected'])
})

test('under the shared lock, both tabs refresh and nobody is signed out', async () => {
  const server = rotatingServer()
  const locks = fakeLocks()
  const results = await Promise.allSettled([
    withRefreshLock(() => server.refresh(), locks),
    withRefreshLock(() => server.refresh(), locks),
    withRefreshLock(() => server.refresh(), locks),
  ])
  assert.deepEqual(results.map((r) => r.status), ['fulfilled', 'fulfilled', 'fulfilled'])
  assert.deepEqual(locks.requested, [REFRESH_LOCK_NAME, REFRESH_LOCK_NAME, REFRESH_LOCK_NAME])
})

test('a failed refresh still fails (a real expired session still signs out) and frees the lock', async () => {
  const locks = fakeLocks()
  await assert.rejects(withRefreshLock(async () => { throw new Error('401') }, locks))
  assert.equal(await withRefreshLock(async () => 'next', locks), 'next')
})

test('without the Web Locks API the refresh runs as before', async () => {
  assert.equal(await withRefreshLock(async () => 'ran', undefined), 'ran')
})
