// frontend/src/pages/auth/RegisterPage.jsx
// ─────────────────────────────────────────────────────────────────────────────
// WHAT: Registration page for new photographers.
// WHY this file exists: Captures business name, email, credentials, and the
//   username that becomes their public subdomain (username.kyapture.com).
//   On success, navigates to /dashboard immediately.
//
// ARCHITECTURAL NOTE ON STORE BINDINGS:
//   This file uses useAuthStore selectors. The exact fields (isAuthenticated,
//   register) must match your actual authStore.js. If your store exposes
//   { accessToken, setAuth } instead, change the two selector lines and the
//   try block accordingly. The rest of this file is store-agnostic.
// ─────────────────────────────────────────────────────────────────────────────

import { useState, useEffect } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useAuthStore } from '../../store/authStore';

export default function RegisterPage() {
  const navigate = useNavigate();

  // ── Store bindings ──────────────────────────────────────────────────────
  // WHY selector pattern (state => state.x):
  // Subscribes this component only to the specific field it needs.
  // Without a selector, any store change (even unrelated ones) re-renders
  // this entire page. Selectors are not optional — they are required for
  // performance correctness.
  //
  // NOTE: If your authStore.js does not have isAuthenticated and register,
  // replace these two lines with:
  //   const isAuthenticated = useAuthStore((state) => !!state.accessToken)
  //   const setAuth         = useAuthStore((state) => state.setAuth)
  // and update the try block to call authApi.register() + setAuth() directly.
  const isAuthenticated = useAuthStore((state) => state.isAuthenticated);
  const register        = useAuthStore((state) => state.register);

  const [form, setForm] = useState({
    displayName:     '',
    username:        '',
    email:           '',
    password:        '',
    confirmPassword: '',
  });

  const [showPassword, setShowPassword] = useState(false);
  const [errors,       setErrors]       = useState({});
  const [loading,      setLoading]      = useState(false);

  // ── Already-authenticated redirect ─────────────────────────────────────
  // WHY useEffect for this case only:
  // This handles exactly ONE scenario: a user who is already logged in
  // navigates to /register (types the URL directly or follows a link).
  // It fires on mount and on any isAuthenticated change.
  //
  // It does NOT handle the post-registration redirect. That happens
  // directly in the try block to avoid an extra render cycle and
  // the unmounted-component state update problem.
  useEffect(() => {
    if (isAuthenticated) {
      navigate('/dashboard', { replace: true });
    }
  }, [isAuthenticated, navigate]);

  const handleChange = (e) => {
    const { name, value } = e.target;
    setForm((prev) => ({ ...prev, [name]: value }));

    // WHY only clear the changed field's error:
    // A general server error ("email already registered") must remain
    // visible while the user reads and acts on it. Clearing it on the
    // first keystroke of any field removes it before they've finished reading.
    if (errors[name]) {
      setErrors((prev) => ({ ...prev, [name]: '' }));
    }
  };

  function validate() {
    const fieldErrors = {};

    if (!form.displayName.trim() || form.displayName.trim().length < 3) {
      fieldErrors.displayName = 'Business name must be at least 3 characters.';
    }

    const trimmedUsername = form.username.trim();
    const usernameRegex   = /^[a-zA-Z0-9_-]+$/;

    if (!trimmedUsername) {
      fieldErrors.username = 'Username is required.';
    } else if (trimmedUsername.length < 3) {
      fieldErrors.username = 'Username must be at least 3 characters.';
    } else if (trimmedUsername.length > 30) {
      fieldErrors.username = 'Username must be 30 characters or fewer.';
    } else if (!usernameRegex.test(trimmedUsername)) {
      fieldErrors.username = 'Only letters, numbers, underscores, and hyphens.';
    }

    if (!form.email || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(form.email)) {
      fieldErrors.email = 'Enter a valid email address.';
    }

    if (!form.password || form.password.length < 8) {
      fieldErrors.password = 'Password must be at least 8 characters.';
    }

    if (form.confirmPassword !== form.password) {
      fieldErrors.confirmPassword = 'Passwords do not match.';
    }

    return fieldErrors;
  }

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (loading) return;

    const fieldErrors = validate();
    if (Object.keys(fieldErrors).length > 0) {
      setErrors(fieldErrors);
      return;
    }

    setErrors({});
    setLoading(true);

    const payload = {
      username:     form.username.toLowerCase().trim(),
      email:        form.email.trim(),
      password:     form.password,
      password2:    form.confirmPassword,
      display_name: form.displayName.trim(),
    };

    try {
      await register(payload);

      // WHY navigate here and not rely on the useEffect:
      // If navigation were left to the useEffect, the sequence is:
      //   register() resolves → store updates → component re-renders →
      //   useEffect fires → navigate() → unmount → finally runs setLoading(false)
      //   on a dead component (React warning).
      //
      // Navigating directly here means:
      //   register() resolves → navigate() → unmount
      //   The finally block never runs because the component is gone.
      //   No unmounted state update. No extra render cycle. Clean.
      navigate('/dashboard', { replace: true });

    } catch (err) {
      const responseData = err.response?.data || {};
      const parsedErrors = {};

      if (responseData.non_field_errors) {
        parsedErrors.general = responseData.non_field_errors[0];
      } else if (responseData.detail) {
        parsedErrors.general = responseData.detail;
      } else {
        // WHY explicit keyMap over regex camelCase conversion:
        // The regex approach converts any unknown backend key automatically,
        // potentially mapping fields that do not exist in our form state.
        // The explicit map only accepts fields we know about. Anything
        // unexpected surfaces as a general error — visible to the user.
        const keyMap = {
          display_name: 'displayName',
          username:     'username',
          email:        'email',
          password:     'password',
        };
        Object.entries(responseData).forEach(([key, value]) => {
          const formKey      = keyMap[key] || null;
          const errorMessage = Array.isArray(value) ? value[0] : value;
          if (formKey) {
            parsedErrors[formKey] = errorMessage;
          } else {
            parsedErrors.general = errorMessage;
          }
        });
      }

      if (Object.keys(parsedErrors).length === 0) {
        parsedErrors.general = 'Failed to create account. Please try again.';
      }

      setErrors(parsedErrors);
      // WHY setLoading(false) here and not in finally:
      // On success, navigate() unmounts this component before finally runs.
      // Calling setLoading on an unmounted component produces a React warning.
      // On failure, the component stays mounted — setLoading here is safe.
      setLoading(false);
    }
  };

  const previewUsername = form.username.toLowerCase().trim() || 'yourname';

  return (
    <div className="min-h-screen bg-gray-50 flex items-center justify-center px-4 py-12">
      <div className="w-full max-w-md">

        <div className="text-center mb-8">
          <p className="text-2xl font-semibold tracking-tight text-gray-900">
            Kyapture
          </p>
          <p className="mt-1 text-sm text-gray-500">
            Start delivering beautiful galleries today
          </p>
        </div>

        <div className="bg-white rounded-2xl border border-gray-200 shadow-sm p-8">

          <div className="flex border border-gray-200 rounded-xl p-1 mb-6 gap-1">
            <Link
              to="/login"
              className="flex-1 text-center text-sm py-2 rounded-lg text-gray-500
                         hover:text-gray-800 transition-colors"
            >
              Sign in
            </Link>
            <button
              type="button"
              className="flex-1 text-center text-sm py-2 rounded-lg bg-gray-900
                         text-white font-medium cursor-default"
            >
              Create account
            </button>
          </div>

          {errors.general && (
            <div
              role="alert"
              className="mb-5 px-4 py-3 rounded-lg bg-red-50 border border-red-200
                         text-sm text-red-700"
            >
              {errors.general}
            </div>
          )}

          <form onSubmit={handleSubmit} noValidate>

            <div className="grid grid-cols-2 gap-3 mb-1">
              <div>
                <label
                  htmlFor="reg-display-name"
                  className="block text-sm font-medium text-gray-700 mb-1"
                >
                  Business name
                </label>
                <input
                  id="reg-display-name"
                  name="displayName"
                  type="text"
                  autoComplete="organization"
                  placeholder="Doe Photography"
                  value={form.displayName}
                  onChange={handleChange}
                  disabled={loading}
                  aria-invalid={!!errors.displayName}
                  aria-describedby={errors.displayName ? 'err-display-name' : undefined}
                  className={`w-full px-3 py-2 text-sm rounded-lg border
                    focus:outline-none focus:ring-2 focus:ring-offset-0 transition-colors
                    disabled:opacity-50 disabled:cursor-not-allowed
                    ${errors.displayName
                      ? 'border-red-400 bg-red-50 focus:ring-red-200'
                      : 'border-gray-300 focus:border-gray-400 focus:ring-gray-100'
                    }`}
                />
                {errors.displayName && (
                  <p id="err-display-name" className="mt-1 text-xs text-red-600">
                    {errors.displayName}
                  </p>
                )}
              </div>

              <div>
                <label
                  htmlFor="reg-username"
                  className="block text-sm font-medium text-gray-700 mb-1"
                >
                  Username
                </label>
                <input
                  id="reg-username"
                  name="username"
                  type="text"
                  autoComplete="username"
                  placeholder="yourname"
                  value={form.username}
                  onChange={handleChange}
                  disabled={loading}
                  aria-invalid={!!errors.username}
                  aria-describedby={errors.username ? 'err-username' : 'username-preview'}
                  className={`w-full px-3 py-2 text-sm rounded-lg border
                    focus:outline-none focus:ring-2 focus:ring-offset-0 transition-colors
                    disabled:opacity-50 disabled:cursor-not-allowed
                    ${errors.username
                      ? 'border-red-400 bg-red-50 focus:ring-red-200'
                      : 'border-gray-300 focus:border-gray-400 focus:ring-gray-100'
                    }`}
                />
                {errors.username && (
                  <p id="err-username" className="mt-1 text-xs text-red-600">
                    {errors.username}
                  </p>
                )}
              </div>
            </div>

            <p
              id="username-preview"
              aria-live="polite"
              className="mb-5 text-xs text-gray-400"
            >
              Your gallery link:{' '}
              <span className="font-medium text-gray-600">
                {previewUsername}.kyapture.com
              </span>
            </p>

            <div className="mb-4">
              <label
                htmlFor="reg-email"
                className="block text-sm font-medium text-gray-700 mb-1"
              >
                Email address
              </label>
              <input
                id="reg-email"
                name="email"
                type="email"
                autoComplete="email"
                placeholder="you@example.com"
                value={form.email}
                onChange={handleChange}
                disabled={loading}
                aria-invalid={!!errors.email}
                aria-describedby={errors.email ? 'err-email' : undefined}
                className={`w-full px-3 py-2 text-sm rounded-lg border
                  focus:outline-none focus:ring-2 focus:ring-offset-0 transition-colors
                  disabled:opacity-50 disabled:cursor-not-allowed
                  ${errors.email
                    ? 'border-red-400 bg-red-50 focus:ring-red-200'
                    : 'border-gray-300 focus:border-gray-400 focus:ring-gray-100'
                  }`}
              />
              {errors.email && (
                <p id="err-email" className="mt-1 text-xs text-red-600">
                  {errors.email}
                </p>
              )}
            </div>

            <div className="mb-4">
              <label
                htmlFor="reg-password"
                className="block text-sm font-medium text-gray-700 mb-1"
              >
                Password
              </label>
              <div className="relative">
                <input
                  id="reg-password"
                  name="password"
                  type={showPassword ? 'text' : 'password'}
                  autoComplete="new-password"
                  placeholder="Minimum 8 characters"
                  value={form.password}
                  onChange={handleChange}
                  disabled={loading}
                  aria-invalid={!!errors.password}
                  aria-describedby={errors.password ? 'err-password' : undefined}
                  className={`w-full pl-3 pr-10 py-2 text-sm rounded-lg border
                    focus:outline-none focus:ring-2 focus:ring-offset-0 transition-colors
                    disabled:opacity-50 disabled:cursor-not-allowed
                    ${errors.password
                      ? 'border-red-400 bg-red-50 focus:ring-red-200'
                      : 'border-gray-300 focus:border-gray-400 focus:ring-gray-100'
                    }`}
                />
                <button
                  type="button"
                  onClick={() => setShowPassword((p) => !p)}
                  disabled={loading}
                  aria-label={showPassword ? 'Hide password' : 'Show password'}
                  className="absolute inset-y-0 right-0 px-3 flex items-center
                             text-gray-400 hover:text-gray-600 transition-colors
                             disabled:cursor-not-allowed"
                >
                  {showPassword ? (
                    // Eye-off icon — hide password
                    <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16"
                         viewBox="0 0 24 24" fill="none" stroke="currentColor"
                         strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"
                         aria-hidden="true">
                      <path d="M17.94 17.94A10.07 10.07 0 0112 20c-7 0-11-8-11-8
                               a18.45 18.45 0 015.06-5.94M9.9 4.24A9.12 9.12 0
                               0112 4c7 0 11 8 11 8a18.5 18.5 0 01-2.16 3.19"/>
                      <line x1="1" y1="1" x2="23" y2="23"/>
                    </svg>
                  ) : (
                    // Eye icon — show password
                    // WHY the space before "8" in "11 8" matters:
                    // "11-8" = x:11, y:-8 (negative, wrong shape)
                    // "11 8" = x:11,  y:8 (positive, correct oval arc)
                    <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16"
                         viewBox="0 0 24 24" fill="none" stroke="currentColor"
                         strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"
                         aria-hidden="true">
                      <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/>
                      <circle cx="12" cy="12" r="3"/>
                    </svg>
                  )}
                </button>
              </div>
              {errors.password && (
                <p id="err-password" className="mt-1 text-xs text-red-600">
                  {errors.password}
                </p>
              )}
            </div>

            <div className="mb-6">
              <label
                htmlFor="reg-confirm"
                className="block text-sm font-medium text-gray-700 mb-1"
              >
                Confirm password
              </label>
              <input
                id="reg-confirm"
                name="confirmPassword"
                type="password"
                autoComplete="new-password"
                placeholder="Repeat your password"
                value={form.confirmPassword}
                onChange={handleChange}
                disabled={loading}
                aria-invalid={!!errors.confirmPassword}
                aria-describedby={errors.confirmPassword ? 'err-confirm' : undefined}
                className={`w-full px-3 py-2 text-sm rounded-lg border
                  focus:outline-none focus:ring-2 focus:ring-offset-0 transition-colors
                  disabled:opacity-50 disabled:cursor-not-allowed
                  ${errors.confirmPassword
                    ? 'border-red-400 bg-red-50 focus:ring-red-200'
                    : 'border-gray-300 focus:border-gray-400 focus:ring-gray-100'
                  }`}
              />
              {errors.confirmPassword && (
                <p id="err-confirm" className="mt-1 text-xs text-red-600">
                  {errors.confirmPassword}
                </p>
              )}
            </div>

            <button
              type="submit"
              disabled={loading}
              className="w-full flex items-center justify-center gap-2 py-2.5 px-4
                         bg-gray-900 text-white text-sm font-medium rounded-lg
                         hover:bg-gray-800 transition-colors
                         disabled:opacity-60 disabled:cursor-not-allowed"
            >
              {loading ? (
                <>
                  <svg
                    className="animate-spin h-4 w-4 text-white"
                    xmlns="http://www.w3.org/2000/svg"
                    fill="none"
                    viewBox="0 0 24 24"
                    aria-hidden="true"
                  >
                    <circle className="opacity-25" cx="12" cy="12" r="10"
                            stroke="currentColor" strokeWidth="4" />
                    <path className="opacity-75" fill="currentColor"
                          d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                  </svg>
                  Creating account…
                </>
              ) : (
                'Create my account'
              )}
            </button>

            <p className="mt-5 text-center text-sm text-gray-500">
              Already have an account?{' '}
              <Link
                to="/login"
                className="font-medium text-gray-900 hover:underline"
              >
                Sign in
              </Link>
            </p>

          </form>
        </div>
      </div>
    </div>
  );
}