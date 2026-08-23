// File Location: frontend/src/api/photosApi.js

import api from './axiosInstance'

/**
 * WHAT: Photo Management API Service Client
 * WHY:  Abstracts all multipart file-upload, single/bulk deletion, and
 *       listing operations against the backend MediaAsset endpoints.
 *
 *     NOTE: /delete-bulk/ exists on the backend but is intentionally unused
 *   here (see deletePhotos below, which fans out individual DELETEs).
 *   PATCH /photos/{gallery_slug}/reorder/ backs the drag-and-drop reorder
 *   feature in PhotoGrid.jsx — see reorderPhotos() below.
 * BACKEND ENDPOINT CONTRACT:
 *   GET    /api/v1/photos/{gallery_slug}/               → list assets
 *   POST   /api/v1/photos/{gallery_slug}/upload/        → bulk upload
 *   DELETE /api/v1/photos/photo/{photo_id}/             → single asset delete
 *
 *   
 *
 * MEDIA ASSET INTERFACE (from MediaAssetSerializer):
 *   {
 *     id:                string  (UUID),
 *     media_type:        'image' | 'video',
 *     title:             string,
 *     original_name:     string,
 *     file_size:         number,   ← bytes
 *     order:             number,   ← display sort index (0-indexed)
 *     original_url:      string,   ← full-resolution file
 *     display_url:       string,   ← 2048px WebP display variant
 *     thumbnail_url:     string,   ← 600px WebP thumbnail for grid
 *     blurhash:          string,   ← Base85 blur placeholder hash
 *     width:             number,
 *     height:            number,
 *     processing_status: string,
 *     created_at:        string,   ← ISO 8601
 *   }
 */

// ─────────────────────────────────────────────────────────────────────────────
// PRIVATE VALIDATION HELPERS
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Asserts that a value is a non-empty string.
 * Tags the error with status: null and code: 'INVALID_ARGUMENT' to match clientsApi shape contracts.
 */
const assertNonEmptyString = (value, label) => {
  if (typeof value !== 'string' || value.trim().length === 0) {
    const err = new TypeError(
      `${label}: expected a non-empty string, received ${Object.prototype.toString.call(value)}`
    )
    err.code = 'INVALID_ARGUMENT'
    err.status = null
    throw err
  }
}

/**
 * Asserts that a value is a non-empty array of valid string UUIDs.
 * Tags the error with status: null and code: 'INVALID_ARGUMENT'.
 */
const assertStringIdArray = (ids, label) => {
  if (!Array.isArray(ids) || ids.length === 0) {
    const err = new TypeError(`${label}: must be a non-empty array`)
    err.code = 'INVALID_ARGUMENT'
    err.status = null
    throw err
  }
  for (let i = 0; i < ids.length; i++) {
    if (typeof ids[i] !== 'string' || ids[i].trim().length === 0) {
      const err = new TypeError(
        `${label}[${i}]: expected a non-empty string UUID, received ${Object.prototype.toString.call(ids[i])}`
      )
      err.code = 'INVALID_ARGUMENT'
      err.status = null
      throw err
    }
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// API CLIENT
// ─────────────────────────────────────────────────────────────────────────────

export const photosApi = {

  /**
   * WHAT: List all media assets inside a gallery.
   * URI:  GET /api/v1/photos/{gallery_slug}/
   *
   * @param   {string} gallerySlug
   * @returns {Promise<MediaAsset[]>}
   */
  list: async (gallerySlug) => {
    assertNonEmptyString(gallerySlug, 'photosApi.list: gallerySlug')
    const { data } = await api.get(`/photos/${encodeURIComponent(gallerySlug)}/`)
    return data
  },

  /**
   * WHAT: Upload multiple images in one multipart POST.
   * URI:  POST /api/v1/photos/{gallery_slug}/upload/
   *
   * WHY no Content-Type header: when Axios receives a FormData body it
   * automatically sets Content-Type: multipart/form-data; boundary=...
   * Hardcoding the header strips the boundary string, causing Django to
   * reject the stream with 415 Unsupported Media Type.
   *
   * @param {string}      gallerySlug
   * @param {FormData}    formData      - must contain one or more 'image' keys
   * @param {Function}   [onProgress]   - receives integer 0–100
   * @param {AbortSignal}[signal]
   * @returns {Promise<MediaAsset[]>}
   */
  uploadBulk: async (gallerySlug, formData, onProgress, signal) => {
    assertNonEmptyString(gallerySlug, 'photosApi.uploadBulk: gallerySlug')

    if (!(formData instanceof FormData)) {
      const err = new TypeError(
        `photosApi.uploadBulk: expected FormData, received ${Object.prototype.toString.call(formData)}`
      )
      err.code = 'INVALID_ARGUMENT'
      err.status = null
      throw err
    }

    const { data } = await api.post(
      `/photos/${encodeURIComponent(gallerySlug)}/upload/`,
      formData,
      {
        signal,
        onUploadProgress: (evt) => {
          if (typeof onProgress === 'function' && evt.total) {
            onProgress(Math.round((evt.loaded * 100) / evt.total))
          }
        },
      }
    )

    return data
  },

  /**
   * WHAT: Delete multiple photos.
   * URI:  DELETE /api/v1/photos/photo/{photo_id}/  (called once per ID)
   *
   * WHY individual calls, not a bulk endpoint:
   *   The backend has no /delete-bulk/ route — only single-photo deletion
   *   at /photos/photo/{photo_id}/.  We fan out with Promise.allSettled
   *   so a single failure doesn't block the rest of the batch.
   *
   * @param   {string[]}    photoIds  - Non-empty array of photo UUIDs
   * @param   {AbortSignal} [signal]
   * @returns {Promise<{ deleted: string[], failed: string[] }>}
   *          Callers can show partial-failure feedback from these arrays.
   */
  deletePhotos: async (photoIds, signal) => {
    assertStringIdArray(photoIds, 'photosApi.deletePhotos: photoIds')

    // Deduplicate so we never send the same DELETE twice in one batch
    const uniqueIds = [...new Set(photoIds)]

    const results = await Promise.allSettled(
      uniqueIds.map((id) =>
        api.delete(`/photos/photo/${encodeURIComponent(id)}/`, { signal })
      )
    )

    const deleted = []
    const failed  = []
    results.forEach((result, i) => {
      if (result.status === 'fulfilled') {
        deleted.push(uniqueIds[i])
      } else {
        failed.push(uniqueIds[i])
      }
    })

    return { deleted, failed }
  },

    /**
   * WHAT: Fetch current status/metadata for a single asset.
   * URI:  GET /api/v1/photos/photo/{photo_id}/
   *
   * Used for polling assets still in 'pending'/'processing' state after
   * upload (e.g. videos awaiting FFmpeg poster-frame generation) so the
   * UI can pick up the finished thumbnail without a manual page refresh.
   */
  getById: async (photoId, signal) => {
    assertNonEmptyString(photoId, 'photosApi.getById: photoId')
    const { data } = await api.get(`/photos/photo/${encodeURIComponent(photoId)}/`, { signal })
    return data
  },

  /**
   * WHAT: Persist a new manually-dragged sort order for a gallery's photos.
   * URI:  PATCH /api/v1/photos/{gallery_slug}/reorder/
   *
   * WHY the caller must send the FULL ordered ID list, not just the moved
   * item: the backend (PhotoReorderView) assigns fresh sequential Decimal
   * `order` values only to the IDs present in the payload, in the order
   * given. Any photo left out keeps its old order value untouched, which
   * can leave it sorting inconsistently against the freshly-renumbered
   * ones. Always pass every photo currently in the gallery.
   *
   * @param   {string}   gallerySlug
   * @param   {string[]} orderedPhotoIds - Every photo ID in the gallery,
   *                                       in the desired display sequence.
   * @returns {Promise<{ success: boolean, ordered_ids: string[] }>}
   */
  reorderPhotos: async (gallerySlug, orderedPhotoIds, signal) => { 
    assertNonEmptyString(gallerySlug, 'photosApi.reorderPhotos: gallerySlug')
    assertStringIdArray(orderedPhotoIds, 'photosApi.reorderPhotos: orderedPhotoIds')

    const { data } = await api.patch(
      `/photos/${encodeURIComponent(gallerySlug)}/reorder/`,
      { ordered_ids: orderedPhotoIds },
      { signal } 
    )
    return data
  },

  // ── BACKWARD-COMPATIBLE ALIAS ─────────────────────────────────────────────
  // Preserves existing UploadPage.jsx implementations during method migrations
  upload: function (gallerySlug, formData, onProgress, signal) {
    return photosApi.uploadBulk(gallerySlug, formData, onProgress, signal)
  },
}