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
   * WHAT: Delete one or more photos in a single request.
   * URI:  POST /api/v1/photos/{gallery_slug}/delete-bulk/
   *
   * CORRECTION (M-3): this doc previously claimed "the backend has no
   * /delete-bulk/ route" and fanned out N individual DELETE calls via
   * Promise.allSettled instead. That was never true — PhotoBulkDeleteView
   * (apps/photos/views.py) has always existed, registered at
   * '<slug:gallery_slug>/delete-bulk/' in apps/photos/urls.py.
   *
   * WHY gallerySlug is now required:
   *   The bulk endpoint is scoped by gallery in the URL path (unlike the
   *   old per-photo DELETE, which only needed the photo UUID). Every
   *   current call site already has the slug in scope.
   *
   * RESPONSE SHAPE LIMITATION:
   *   The backend returns only { deleted_count } — not which specific IDs
   *   succeeded. Non-matching IDs (wrong gallery/owner, already deleted)
   *   are silently excluded server-side, not reported individually. This
   *   is exact for every current caller (always a single ID: deleted_count
   *   1 = success, 0 = failure). If a future multi-select bulk-delete UI
   *   ever sends more than one ID and the count comes back short, we
   *   deliberately do NOT guess which ones succeeded — see the partial
   *   branch below.
   *
   * @param   {string}      gallerySlug
   * @param   {string[]}    photoIds  - Non-empty array of photo UUIDs
   * @param   {AbortSignal} [signal]
   * @returns {Promise<{ deleted: string[], failed: string[], partialDeletedCount?: number }>}
   */
  deletePhotos: async (gallerySlug, photoIds, signal) => {
    assertNonEmptyString(gallerySlug, 'photosApi.deletePhotos: gallerySlug')
    assertStringIdArray(photoIds, 'photosApi.deletePhotos: photoIds')

    // Deduplicate so we never send the same ID twice in one batch
    const uniqueIds = [...new Set(photoIds)]

    const { data } = await api.post(
      `/photos/${encodeURIComponent(gallerySlug)}/delete-bulk/`,
      { photo_ids: uniqueIds },
      { signal }
    )

    const deletedCount = data?.deleted_count ?? 0

    if (deletedCount === uniqueIds.length) {
      return { deleted: uniqueIds, failed: [] }
    }
    if (deletedCount === 0) {
      return { deleted: [], failed: uniqueIds }
    }
    // Partial batch failure with no per-id attribution available from the
    // backend. Reported honestly as "some failed," not faked as specific IDs.
    return { deleted: [], failed: uniqueIds, partialDeletedCount: deletedCount }
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