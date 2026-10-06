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

test('storage usage reads in bytes-aware units, figures from a refusal in GB', async () => {
  const { formatStorageFigures, formatStorageUsage } = await import('./planLimits.js')
  assert.equal(formatStorageUsage({ storage_used_bytes: 2.99 * 1024 ** 3, plan_storage_limit_gb: 3 }), '2.99 GB / 3 GB')
  assert.equal(formatStorageUsage({ storage_used_bytes: 412 * 1024 ** 2, plan_storage_limit_gb: 3 }), '412.0 MB / 3 GB')
  assert.equal(formatStorageUsage({ storage_used_bytes: 1024 ** 3 - 9308, plan_storage_limit_gb: 1 }), '1.00 GB / 1 GB') // not '1024.0 MB'
  assert.equal(formatStorageUsage({ storage_used_bytes: 3.4 * 1024 ** 3, plan_storage_limit_gb: 1 }), '3.40 GB / 1 GB')
  assert.equal(formatStorageFigures(2.994, 3), '2.99 / 3 GB')
  assert.equal(formatStorageFigures(3.4, 1), '3.4 / 1 GB')
})

test('byte sizes above 2^31 are shown in full, not truncated to 32 bits (DB-A)', async () => {
  const { formatStorageUsage } = await import('./planLimits.js')
  const { formatBytes } = await import('./formatters.js')
  const GB = 1024 ** 3
  assert.equal(formatBytes(4 * GB), '4.00 GB')
  assert.equal(formatBytes(5 * GB), '5.00 GB')
  assert.equal(formatBytes(2 ** 31 + 1), '2.00 GB')
  assert.equal(formatStorageUsage({ storage_used_bytes: 8 * GB, plan_storage_limit_gb: 10 }), '8.00 GB / 10 GB')
})
