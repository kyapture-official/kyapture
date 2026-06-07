import api from './axiosInstance'

/**
 * WHAT: Network Service Client for Authentication Endpoints
 * WHY:  Centralizes all HTTP operations related to photographer credentials and sessions.
 *       Prevents components and stores from importing Axios directly [18].
 *
 * UNIFIED RETURN SHAPES:
 *   login()          → { access: string, refresh: string, user: UserProfile }
 *   register()       → { access: string, refresh: string, user: UserProfile }
 *   logout()         → void (HTTP 200/204 No Content)
 *   me()             → UserProfile
 *   forgotPassword() → { detail: string }
 *
 * USER PROFILE INTERFACE (UserProfile):
 *   {
 *     id:             string (UUID),
 *     username:       string,   ← Subdomain identifier (e.g., username.domain.com)
 *     email:          string,
 *     display_name:   string,   ← Business/Photographer display name
 *     logo:           string | null,
 *     is_active_plan: boolean   ← Premium billing plan status (gated feature lock)
 *   }
 */
export const authApi = {

  /**
   * WHAT: Authenticates a photographer and returns active JWT credentials.
   * URI:  POST /api/v1/auth/login/
   *
   * @param {{ email: string, password: string }} credentials
   * @returns {Promise<{ access: string, refresh: string, user: UserProfile }>}
   */
  login: (credentials) =>
    api.post('/auth/login/', credentials).then((res) => res.data),

  /**
   * WHAT: Creates a new photographer account and returns tokens immediately.
   * URI:  POST /api/v1/auth/register/
   *
   * NOTE: We return session tokens immediately after registration for optimized UX,
   *       allowing photographers to skip manual secondary login pages.
   *
   * @param {{
   *   username:     string,
   *   email:        string,
   *   password:     string,
   *   display_name: string
   * }} payload
   * @returns {Promise<{ access: string, refresh: string, user: UserProfile }>}
   */
  register: (payload) =>
    api.post('/auth/register/', payload).then((res) => res.data),

  /**
   * WHAT: Blacklists the provided refresh token on the backend to terminate the session.
   * URI:  POST /api/v1/auth/logout/
   *
   * NOTE: We keep authApi pure. We pass the token as a parameter rather than loading the store,
   *       preserving strict separation of concerns between our network and state layers.
   *
   * @param   {string}        refreshToken - JWT refresh string targeting database invalidation
   * @returns {Promise<void>}
   */
  logout: (refreshToken) =>
    api.post('/auth/logout/', { refresh: refreshToken }).then((res) => res.data),

  /**
   * WHAT: Retrieves the currently authenticated photographer's profile settings.
   * URI:  GET /api/v1/auth/me/
   *
   * @returns {Promise<UserProfile>}
   */
  me: () =>
    api.get('/auth/me/').then((res) => res.data),

  /**
   * WHAT: Dispatches a password recovery request instructions email.
   * URI:  POST /api/v1/auth/password/reset/
   *
   * @param   {{ email: string }} payload
   * @returns {Promise<{ detail: string }>}
   */
  forgotPassword: (payload) =>
    api.post('/auth/password/reset/', payload).then((res) => res.data),
}