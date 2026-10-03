//C:\Users\LENOVO\Desktop\kyapture\frontend\src\api\authApi.js
import api from './axiosInstance'

/**
 * WHAT: Network Service Client for Authentication and Photographer Profile Endpoints.
 * WHY:  Centralizes all HTTP operations. Prevents components from importing Axios directly.
 *
 * UNIFIED RETURN SHAPES:
 *   login()          → { user: UserProfile }
 *   register()       → { user: UserProfile }
 *   logout()         → { message: string }
 *   me()             → UserProfile
 *   updateMe()       → UserProfile
 *   changePassword() → { message: string }
 *   forgotPassword() → { detail: string }
 *
 * USER PROFILE INTERFACE (UserProfile):
 *   {
 *     id:             string (UUID),
 *     username:       string,   ← Subdomain identifier (e.g., username.domain.com)
 *     email:          string,
 *     display_name:   string,   ← Business/Photographer display name
 *     bio:            string,
 *     avatar:         string | null,
 *     phone:          string,   ← Optional contact phone metadata
 *     website:        string | null,
 *     is_active_plan: boolean   ← Premium billing plan status (gated feature lock)
 *   }
 */
export const authApi = {

  /**
   * WHAT: Authenticates a photographer. 
   *       Backend sets secure HttpOnly cookies, returns only user profile.
   * URI:  POST /api/v1/auth/login/
   *
   * @param {{ email: string, password: string }} credentials
   * @returns {Promise<{ user: UserProfile }>}
   */
  login: (credentials) =>
    api.post('/auth/login/', credentials).then((res) => res.data),

  /**
   * WHAT: Creates a new photographer account.
   *       Backend sets secure HttpOnly cookies, returns only user profile.
   * URI:  POST /api/v1/auth/register/
   *
   * @param {{
   *   username:     string,
   *   email:        string,
   *   password:     string,
   *   display_name: string,
   *   phone?:       string,
   *   website?:     string
   * }} payload
   * @returns {Promise<{ user: UserProfile }>}
   */
  register: (payload) =>
    api.post('/auth/register/', payload).then((res) => res.data),

  /**
   * WHAT: Instructs the backend to blacklist the refresh cookie and purge all session cookies.
   * URI:  POST /api/v1/auth/logout/
   *
   * @returns {Promise<{ message: string }>}
   */
  logout: () =>
    api.post('/auth/logout/', {}).then((res) => res.data),

  /**
   * WHAT: Retrieves the currently authenticated photographer's profile settings.
   * URI:  GET /api/v1/auth/me/
   *
   * @returns {Promise<UserProfile>}
   */
  me: () =>
    api.get('/auth/me/').then((res) => res.data),

  /**
   * WHAT: Partially updates photographer profile settings (bio, display name, avatar).
   * URI:  PUT /api/v1/auth/me/
   *
   * @param   {FormData | object} payload - Can be raw JSON or FormData (if uploading avatar)
   * @returns {Promise<UserProfile>}
   */
  updateMe: (payload) =>
    api.put('/auth/me/', payload).then((res) => res.data),

  /**
   * WHAT: Updates the authenticated user's password securely.
   * URI:  PUT /api/v1/auth/change-password/
   *
   * @param   {{ old_password: string, new_password: string, new_password2: string }} payload
   * @returns {Promise<{ message: string }>}
   */
  changePassword: (payload) =>
    api.put('/auth/change-password/', payload).then((res) => res.data),

  /**
   * WHAT: Signs the account out everywhere — the server blacklists every
   *       outstanding refresh token (this device included) and clears cookies.
   * URI:  POST /api/v1/auth/logout-all/
   */
  logoutAll: () =>
    api.post('/auth/logout-all/', {}).then((res) => res.data),

  /**
   * WHAT: Notification preferences, privacy, and Collection Defaults.
   * URI:  GET /api/v1/auth/settings/
   *
   * @returns {Promise<{ notifications: {downloads, favorites, payments},
   *                     privacy: {portfolio_public}, collection_defaults: object }>}
   */
  getSettings: () =>
    api.get('/auth/settings/').then((res) => res.data),

  /**
   * WHAT: Saves any subset of those sections; the response is the full saved
   *       state, so callers render what the server actually stored.
   * URI:  PATCH /api/v1/auth/settings/
   */
  updateSettings: (payload) =>
    api.patch('/auth/settings/', payload).then((res) => res.data),

  /**
   * WHAT: Dispatches a password recovery request instructions email.
   * URI:  POST /api/v1/auth/password/reset/
   *
   * @param   {{ email: string }} payload
   * @returns {Promise<{ detail: string }>}
   */
  forgotPassword: (payload) =>
    api.post('/auth/password/reset/', payload).then((res) => res.data),

  /**
   * WHAT: Confirms a password reset using the emailed uidb64/token pair and
   *       sets the new password. Called from the link in the reset email.
   * URI:  POST /api/v1/auth/password/reset/confirm/
   *
   * @param   {{ uidb64: string, token: string, new_password: string, new_password2: string }} payload
   * @returns {Promise<{ message: string }>}
   */
  resetPasswordConfirm: (payload) =>
    api.post('/auth/password/reset/confirm/', payload).then((res) => res.data),
}