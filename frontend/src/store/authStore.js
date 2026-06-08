// frontend/src/store/authStore.js
// ─────────────────────────────────────────────────────────────────────────────
// WHAT: Global authentication state for the entire application.
// WHY Zustand with persist middleware:
//   Tokens must survive page reloads (localStorage) but also be readable
//   synchronously from anywhere (Zustand state). The persist middleware
//   handles both: Zustand is the single source of truth, localStorage is
//   the automatic persistence layer. No manual localStorage calls needed.
//
// WHY persist only tokens, not user or loading:
//   `user` is always fetched fresh via init() — stale cached user data
//   could reflect old plan status, old display name, old permissions.
//   `loading` is a UI state, not a session state — it resets on every boot.
//   `isAuthenticated` is derived: if accessToken exists after init() validates
//   it, the user is authenticated. Storing it separately creates a second
//   source of truth that can diverge.
// ─────────────────────────────────────────────────────────────────────────────

import { create }                     from 'zustand';
import { persist, createJSONStorage } from 'zustand/middleware';
import { authApi }                    from '../api/authApi';

export const useAuthStore = create(
  persist(
    (set, get) => ({

      // ── Initial State ───────────────────────────────────────────────────────
      // WHY accessToken and refreshToken in state:
      //   axiosInstance.js reads useAuthStore.getState().accessToken to attach
      //   the Authorization header. If tokens only lived in localStorage, the
      //   interceptor would have no way to read them through Zustand.
      //   One store, one source of truth.
      user:            null,
      accessToken:     null,
      refreshToken:    null,
      isAuthenticated: false,

      // WHY loading starts true:
      //   The app must not render protected routes until init() confirms the
      //   stored token is still valid. loading=true signals App.jsx to show
      //   a spinner. It becomes false only after init() completes.
      loading:         true,


      // ── Actions ─────────────────────────────────────────────────────────────

      /**
       * WHAT: Boot-time session validator.
       * WHY:  On every page load, if a token exists in persisted state, call /me/
       *       to confirm it is still accepted by the backend.
       *       This catches tokens that expired while the tab was closed — the
       *       Axios refresh interceptor only runs during active use.
       *
       *       If /me/ succeeds: user is authenticated, render the app.
       *       If /me/ fails:    handle based on failure type (see catch block).
       *
       * CALL SITE: App.jsx — once on mount, inside useEffect with [] dependency.
       */
      init: async () => {
        const { accessToken } = get();

        // No persisted token — user has never logged in or previously logged out.
        // Set loading false so the app renders the login page immediately.
        if (!accessToken) {
          return set({ loading: false, isAuthenticated: false });
        }

        try {
          // authApi.me() returns the user object directly — { id, username, ... }
          // There is no .data wrapper — authApi functions extract it internally.
          const user = await authApi.me();
          set({ user, isAuthenticated: true, loading: false });

        } catch (err) {
          // ── WHY distinguish auth rejections from network failures ───────────
          // A 401/403 means the backend actively rejected the token — it is
          // invalid, expired, or revoked. Safe to clear.
          //
          // A network failure (err.response is undefined), a server 500, or a
          // CORS error does NOT prove the token is invalid — only that we
          // could not reach the backend right now. Clearing tokens here would
          // permanently log the user out due to a temporary connectivity issue.
          //
          // NOTE: if the Axios refresh interceptor already called logout()
          // before this catch runs, accessToken and refreshToken are already
          // null. The isAuthRejection branch just sets them to null again
          // (harmless). The else branch is what protects against network errors.
          const isAuthRejection =
            err?.response?.status === 401 || err?.response?.status === 403;

          if (isAuthRejection) {
            set({
              user:            null,
              accessToken:     null,
              refreshToken:    null,
              isAuthenticated: false,
              loading:         false,
            });
          } else {
            // Network failure or server error — preserve tokens.
            // User can retry by refreshing the page when connectivity returns.
            set({ isAuthenticated: false, loading: false });
          }
        }
      },


      /**
       * WHAT: Login action.
       * WHY:  Authenticates credentials and stores the returned tokens in Zustand
       *       state. The persist middleware automatically syncs to localStorage.
       *
       * NOTE: authApi.login() returns { access, refresh, user } directly.
       *       Do not destructure as `{ data }` — there is no data wrapper.
       */
      login: async (email, password) => {
        const response = await authApi.login({ email, password });
        set({
          user:            response.user,
          accessToken:     response.access,
          refreshToken:    response.refresh,
          isAuthenticated: true,
          loading:         false,
        });
        return response;
      },


      /**
       * WHAT: Registration action.
       * WHY:  Registers the photographer and logs them in immediately.
       *       The backend returns tokens on successful registration — the user
       *       does not need to authenticate again after signing up.
       *
       * NOTE: Same return shape as login: { access, refresh, user }.
       */
      register: async (payload) => {
        const response = await authApi.register(payload);
        set({
          user:            response.user,
          accessToken:     response.access,
          refreshToken:    response.refresh,
          isAuthenticated: true,
          loading:         false,
        });
        return response;
      },


      /**
       * WHAT: Logout action.
       * WHY:  Blacklists the refresh token on the backend, then clears all local
       *       state. The persist middleware automatically clears localStorage.
       *
       *       Called from two places:
       *       1. User clicks "Log out" — intentional logout.
       *       2. axiosInstance.handleSessionExpiry() — forced logout when both
       *          tokens are expired or invalid.
       *
       * WHY try/catch around the blacklist call:
       *       If the network is down or the backend is unreachable, we still clear
       *       local state. The refresh token will expire naturally on the backend
       *       within its configured TTL (7 days). Blocking local logout on a
       *       network failure is a worse user experience than leaving a
       *       soon-to-expire refresh token alive.
       *
       * WHY authApi.logout(refreshToken) receives the string directly:
       *       authApi.logout() already wraps it in { refresh: token } internally.
       *       Passing { refresh: token } from here would double-wrap it, sending
       *       { refresh: { refresh: "eyJ..." } } to the backend.
       */
      logout: async () => {
        const { refreshToken } = get();

        if (refreshToken) {
          try {
            await authApi.logout(refreshToken);
          } catch (err) {
            console.warn(
              '[authStore] Token blacklisting failed — local logout will proceed:',
              err.message
            );
          }
        }

        // Clearing state triggers persist middleware to remove tokens from localStorage.
        set({
          user:            null,
          accessToken:     null,
          refreshToken:    null,
          isAuthenticated: false,
          loading:         false,
        });
      },


      /**
       * WHAT: Password reset request.
       * WHY:  Dispatches the reset email via the API.
       *       No state changes — the backend handles delivery.
       *       The backend always returns 200 regardless of whether the email exists
       *       to prevent user enumeration attacks.
       */
      forgotPassword: async (email) => {
        await authApi.forgotPassword({ email });
      },


      /**
       * WHAT: Optimistic user profile updater.
       * WHY:  After the photographer saves settings (display name, logo), call this
       *       with the updated fields to reflect the change immediately in the UI
       *       without waiting for a full /me/ refetch.
       *
       *       Only call this AFTER the API call succeeds — never before.
       *       If the API call fails, local state will be stale until next reload.
       */
      updateUser: (updatedFields) => {
        const { user } = get();
        // WHY guard: If called before init() completes, user is null.
        // Merging into null would throw — return early instead.
        if (!user) return;
        set({ user: { ...user, ...updatedFields } });
      },

    }),

    {
      // WHY 'kyapture-auth' as the key:
      // Specific to this app — prevents collisions if other apps run on
      // the same localhost during development.
      name:    'kyapture-auth',
      storage: createJSONStorage(() => localStorage),

      // WHY partialize:
      // Only tokens are persisted. user, isAuthenticated, and loading are
      // always computed fresh on boot via init(). Persisting stale user data
      // would cause the UI to briefly show outdated plan status or display names.
      partialize: (state) => ({
        accessToken:  state.accessToken,
        refreshToken: state.refreshToken,
      }),
    }
  )
);