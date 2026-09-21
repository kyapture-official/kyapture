// frontend/src/pages/auth/RegisterPage.jsx
import { useState, useEffect } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useAuthStore } from "../../store/authStore";
import { validateEmail, validateUsername } from "../../utils/validator";

export default function RegisterPage() {
  const navigate = useNavigate();

  const isAuthenticated = useAuthStore((state) => state.isAuthenticated);
  const register = useAuthStore((state) => state.register);

  const [form, setForm] = useState({
    displayName: "",
    username: "",
    email: "",
    password: "",
    confirmPassword: "",
  });

  const [showPassword, setShowPassword] = useState(false);
  const [errors, setErrors] = useState({});
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (isAuthenticated) {
      navigate("/dashboard", { replace: true });
    }
  }, [isAuthenticated, navigate]);

  const handleChange = (e) => {
    const { name, value } = e.target;
    setForm((prev) => ({ ...prev, [name]: value }));
    if (errors[name]) {
      setErrors((prev) => ({ ...prev, [name]: "" }));
    }
  };

  function validate() {
    const fieldErrors = {};

    if (!form.displayName.trim() || form.displayName.trim().length < 3) {
      fieldErrors.displayName = "Business name must be at least 3 characters.";
    }

    const usernameCheck = validateUsername(form.username);
    if (!usernameCheck.isValid) {
      fieldErrors.username = usernameCheck.error;
    }

    const emailCheck = validateEmail(form.email);
    if (!emailCheck.isValid) {
      fieldErrors.email = emailCheck.error;
    }

    if (!form.password || form.password.length < 8) {
      fieldErrors.password = "Password must be at least 8 characters.";
    }

    if (form.confirmPassword !== form.password) {
      fieldErrors.confirmPassword = "Passwords do not match.";
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
      username: form.username.toLowerCase().trim(),
      email: form.email.trim(),
      password: form.password,
      password2: form.confirmPassword,
      display_name: form.displayName.trim(),
    };

    try {
      await register(payload);
      navigate("/dashboard", { replace: true });
    } catch (err) {
      const responseData = err.response?.data || {};
      const validationDetails = responseData.details || {};
      const parsedErrors = {};

      const keyMap = {
        display_name: "displayName",
        username: "username",
        email: "email",
        password: "password",
        password2: "confirmPassword",
        non_field_errors: "general",
      };

      Object.entries(validationDetails).forEach(([key, value]) => {
        const formKey = keyMap[key] || null;
        const errorMessage = Array.isArray(value) ? value[0] : String(value);
        if (formKey) {
          parsedErrors[formKey] = errorMessage;
        } else {
          parsedErrors.general = parsedErrors.general
            ? `${parsedErrors.general} ${errorMessage}`
            : errorMessage;
        }
      });

      const hasActionableFeedback = Object.keys(parsedErrors).length > 0;

      if (responseData.error && !hasActionableFeedback) {
        parsedErrors.general = responseData.error;
      }

      if (Object.keys(parsedErrors).length === 0) {
        parsedErrors.general = "Failed to create account. Please try again.";
      }

      setErrors(parsedErrors);
      setLoading(false);
    }
  };

  const previewUsername = form.username.toLowerCase().trim() || "yourname";

  return (
    <div className="auth-page">
      <div className="auth-page__bg" />
      <div className="auth-page__grid" />

      <Link to="/" className="auth-page__back">&larr; Back to home</Link>

      <div className="auth-card animate-fadeUp">
        {/* Logo */}
        <div className="auth-card__logo">
          <div className="auth-card__logo-icon">📸</div>
          <div className="auth-card__brand">Kyapture</div>
        </div>

        <h1 className="auth-card__title">Create your account</h1>
        <p className="auth-card__sub">Start delivering beautiful galleries today</p>

        {/* Tabs */}
        <div className="auth-tabs">
          <Link to="/login" className="auth-tab" style={{ textDecoration: "none", textAlign: "center" }}>
            Sign in
          </Link>
          <button className="auth-tab auth-tab--active" type="button">
            Create account
          </button>
        </div>

        <form onSubmit={handleSubmit} noValidate>
          {/* General error banner */}
          {errors.general && (
            <div
              role="alert"
              style={{
                marginBottom: 16, padding: "10px 14px",
                background: "rgba(192,72,58,0.08)", border: "1px solid rgba(192,72,58,0.2)",
                borderRadius: 9, fontSize: 13, color: "var(--red)",
              }}
            >
              {errors.general}
            </div>
          )}

          {/* Business name + Username row */}
          <div className="form-row">
            <div className="form-group">
              <label className="form-label" htmlFor="reg-display-name">Business name</label>
              <input
                id="reg-display-name"
                className={`form-input ${errors.displayName ? "error" : ""}`}
                type="text"
                name="displayName"
                autoComplete="organization"
                placeholder="Doe Photography"
                value={form.displayName}
                onChange={handleChange}
                disabled={loading}
                aria-invalid={!!errors.displayName}
                aria-describedby={errors.displayName ? "err-display-name" : undefined}
              />
              {errors.displayName && (
                <div id="err-display-name" className="form-error">{errors.displayName}</div>
              )}
            </div>

            <div className="form-group">
              <label className="form-label" htmlFor="reg-username">Username</label>
              <input
                id="reg-username"
                className={`form-input ${errors.username ? "error" : ""}`}
                type="text"
                name="username"
                autoComplete="username"
                placeholder="yourname"
                value={form.username}
                onChange={handleChange}
                disabled={loading}
                aria-invalid={!!errors.username}
                aria-describedby={errors.username ? "err-username" : "username-preview"}
              />
              {errors.username && (
                <div id="err-username" className="form-error">{errors.username}</div>
              )}
            </div>
          </div>

          <p id="username-preview" aria-live="polite" className="form-hint" style={{ marginBottom: 16 }}>
            Your gallery link:{" "}
            <span style={{ fontWeight: 600, color: "var(--ink)" }}>
              {previewUsername}.kyapture.com
            </span>
          </p>

          {/* Email */}
          <div className="form-group">
            <label className="form-label" htmlFor="reg-email">Email address</label>
            <input
              id="reg-email"
              className={`form-input ${errors.email ? "error" : ""}`}
              type="email"
              name="email"
              autoComplete="email"
              placeholder="you@example.com"
              value={form.email}
              onChange={handleChange}
              disabled={loading}
              aria-invalid={!!errors.email}
              aria-describedby={errors.email ? "err-email" : undefined}
            />
            {errors.email && (
              <div id="err-email" className="form-error">{errors.email}</div>
            )}
          </div>

          {/* Password */}
          <div className="form-group">
            <label className="form-label" htmlFor="reg-password">Password</label>
            <div className="input-wrap">
              <input
                id="reg-password"
                className={`form-input ${errors.password ? "error" : ""}`}
                type={showPassword ? "text" : "password"}
                name="password"
                autoComplete="new-password"
                placeholder="Minimum 8 characters"
                value={form.password}
                onChange={handleChange}
                disabled={loading}
                aria-invalid={!!errors.password}
                aria-describedby={errors.password ? "err-password" : undefined}
              />
              <button
                type="button"
                className="eye-btn"
                onClick={() => setShowPassword((p) => !p)}
                disabled={loading}
                aria-label={showPassword ? "Hide password" : "Show password"}
              >
                {showPassword ? "🙈" : "👁"}
              </button>
            </div>
            {errors.password && (
              <div id="err-password" className="form-error">{errors.password}</div>
            )}
          </div>

          {/* Confirm password */}
          <div className="form-group">
            <label className="form-label" htmlFor="reg-confirm">Confirm password</label>
            <input
              id="reg-confirm"
              className={`form-input ${errors.confirmPassword ? "error" : ""}`}
              type="password"
              name="confirmPassword"
              autoComplete="new-password"
              placeholder="Repeat your password"
              value={form.confirmPassword}
              onChange={handleChange}
              disabled={loading}
              aria-invalid={!!errors.confirmPassword}
              aria-describedby={errors.confirmPassword ? "err-confirm" : undefined}
            />
            {errors.confirmPassword && (
              <div id="err-confirm" className="form-error">{errors.confirmPassword}</div>
            )}
          </div>

          <button className="btn-submit" type="submit" disabled={loading}>
            {loading ? (
              <div style={{ display: "flex", alignItems: "center", justifyContent: "center", gap: 8 }}>
                <div className="spinner" />
                <span>Creating account…</span>
              </div>
            ) : (
              "Create my account"
            )}
          </button>

          <p className="auth-footer-text">
            Already have an account?{" "}
            <Link to="/login" className="auth-link">Sign in</Link>
          </p>
        </form>
      </div>
    </div>
  );
}
