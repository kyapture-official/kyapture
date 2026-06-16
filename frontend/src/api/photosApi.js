import api from './axiosInstance'

/**
 * WHAT: Photo Management API Service Client
 * WHY:  Abstracts all multipart file-upload forms, deletion vectors, and sorting
 *       arrangements. Decouples components from raw asset URLs and Axios
 *       multipart configurations.
 *
 * UNIFIED API DATA SHAPES:
 *   uploadBulk()    → Photo[]
 *   deletePhotos()  → void (HTTP 204 No Content)
 *   reorderPhotos() → { success: boolean, ordered_ids: string[] }
 *
 * PHOTO INTERFACE:
 *   {
 *     id:            string (UUID),
 *     image_url:     string,   ← Absolute S3/CDN URL
 *     original_name: string,
 *     file_size:     number,   ← In bytes
 *     width:         number,   ← In pixels
 *     height:        number,   ← In pixels
 *     order:         number,   ← Sorting position index (0-indexed)
 *     uploaded_at:   string (ISO 8601)
 *   }
 */

// ─────────────────────────────────────────────────────────────────────────────
// PRIVATE LIFE-CYCLE VALIDATION HELPERS
// Evaluated once at module load; prevents duplicate validation loops.
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Throws a TypeError if value is not a non-empty, non-whitespace-only string.
 * Defends URL pathing from receiving null/undefined/number which would
 * silently evaluate as "null", "undefined", or "42" inside the path segment.
 */
const assertNonEmptyString = (value, label) => {
  if (typeof value !== 'string' || value.trim().length === 0) {
    throw new TypeError(
      `${label}: expected a non-empty string, received ${Object.prototype.toString.call(value)}`
    )
  }
}

/**
 * Throws a TypeError if the array is empty or contains non-string types.
 * Fails fast on the first offending index so developers get precise, localized warnings.
 */
const assertStringIdArray = (ids, label) => {
  if (!Array.isArray(ids) || ids.length === 0) {
    throw new TypeError(`${label}: must be a non-empty array`)
  }
  for (let i = 0; i < ids.length; i++) {
    if (typeof ids[i] !== 'string' || ids[i].trim().length === 0) {
      throw new TypeError(
        `${label}[${i}]: expected a non-empty string UUID, received ${Object.prototype.toString.call(ids[i])}`
      )
    }
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// API CLIENT
// ─────────────────────────────────────────────────────────────────────────────

export const photosApi = {
  /**
   * WHAT: Upload Multiple Images (Bulk)
   * URI:  POST /api/v1/photos/{gallery_slug}/upload/
   *
   * @param {string}      gallerySlug   - Target gallery identifier
   * @param {FormData}    formData      - Binary file payload; must be a FormData instance
   * @param {Function}   [onProgress]   - Upload progress callback, receives integer 0-100
   * @param {AbortSignal}[signal]       - Optional AbortController signal for cancellation
   *
   * @returns {Promise<Photo[]>}
   * @throws  {TypeError} If gallerySlug is not a non-empty string
   * @throws  {TypeError} If formData is not a FormData instance
   */
  uploadBulk: async (gallerySlug, formData, onProgress, signal) => {
    assertNonEmptyString(gallerySlug, 'photosApi.uploadBulk: gallerySlug')

    if (!(formData instanceof FormData)) {
      throw new TypeError(
        `photosApi.uploadBulk: expected a FormData instance, received ${Object.prototype.toString.call(formData)}`
      )
    }

    const { data } = await api.post(
      `/photos/${encodeURIComponent(gallerySlug)}/upload/`,
      formData,
      {
        signal,
        onUploadProgress: (progressEvent) => {
          if (typeof onProgress === 'function' && progressEvent.total) {
            const percentCompleted = Math.round(
              (progressEvent.loaded * 100) / progressEvent.total
            )
            onProgress(percentCompleted)
          }
        },
      }
    )

    return data
  },

  /**
   * WHAT: Delete Multiple Images (Bulk)
   * URI:  POST /api/v1/photos/{gallery_slug}/delete-bulk/
   *
   * @param   {string}      gallerySlug
   * @param   {string[]}    photoIds    - Non-empty array of Photo UUIDs to purge
   * @param   {AbortSignal} [signal]    - Optional cancellation signal
   *
   * @returns {Promise<void>}           Expects HTTP 204 No Content
   * @throws  {TypeError} If gallerySlug is not a non-empty string
   * @throws  {TypeError} If photoIds is not a non-empty array of non-empty strings
   */
  deletePhotos: async (gallerySlug, photoIds, signal) => {
    assertNonEmptyString(gallerySlug, 'photosApi.deletePhotos: gallerySlug')
    assertStringIdArray(photoIds, 'photosApi.deletePhotos: photoIds')

    // Deduplication: safe for deletes as order has no impact.
    // Prevents database constraint errors caused by deleting the same row twice in one transaction.
    const uniqueIds = [...new Set(photoIds)]

    await api.post(
      `/photos/${encodeURIComponent(gallerySlug)}/delete-bulk/`,
      { photo_ids: uniqueIds },
      { signal }
    )
  },

  /**
   * WHAT: Reorder Images (Bulk Sort)
   * URI:  PATCH /api/v1/photos/{gallery_slug}/reorder/
   *
   * @param   {string}      gallerySlug
   * @param   {string[]}    orderedPhotoIds - Non-empty ordered array of Photo UUIDs
   * @param   {AbortSignal} [signal]        - Optional cancellation signal
   *
   * @returns {Promise<{ success: boolean, ordered_ids: string[] }>}
   * @throws  {TypeError} If gallerySlug is not a non-empty string
   * @throws  {TypeError} If orderedPhotoIds is not a non-empty array of non-empty strings
   */
  reorderPhotos: async (gallerySlug, orderedPhotoIds, signal) => {
    assertNonEmptyString(gallerySlug, 'photosApi.reorderPhotos: gallerySlug')
    assertStringIdArray(orderedPhotoIds, 'photosApi.reorderPhotos: orderedPhotoIds')

    // No deduplication here: duplicate elements inside a sorting array is a true logic error.
    // We let the backend reject the invalid payload to force the upstream bug to be fixed.

    const { data } = await api.patch(
      `/photos/${encodeURIComponent(gallerySlug)}/reorder/`,
      { ordered_ids: orderedPhotoIds },
      { signal }
    )

    return data
  },
}