// frontend/src/api/galleriesApi.js
// ─────────────────────────────────────────────────────────────
// WHAT: Gallery API Service Client
// WHY:  Single source of truth for all gallery HTTP operations.
//       Components and hooks never reference raw API endpoints.
//       If an endpoint changes, this is the only file to update.
//
// ⚠️  SPEC SYNC REQUIRED (resolve with backend developer before Week 4):
//     weekly_tasks.txt (Week 1 model) defines only `is_active`.
//     file_and_folder_structure.txt defines both `is_active` and `is_published`.
//     The field names for download and password also differ between documents.
//     Confirm the final model fields before the Week 4 integration sprint.
//
// AGREED RETURN SHAPES (confirm against backend once built):
//   getGalleries()  → { count: number, next: string|null,
//                       previous: string|null, results: Gallery[] }
//   getGallery()    → Gallery
//   createGallery() → Gallery
//   updateGallery() → Gallery
//   deleteGallery() → void  (HTTP 204 — no body)
//
// Gallery object shape (⚠️ pending backend sync on is_published):
//   {
//     id:               string  (UUID)
//     title:            string
//     slug:             string
//     branding_color:   string  (hex, e.g. "#1a1a1a")
//     is_downloadable:  boolean
//     is_active:        boolean  (soft-delete flag — False = deleted)
//     is_published:     boolean  (⚠️ exists only if backend implements it)
//     has_password:     boolean  (presence flag — hash never exposed)
//     cover_url:        string | null
//     photo_count:      number
//     created_at:       string  (ISO 8601)
//     updated_at:       string  (ISO 8601)
//   }
// ─────────────────────────────────────────────────────────────

import api from './axiosInstance'

export const galleriesApi = {

  /**
   * WHAT: Fetch the authenticated photographer's gallery list (paginated).
   * URI:  GET /api/v1/galleries/
   *
   * @param {Object}      params            - Optional DRF query parameters
   * @param {number}      params.page       - Page number  (default: 1)
   * @param {number}      params.page_size  - Results per page (default: 20)
   * @param {string}      params.search     - Keyword filter on gallery title
   * @param {string}      params.ordering   - Sort field; prefix '-' = descending
   *                                          Examples: 'created_at', '-created_at'
   * @param {AbortSignal} [signal]          - AbortController signal.
   *
   * WHY the signal parameter exists:
   *   When a user types into a search field, a new request fires on every
   *   keystroke. Without cancellation, three requests fire and the slowest
   *   one wins — the UI shows stale data. The calling hook creates one
   *   AbortController per keystroke, passes its signal here, and aborts
   *   the previous in-flight request before the next one starts.
   *
   * @returns {Promise<{ count: number, next: string|null,
   *                     previous: string|null, results: Gallery[] }>}
   */
  getGalleries: async (params = {}, signal = undefined) => {
    const { data } = await api.get('/galleries/', { params, signal })
    return data
  },

  /**
   * WHAT: Fetch the full configuration of one specific gallery.
   * URI:  GET /api/v1/galleries/{slug}/
   *
   * WHY slug and not numeric ID:
   *   Numeric IDs expose database size (/galleries/3 reveals you have 3 records).
   *   Slugs are human-readable, SEO-friendly, and reveal nothing about scale.
   *   The backend sets lookup_field = 'slug' on the ViewSet (Week 3 spec).
   *
   * @param   {string}         slug
   * @returns {Promise<Gallery>}
   */
  getGallery: async (slug) => {
    const { data } = await api.get(`/galleries/${slug}/`)
    return data
  },

  /**
   * WHAT: Create a new empty gallery.
   * URI:  POST /api/v1/galleries/
   *
   * WHY password is excluded from this call:
   *   Password protection is a deliberate, separate action applied after
   *   creation. Combining creation and password in one call violates the
   *   single-responsibility principle and makes the creation form more
   *   complex than it needs to be.
   *
   * @param   {{ title:            string,
   *             branding_color?:  string,
   *             is_downloadable?: boolean }} galleryData
   * @returns {Promise<Gallery>}
   */
  createGallery: async (galleryData) => {
    const { data } = await api.post('/galleries/', galleryData)
    return data
  },

  /**
   * WHAT: Partially update specific gallery settings fields.
   * URI:  PATCH /api/v1/galleries/{slug}/
   *
   * WHY PATCH and never PUT:
   *   PUT replaces the entire resource. Sending only { branding_color: '#ff0000' }
   *   with PUT would wipe every other field to null on the backend.
   *   PATCH updates only the explicitly sent fields. Always use PATCH
   *   for settings panels where individual fields change independently.
   *
   * WHY is_published is NOT in this parameter list:
   *   Publish state has a dedicated method (publishGallery) that calls a
   *   dedicated endpoint (/publish/). That endpoint may have backend
   *   side-effects beyond flipping a boolean (notifications, validation,
   *   cache invalidation). Routing publish through updateGallery bypasses
   *   those side-effects and creates two inconsistent paths to the same state.
   *   One action, one method, one endpoint.
   *
   * @param {string} slug
   * @param {{ title?:           string,
   *           branding_color?:  string,
   *           is_downloadable?: boolean,
   *           cover_photo?:     string }} updatedFields
   * @returns {Promise<Gallery>}
   */
  updateGallery: async (slug, updatedFields) => {
    const { data } = await api.patch(`/galleries/${slug}/`, updatedFields)
    return data
  },

  /**
   * WHAT: Soft-delete a gallery (backend sets is_active = false).
   * URI:  DELETE /api/v1/galleries/{slug}/
   *
   * WHY soft delete and not hard delete:
   *   Soft delete marks the record inactive. The data and all associated
   *   photos remain in the database, recoverable by an admin. Hard delete
   *   permanently destroys the database row and all photo files with no
   *   recovery path. We protect against accidental data loss.
   *
   * WHY this returns void:
   *   The backend returns HTTP 204 No Content. Axios sets response.data
   *   to empty string '' on 204. Returning '' to the caller is meaningless.
   *   The calling hook removes the gallery from its local state after
   *   this promise resolves — the API layer has no role in that.
   *
   * @param   {string}       slug
   * @returns {Promise<void>}
   */
  deleteGallery: async (slug) => {
    await api.delete(`/galleries/${slug}/`)
    // Intentionally returns nothing.
  },

  /**
   * WHAT: Enable or remove password protection on a gallery.
   * URI:  POST /api/v1/galleries/{slug}/set-password/
   *
   * @param {string}      slug
   * @param {string|null} password
   *   Non-empty string → enables protection (backend hashes with bcrypt)
   *   null             → explicitly removes password protection
   *
   * WHY null and not empty string "":
   *   An empty string is ambiguous — the user may have accidentally cleared
   *   the input. null is an explicit, intentional value meaning "no password."
   *   The ?? operator converts undefined to null, ensuring the backend
   *   always receives a clear signal, never an accidental undefined.
   *
   * @returns {Promise<{ has_password: boolean }>}
   */
  setGalleryPassword: async (slug, password) => {
    const { data } = await api.post(`/galleries/${slug}/set-password/`, {
      password: password ?? null,
    })
    return data
  },

  /**
   * WHAT: Toggle a gallery between published (visible to clients) and draft.
   * URI:  POST /api/v1/galleries/{slug}/publish/
   *
   * WHY this is separate from updateGallery:
   *   Publishing is a significant state change with potential backend
   *   side-effects. It has its own endpoint for that reason.
   *
   * ⚠️  FIELD NAME PENDING BACKEND SYNC:
   *   file_and_folder_structure.txt defines `is_published` as the visibility
   *   field, separate from `is_active` (soft-delete).
   *   weekly_tasks.txt Week 1 model does not define `is_published`.
   *   Confirm with the backend developer which field this endpoint accepts
   *   before the Week 4 integration sprint.
   *   Current implementation follows file_and_folder_structure.txt.
   *
   * @param   {string}  slug
   * @param   {boolean} isPublished  true = visible to clients, false = draft
   * @returns {Promise<Gallery>}
   *   Returns the updated Gallery object.
   *   (⚠️ confirm exact return shape with backend — may vary)
   */
  publishGallery: async (slug, isPublished) => {
    const { data } = await api.post(`/galleries/${slug}/publish/`, {
      is_published: isPublished,
    })
    return data
  },

}