import test from 'node:test'
import assert from 'node:assert/strict'
import {
  cheapestVideoPlan,
  collectionLimitInfo,
  collectionLimitReached,
  planVideoFiles,
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

test('video: a plan with no video drops videos, keeps photos, reports video_not_in_plan', () => {
  const files = [img('a.jpg'), vid('b.mp4'), img('c.jpg')]
  const { allowed, block } = planVideoFiles(files, usage({ video_minutes_limit: 0 }))
  assert.deepEqual(allowed.map((f) => f.name), ['a.jpg', 'c.jpg'])
  assert.equal(block.code, 'video_not_in_plan')
})

test('video: no videos, unlimited plan, or unknown usage never block', () => {
  const files = [img('a.jpg'), vid('b.mp4')]
  assert.equal(planVideoFiles([img('a.jpg')], usage({ video_minutes_limit: 0 })).block, null)
  assert.equal(planVideoFiles(files, usage({ video_minutes_limit: null })).block, null)
  assert.equal(planVideoFiles(files, null).allowed.length, 2)
})

test('video: all minutes used blocks the videos, keeps photos, reports used / limit', () => {
  const { allowed, block } = planVideoFiles([vid('b.mp4'), img('a.jpg')], usage({ video_minutes_limit: 10, video_minutes_used: 10 }))
  assert.deepEqual(allowed.map((f) => f.name), ['a.jpg'])
  assert.deepEqual([block.code, block.used_minutes, block.plan_limit_minutes], ['video_minutes_exceeded', 10, 10])
})

test('video: minutes left means the server decides by the real length (no client guess)', () => {
  const files = [vid('a.mp4'), img('b.jpg')]
  const { allowed, block } = planVideoFiles(files, usage({ video_minutes_limit: 10, video_minutes_used: 9.5 }))
  assert.equal(allowed.length, 2)
  assert.equal(block, null)
})

test('video: the server 403 codes are the fallback; other errors are not video limits', () => {
  assert.equal(videoLimitFromError({ code: 'video_not_in_plan' }).code, 'video_not_in_plan')
  assert.deepEqual(
    videoLimitFromError({ code: 'video_minutes_exceeded', used_minutes: 4.5, plan_limit_minutes: 5 }),
    { code: 'video_minutes_exceeded', used_minutes: 4.5, plan_limit_minutes: 5 },
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
