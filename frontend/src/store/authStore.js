// frontend/src/store/authStore.js

import { create }                     from 'zustand';
import { persist, createJSONStorage } from 'zustand/middleware';
import { authApi }                    from '../api/authApi';

export const useAuthStore = create(
  persist(
    (set, get) => ({

      // ── Initial State ───────────────────────────────────────────────────────
      // We have completely removed accessToken and refreshToken from Javascript.
      // The browser automatically attaches them via secure HttpOnly cookies.
      user:            null,
      isAuthenticated: false,
      loading:         true,

      // ── Actions ─────────────────────────────────────────────────────────────

      /**
       * WHAT: Boot-time session rehydrator.
       * WHY:  On every page load, simply call /me/. If your browser has a valid, 
       *       active access cookie, the request succeeds and returns your profile.
       *       If the access cookie is expired, axiosInstance's interceptor will 
       *       silently refresh it in the background before this call completes.
       */
      init: async () => {
        try {
          // The browser automatically attaches your HttpOnly access_token cookie
          const user = await authApi.me();
          set({ user, isAuthenticated: true, loading: false });

        } catch (err) {
          // A 401/403 means the backend actively rejected the cookie — expired or revoked
          const isAuthRejection =
            err?.response?.status === 401 || err?.response?.status === 403;

          if (isAuthRejection) {
            set({
              user:            null,
              isAuthenticated: false,
              loading:         false,
            });
          } else {
            // Network failure or server error — preserve local cache.
            // Stop spinner so the offline app can render.
            set({ loading: false });
          }
        }
      },


      /**
       * WHAT: Login action.
       * WHY:  The backend sets HttpOnly cookies on the browser, and returns 
       *       only your safe user profile metadata in the JSON payload.
       */
      login: async (email, password) => {
        const response = await authApi.login({ email, password });
        set({
          user:            response.user,
          isAuthenticated: true,
          loading:         false,
        });
        return response;
      },


      /**
       * WHAT: Registration action.
       * WHY:  Registers the user and sets secure cookies, returning profile details.
       */
      register: async (payload) => {
        const response = await authApi.register(payload);
        set({
          user:            response.user,
          isAuthenticated: true,
          loading:         false,
        });
        return response;
      },


      /**
       * WHAT: Logout action.
       * WHY:  Tells the backend to blacklist the refresh cookie and clear browser cookies, 
       *       then clears local state. No payload parameters are sent.
       */
      logout: async () => {
        try {
          // The backend automatically extracts and blacklists the refresh cookie
          await authApi.logout();
        } catch (err) {
          console.warn(
            '[authStore] Token blacklisting failed — local logout will proceed:',
            err.message
          );
        }

        // Clear local profile state
        set({
          user:            null,
          isAuthenticated: false,
          loading:         false,
        });
      },


      /**
       * WHAT: Password reset request.
       */
      forgotPassword: async (email) => {
        await authApi.forgotPassword({ email });
      },


      /**
       * WHAT: Optimistic user profile updater.
       */
      updateUser: (updatedFields) => {
        const { user } = get();
        if (!user) return;
        set({ user: { ...user, ...updatedFields } });
      },

    }),

    {
      name:    'kyapture-auth',
      storage: createJSONStorage(() => localStorage),

      // Enforce: Persist only the safe user profile metadata—NO sensitive JWT credentials!
      partialize: (state) => ({
        user:            state.user,
        isAuthenticated: state.isAuthenticated,
      }),
    }
  )
);