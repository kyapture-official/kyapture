import test from 'node:test'
import assert from 'node:assert/strict'
import { formatCollections, formatPhotoEstimate, formatStorage, formatVideoMinutes } from './planLimits.js'

test('video row: dash for none, minutes/hours, Unlimited when empty', () => {
  assert.equal(formatVideoMinutes(0), '—')
  assert.equal(formatVideoMinutes(30), '30 min')
  assert.equal(formatVideoMinutes(60), '1 hour')
  assert.equal(formatVideoMinutes(120), '2 hours')
  assert.equal(formatVideoMinutes(90), '1 hour 30 min')
  assert.equal(formatVideoMinutes(null), 'Unlimited')
  assert.equal(formatVideoMinutes(undefined), 'Unlimited')
})

test('collections row: a plain number, or Unlimited when empty', () => {
  assert.equal(formatCollections(10), '10')
  assert.equal(formatCollections(null), 'Unlimited')
})

test('photo estimate is only formatted from the API value, never computed here', () => {
  assert.equal(formatPhotoEstimate({ storage_gb: 3, estimated_photos: 1000 }), '1,000+ photos')
  assert.equal(formatPhotoEstimate({ storage_gb: 500, estimated_photos: 160000 }), '160,000+ photos')
  assert.equal(formatPhotoEstimate({ storage_gb: 3 }), '')           // no API value -> nothing invented
  assert.equal(formatStorage(3), '3 GB')
})
