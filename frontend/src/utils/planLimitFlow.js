// File Location: frontend/src/utils/planLimitFlow.js
// Click-time plan-limit decisions for the collection and video flows. Pure
// functions over the usage endpoint (GET galleries/dashboard/stats/) and the
// plans API: no plan name, limit or price is known here. The server still
// enforces everything; this only avoids a doomed request.

const VIDEO_NOT_IN_PLAN = 'video_not_in_plan'
const VIDEO_MINUTES_EXCEEDED = 'video_minutes_exceeded'

export const VIDEO_LIMIT_CODES = [VIDEO_NOT_IN_PLAN, VIDEO_MINUTES_EXCEEDED]

export const isVideoFile = (file) => Boolean(file?.type) && file.type.startsWith('video/')

/** At the collection cap: the plan has a limit (empty = unlimited) and no slots remain. */
export const collectionLimitReached = (usage) =>
  Boolean(usage) && usage.plan_gallery_limit != null && usage.galleries_remaining === 0

/** The figures the shared limit modal shows, in the shape the 403 gallery_limit_reached body uses. */
export const collectionLimitInfo = (usage) => ({
  plan_name: usage.plan_name,
  plan_limit: usage.plan_gallery_limit,
  current_count: usage.galleries_used,
})

/** The cheapest paid plan that includes video (0 = none, empty = unlimited), or null. */
export const cheapestVideoPlan = (plans) =>
  (Array.isArray(plans) ? plans : [])
    .filter((plan) => !plan.is_free && plan.video_minutes !== 0)
    .sort((a, b) => Number(a.price) - Number(b.price))[0] || null

/** Server 403 body -> the video-limit modal state, or null when it is some other error. */
export const videoLimitFromError = (data) =>
  data && VIDEO_LIMIT_CODES.includes(data.code)
    ? {
        code: data.code,
        used_minutes: data.used_minutes,
        plan_limit_minutes: data.plan_limit_minutes,
        upload_minutes: data.upload_minutes,
      }
    : null

const STORAGE_LIMIT_REACHED = 'storage_limit_reached'

/** Server 403 body -> the storage-limit modal state, or null when it is some other error. */
export const storageLimitFromError = (data) =>
  data && data.code === STORAGE_LIMIT_REACHED
    ? {
        plan_name: data.plan_name,
        used_gb: data.used_gb,
        plan_limit_gb: data.plan_limit_gb,
        refused_count: data.refused_count ?? 1,
      }
    : null

/**
 * An upload answer is a plain list of assets when everything was stored. When
 * only part of a batch fit, it is { uploaded, refused, storage } (see the upload
 * endpoint). Either way: the stored assets, and the storage refusal to show (or null).
 */
export const readUploadResponse = (data) => {
  if (Array.isArray(data)) return { assets: data, storageRefusal: null }
  if (data && Array.isArray(data.uploaded)) {
    const refused = Array.isArray(data.refused) ? data.refused : []
    return {
      assets: data.uploaded,
      storageRefusal: refused.length
        ? storageLimitFromError({ ...data.storage, code: STORAGE_LIMIT_REACHED, refused_count: refused.length })
        : null,
    }
  }
  return { assets: data ? [data] : [], storageRefusal: null }
}

/**
 * Click-time storage check, from the usage endpoint's own remaining space:
 * files are taken in order while they still fit (a smaller file after a refused
 * larger one may still go in), the same rule the server applies. No limit in the
 * usage answer (staff) means everything may go. The server decides again at upload.
 * Returns { allowed: File[], refused: File[] }.
 */
export const splitByStorage = (files, usage) => {
  if (!usage || usage.storage_remaining_bytes == null) return { allowed: files, refused: [] }
  let remaining = usage.storage_remaining_bytes
  const allowed = []
  const refused = []
  for (const file of files) {
    if (file.size <= remaining) {
      allowed.push(file)
      remaining -= file.size
    } else {
      refused.push(file)
    }
  }
  return { allowed, refused }
}

/** The figures the storage modal shows, from the usage endpoint (same shape as storageLimitFromError). */
export const storageLimitInfo = (usage, refusedCount) => ({
  plan_name: usage.plan_name,
  used_gb: usage.storage_used_gb,
  plan_limit_gb: usage.plan_storage_limit_gb,
  refused_count: refusedCount,
})

const MB = 1024 * 1024

/**
 * Click-time per-file size check against the limits the usage endpoint returns
 * (`usage.upload_limits`: max_image_mb / max_image_pixels / max_video_mb, edited
 * by the owner in admin). A file over its limit never uploads; its reason shows
 * on that file and the rest of the batch goes ahead. 1 MB = 1024 * 1024 bytes,
 * the same unit and wording the server uses. The pixel limit is NOT checked here
 * (huge images are never decoded in the browser): the server refuses those from
 * the image header. No limits in the answer: everything goes, the server decides.
 * Returns { allowed: File[], rejected: { file, message }[] }.
 */
export const splitByFileLimits = (files, usage) => {
  const limits = usage?.upload_limits
  if (!limits) return { allowed: files, rejected: [] }
  const allowed = []
  const rejected = []
  for (const file of files) {
    const limitMb = isVideoFile(file) ? limits.max_video_mb : limits.max_image_mb
    if (Number.isFinite(limitMb) && file.size > limitMb * MB) {
      rejected.push({ file, message: `Size exceeds ${limitMb} MB limit` })
    } else {
      allowed.push(file)
    }
  }
  return { allowed, rejected }
}

const READ_CHUNK = 4

/**
 * Splits a selection into what may upload and what the plan refuses, BEFORE any
 * upload request. The browser reads each video's length (`readDuration`), the
 * server judges them together (`preflight(videoCount, durations)`, the same rule
 * and refusal as the upload): this module does no minute arithmetic and knows no
 * limit. A length the browser cannot read is simply left out of `durations`; if
 * the pre-flight itself fails (network, throttle, bad input) the files go ahead
 * and the upload's own authoritative check decides.
 *
 * Returns { allowed: File[], block: null | { code, used_minutes, plan_limit_minutes, upload_minutes } }.
 * A refusal drops every video of the batch and keeps the photos.
 */
export async function checkVideoBatch(files, { readDuration, preflight }) {
  const videos = files.filter(isVideoFile)
  if (!videos.length) return { allowed: files, block: null }

  const lengths = []
  for (let i = 0; i < videos.length; i += READ_CHUNK) {
    lengths.push(...(await Promise.all(videos.slice(i, i + READ_CHUNK).map((file) => readDuration(file)))))
  }
  const durations = lengths.filter((seconds) => Number.isFinite(seconds) && seconds > 0)

  try {
    await preflight(videos.length, durations)
  } catch (error) {
    const refusal = error?.response?.status === 403 ? videoLimitFromError(error.response.data) : null
    if (refusal) return { allowed: files.filter((file) => !isVideoFile(file)), block: refusal }
  }
  return { allowed: files, block: null }
}
