import test from 'node:test'
import assert from 'node:assert/strict'
import {
  cheapestVideoPlan,
  collectionLimitInfo,
  collectionLimitReached,
  checkVideoBatch,
  videoLimitFromError,
} from './planLimitFlow.js'

const vid = (name) => ({ name, type: 'video/mp4' })
const img = (name) => ({ name, type: 'image/jpeg' })
// Usage-endpoint shapes; the numbers are test fixtures, not product limits.
const usage = (over) => ({
  plan_name: 'P', plan_gallery_limit: 4, galleries_used: 4, galleries_remaining: 0,
  video_minutes_limit: 0, video_minutes_used: 0, ...over,
})

test('collections: at the cap blocks, one below does not, unlimited never does', () => {
  assert.equal(collectionLimitReached(usage({})), true)
  assert.equal(collectionLimitReached(usage({ galleries_used: 3, galleries_remaining: 1 })), false)
  assert.equal(collectionLimitReached(usage({ plan_gallery_limit: null, galleries_remaining: null })), false)
  assert.equal(collectionLimitReached(null), false) // count unknown: the form opens, the server decides
  assert.deepEqual(collectionLimitInfo(usage({})), { plan_name: 'P', plan_limit: 4, current_count: 4 })
})

// The pre-flight is the server's call: these fakes record what the flow sends and answer as it would.
const refusal = (data) => Object.assign(new Error('403'), { response: { status: 403, data } })
const harness = ({ lengths = {}, answer } = {}) => {
  const sent = []
  return {
    sent,
    deps: {
      readDuration: async (file) => (file.name in lengths ? lengths[file.name] : null),
      preflight: async (count, durations) => {
        sent.push({ count, durations })
        if (answer) throw answer
        return { allowed: true }
      },
    },
  }
}

test('video: no videos in the batch means no pre-flight request at all', async () => {
  const { deps, sent } = harness()
  const files = [img('a.jpg'), img('b.jpg')]
  const result = await checkVideoBatch(files, deps)
  assert.deepEqual([result.allowed, result.block, sent.length], [files, null, 0])
})

test('video: sends the video count and each readable length, never the photos', async () => {
  const { deps, sent } = harness({ lengths: { 'a.mp4': 12.5, 'b.mp4': 40 } })
  const result = await checkVideoBatch([img('p.jpg'), vid('a.mp4'), vid('b.mp4'), vid('c.mov')], deps)
  assert.deepEqual(sent, [{ count: 3, durations: [12.5, 40] }]) // c.mov unreadable: counted, not measured
  assert.equal(result.block, null)
  assert.equal(result.allowed.length, 4)
})

test('video: a refusal drops every video, keeps the photos, carries the server figures', async () => {
  const body = { code: 'video_minutes_exceeded', used_minutes: 9, plan_limit_minutes: 10, upload_minutes: 3, error: 'x' }
  const { deps } = harness({ lengths: { 'a.mp4': 180 }, answer: refusal(body) })
  const { allowed, block } = await checkVideoBatch([img('p.jpg'), vid('a.mp4'), img('q.jpg')], deps)
  assert.deepEqual(allowed.map((f) => f.name), ['p.jpg', 'q.jpg'])
  assert.deepEqual(block, { code: 'video_minutes_exceeded', used_minutes: 9, plan_limit_minutes: 10, upload_minutes: 3 })
})

test('video: not-in-plan refusal needs no readable length (count alone)', async () => {
  const { deps, sent } = harness({ answer: refusal({ code: 'video_not_in_plan', used_minutes: 0, plan_limit_minutes: 0 }) })
  const { allowed, block } = await checkVideoBatch([vid('a.mov')], deps)
  assert.deepEqual([allowed.length, block.code, sent[0]], [0, 'video_not_in_plan', { count: 1, durations: [] }])
})

test('video: a pre-flight that fails for any other reason lets the upload decide', async () => {
  for (const answer of [Object.assign(new Error('net'), {}), refusal({ code: 'storage_limit_reached' }),
    Object.assign(new Error('429'), { response: { status: 429, data: {} } })]) {
    const { deps } = harness({ lengths: { 'a.mp4': 5 }, answer })
    const result = await checkVideoBatch([vid('a.mp4'), img('p.jpg')], deps)
    assert.equal(result.block, null)
    assert.equal(result.allowed.length, 2)
  }
})

test('video: lengths of a big drop are read a few at a time, all of them', async () => {
  let running = 0
  let peak = 0
  const deps = {
    readDuration: async () => {
      running += 1
      peak = Math.max(peak, running)
      await new Promise((resolve) => setTimeout(resolve, 2))
      running -= 1
      return 1
    },
    preflight: async () => ({ allowed: true }),
  }
  const files = Array.from({ length: 10 }, (_, i) => vid(`v${i}.mp4`))
  await checkVideoBatch(files, deps)
  assert.ok(peak > 1 && peak <= 4, `peak concurrent reads was ${peak}`)
})

test('video: the server 403 codes are the fallback; other errors are not video limits', () => {
  assert.equal(videoLimitFromError({ code: 'video_not_in_plan' }).code, 'video_not_in_plan')
  assert.deepEqual(
    videoLimitFromError({ code: 'video_minutes_exceeded', used_minutes: 4.5, plan_limit_minutes: 5 }),
    { code: 'video_minutes_exceeded', used_minutes: 4.5, plan_limit_minutes: 5, upload_minutes: undefined },
  )
  assert.equal(videoLimitFromError({ code: 'storage_limit_reached' }), null)
  assert.equal(videoLimitFromError(undefined), null)
})

test('video plan name comes from the plans API: cheapest paid plan with a video allowance', () => {
  const plans = [
    { name: 'F', is_free: true, price: '0', video_minutes: 0 },
    { name: 'B', is_free: false, price: '500', video_minutes: 0 },
    { name: 'S', is_free: false, price: '3000', video_minutes: 120 },
    { name: 'P', is_free: false, price: '1500', video_minutes: 60 },
  ]
  assert.equal(cheapestVideoPlan(plans).name, 'P')
  assert.equal(cheapestVideoPlan([plans[0], plans[1]]), null)
  assert.equal(cheapestVideoPlan([{ name: 'U', is_free: false, price: '9', video_minutes: null }]).name, 'U') // empty = unlimited
})
