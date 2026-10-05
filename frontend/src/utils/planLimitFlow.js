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
