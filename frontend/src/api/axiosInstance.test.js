// 7G (reviewer 7R-2 R5): the axios 401 -> refresh interceptor itself, not only the lock helper.
// Two "tabs" are two instances of the real axiosInstance.js module (one origin: one cookie jar,
// one localStorage, one Web Lock). axios is mocked at the adapter level; the lock is a fake
// exclusive lock. Removing the lock (or refreshOnce) from axiosInstance.js fails these tests.
import test, { beforeEach } from 'node:test'
import assert from 'node:assert/strict'
import axios from 'axios'
import { REFRESH_LOCK_NAME } from './refreshLock.js'

/** The Web Locks API's exclusive mode, shared by every tab like one origin. */
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

function memoryStorage() {
  const data = new Map()
  return { getItem: (k) => (data.has(k) ? data.get(k) : null), setItem: (k, v) => data.set(k, String(v)) }
}

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms))

/** One origin's cookie jar and a server whose refresh token rotates (the one sent is blacklisted). */
function rotatingServer() {
  const jar = { access: 'a0', refresh: 'r0' }
  const state = { validAccess: 'a0', currentRefresh: 'r0', n: 0, refreshes: 0, refreshFails: false }
  const reply = (config, status, data) => {
    const response = { data, status, statusText: String(status), headers: {}, config, request: {} }
    if (status >= 400) {
      throw new axios.AxiosError(`Request failed with status code ${status}`, 'ERR_BAD_REQUEST', config, {}, response)
    }
    return response
  }
  return {
    jar,
    state,
    async api(config) {                          // every app request: the access cookie rides along
      const sent = jar.access
      await sleep(5)
      return sent === state.validAccess ? reply(config, 200, { ok: true }) : reply(config, 401, { code: 'token_not_valid' })
    },
    async refresh(config) {                      // bare axios.post('/auth/token/refresh/')
      const sent = jar.refresh
      await sleep(20)
      if (state.refreshFails || sent !== state.currentRefresh) return reply(config, 401, { code: 'token_not_valid' })
      state.n += 1
      state.refreshes += 1
      state.currentRefresh = `r${state.n}`
      state.validAccess = `a${state.n}`
      jar.refresh = state.currentRefresh          // the response sets the new cookies
      jar.access = state.validAccess
      return reply(config, 200, {})
    },
  }
}

let server, locks, logouts, tabSeq = 0

async function openTab() {
  tabSeq += 1
  const { default: api } = await import(`./axiosInstance.js?tab=${tabSeq}`)
  api.defaults.adapter = (config) => server.api(config)
  return api
}

beforeEach(() => {
  server = rotatingServer()
  locks = fakeLocks()
  logouts = 0
  const win = new EventTarget()
  win.addEventListener('auth-session-expired', () => { logouts += 1 })
  Object.defineProperty(globalThis, 'navigator', { value: { locks }, configurable: true })
  Object.defineProperty(globalThis, 'localStorage', { value: memoryStorage(), configurable: true })
  Object.defineProperty(globalThis, 'window', { value: win, configurable: true })
  axios.defaults.adapter = (config) => server.refresh(config)
})

test('a 401 refreshes under the shared cross-tab lock, then retries the request', async () => {
  const tab = await openTab()
  server.state.validAccess = 'expired'
  const response = await tab.get('/galleries/')
  assert.equal(response.status, 200)
  assert.deepEqual(locks.requested, [REFRESH_LOCK_NAME])
  assert.equal(server.state.refreshes, 1)
  assert.equal(logouts, 0)
})

test('two tabs whose access expired together both keep working, with ONE token rotation', async () => {
  const [a, b] = [await openTab(), await openTab()]
  server.state.validAccess = 'expired'
  const [ra, rb] = await Promise.all([a.get('/galleries/'), b.get('/notifications/')])
  assert.deepEqual([ra.status, rb.status], [200, 200])
  assert.equal(logouts, 0)                                  // without the lock the 2nd refresh got 401 -> logout
  assert.equal(locks.requested.length, 2)                   // each tab went through the lock
  assert.equal(server.state.refreshes, 1)                   // the waiting tab reused the first refresh
})

test('a tab whose request left AFTER the last refresh still refreshes', async () => {
  const tab = await openTab()
  server.state.validAccess = 'expired'
  await tab.get('/galleries/')
  server.state.validAccess = 'expired-again'                // the new access token expired too
  await sleep(5)
  const response = await tab.get('/galleries/')
  assert.equal(response.status, 200)
  assert.equal(server.state.refreshes, 2)
})

test('a failed refresh signs out once and rejects the request', async () => {
  const tab = await openTab()
  server.state.validAccess = 'expired'
  server.state.refreshFails = true
  await assert.rejects(tab.get('/galleries/'))
  assert.equal(logouts, 1)
})

test('a 401 from a public gallery route never refreshes or signs out', async () => {
  const tab = await openTab()
  server.state.validAccess = 'expired'
  await assert.rejects(tab.get('/public/someone/some-gallery/'), (error) => error.response?.status === 401)
  assert.equal(server.state.refreshes, 0)
  assert.deepEqual(locks.requested, [])
  assert.equal(logouts, 0)
})
