// frontend/src/utils/blurhashDataUrl.js
import { decode } from 'blurhash'

// Module-level cache: the same photo re-renders constantly during masonry
// reflows/scrolling, and re-decoding the identical hash every time would be
// pure waste. Decode once per (hash, size), reuse forever.
const cache = new Map()

/**
 * Decodes a BlurHash string (computed server-side in
 * apps/core/utils.py::process_image_pipeline) into a tiny PNG data URL,
 * usable directly as a CSS background-image while the real thumbnail is
 * still loading over the network.
 *
 * Decodes at a small fixed resolution (32x32 by default) — blurhash is a
 * deliberately low-frequency approximation, so decoding larger only costs
 * more CPU for a visually identical blur.
 *
 * Returns null for a missing/invalid hash so callers can just render
 * nothing instead of a broken placeholder.
 */
export function getBlurhashDataUrl(hash, width = 32, height = 32) {
    if (!hash || typeof document === 'undefined') return null

    const cacheKey = `${hash}:${width}x${height}`
    if (cache.has(cacheKey)) return cache.get(cacheKey)

    let dataUrl = null
    try {
        const pixels = decode(hash, width, height)
        const canvas = document.createElement('canvas')
        canvas.width = width
        canvas.height = height
        const ctx = canvas.getContext('2d')
        const imageData = ctx.createImageData(width, height)
        imageData.data.set(pixels)
        ctx.putImageData(imageData, 0, 0)
        dataUrl = canvas.toDataURL('image/png')
    } catch {
        // Malformed hash — skip the placeholder rather than throw.
        dataUrl = null
    }

    cache.set(cacheKey, dataUrl)
    return dataUrl
}