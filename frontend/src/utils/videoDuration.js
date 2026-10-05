// File Location: frontend/src/utils/videoDuration.js
// Reads a local video file's length in the browser, BEFORE it is uploaded.
// The nginx CSP carries `blob:` in media-src for exactly this (see nginx.conf).

const DEFAULT_TIMEOUT_MS = 5000

/**
 * Resolves with the video's duration in seconds, or null when the browser
 * cannot tell (unsupported codec, unreadable file, no metadata within the
 * timeout). Never rejects. The object URL is always revoked and the hidden
 * element released, whatever the outcome.
 */
export function readVideoDuration(file, timeoutMs = DEFAULT_TIMEOUT_MS) {
  return new Promise((resolve) => {
    let url = null
    let video = null
    let timer = null
    let settled = false

    const finish = (value) => {
      if (settled) return
      settled = true
      clearTimeout(timer)
      if (video) {
        video.removeAttribute('src')
        video.load()
      }
      if (url) URL.revokeObjectURL(url)
      resolve(value)
    }

    try {
      url = URL.createObjectURL(file)
      video = document.createElement('video')
      video.preload = 'metadata'
      video.muted = true
      video.onloadedmetadata = () => {
        const seconds = video.duration
        finish(Number.isFinite(seconds) && seconds > 0 ? seconds : null)
      }
      video.onerror = () => finish(null)
      timer = setTimeout(() => finish(null), timeoutMs)
      video.src = url
    } catch {
      finish(null)
    }
  })
}
