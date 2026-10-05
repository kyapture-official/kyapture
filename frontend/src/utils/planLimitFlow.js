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
    ? { code: data.code, used_minutes: data.used_minutes, plan_limit_minutes: data.plan_limit_minutes }
    : null

/**
 * Splits a selection into what may upload and what the plan already refuses,
 * BEFORE any upload. `usage` is the fresh usage-endpoint answer (null =
 * unknown: let the server decide). Two cases are certain from the usage alone:
 * the plan has no video (limit 0), or its video minutes are all used. A video
 * that merely might be too long is the server's call: its length is only known
 * there (ffprobe), and its video_minutes_exceeded 403 is the fallback.
 *
 * Returns { allowed: File[], block: null | { code, used_minutes, plan_limit_minutes, plan_name } }.
 */
export function planVideoFiles(files, usage) {
  if (!usage || usage.video_minutes_limit == null || !files.some(isVideoFile)) {
    return { allowed: files, block: null }
  }
  const limit = usage.video_minutes_limit
  const figures = { used_minutes: usage.video_minutes_used, plan_limit_minutes: limit, plan_name: usage.plan_name }
  if (limit === 0) {
    return { allowed: files.filter((file) => !isVideoFile(file)), block: { code: VIDEO_NOT_IN_PLAN, ...figures } }
  }
  if (usage.video_minutes_used >= limit) {
    return { allowed: files.filter((file) => !isVideoFile(file)), block: { code: VIDEO_MINUTES_EXCEEDED, ...figures } }
  }
  return { allowed: files, block: null }
}
