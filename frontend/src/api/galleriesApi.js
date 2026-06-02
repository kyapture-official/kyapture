import api from './axiosInstance';

/**
 * WHAT: Aligned and Optimized Gallery API client
 * WHY: Corrects slug-based lookups, handles query parameters, and maps MVP features.
 * HOW: Leverages our shared Axios instance, mapping explicit parameters to DRF viewset endpoints.
 * WHERE: frontend/src/api/galleriesApi.js
 */
export const galleriesApi = {
  /**
   * Fetches all active photographer galleries.
   * Supports search queries, sort orders, and pagination offsets.
   * Usage: galleriesApi.list({ search: 'wedding', page: 2 })
   */
  list: (params) => api.get('/galleries/', { params }),

  /**
   * Registers a new gallery inside the photographer's store.
   * Expected payload data: { title: string, branding_color: string }
   */
  create: (data) => api.post('/galleries/', data),

  /**
   * Fetches full metadata for a single gallery.
   * Strictly uses unique 'slug' as the lookup parameter as configured in Django.
   */
  get: (slug) => api.get(`/galleries/${slug}/`),

  /**
   * Performs a partial patch mutation on a specific gallery.
   */
  update: (slug, data) => api.patch(`/galleries/${slug}/`, data),

  /**
   * Initiates a soft-delete instruction to the backend.
   */
  delete: (slug) => api.delete(`/galleries/${slug}/`),

  /**
   * Publishes the gallery, making it visible to the public under the tenant subdomain.
   */
  publish: (slug) => api.post(`/galleries/${slug}/publish/`),

  /**
   * Unpublishes the gallery, restricting access back to the photographer admin dashboard.
   */
  unpublish: (slug) => api.post(`/galleries/${slug}/unpublish/`),

  /**
   * Assigns or updates the protection password for a gallery.
   * Automatically serializes the raw password input to the expected backend payload.
   */
  setPassword: (slug, password) => api.post(`/galleries/${slug}/set-password/`, { password }),
};