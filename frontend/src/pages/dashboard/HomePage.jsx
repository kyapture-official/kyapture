// C:/Users/LENOVO/Desktop/kyapture/frontend/src/pages/dashboard/HomePage.jsx
import React, {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { Link } from "react-router-dom";
import { useAuthStore } from "../../store/authStore";
import { galleriesApi } from "../../api/galleriesApi";
import { subscriptionsApi } from "../../api/subscriptionsApi";
import Badge from "../../components/ui/Badge";
import { formatDate } from "../../utils/formatters";

// Confirm this mapping against your backend's actual subscription-status enum —
// anything not listed here falls back to the neutral 'default' badge instead of
// silently reading as an error.
const STATUS_BADGE_VARIANT = {
  active: "success",
  trialing: "success",
  pending: "warning",
  past_due: "warning",
  incomplete: "warning",
  canceled: "danger",
  unpaid: "danger",
  expired: "danger",
};

export default function HomePage() {
  const { user } = useAuthStore();
  const [galleries, setGalleries] = useState([]);
  const [dashboardStats, setDashboardStats] = useState(null);
  const [sub, setSub] = useState(null);
  const [loading, setLoading] = useState(true);
  const [galleriesError, setGalleriesError] = useState(false);
  const [subError, setSubError] = useState(false);
  const mountedRef = useRef(true);

  const loadDashboard = useCallback(() => {
    setLoading(true);
    setGalleriesError(false);
    setSubError(false);

    const statsPromise = galleriesApi
      .getDashboardStats()
      .then((data) => {
        if (!mountedRef.current) return;
        setDashboardStats(data);
      })
      .catch(() => {
        if (!mountedRef.current) return;
        setDashboardStats(null);
      });

    // UNVERIFIED FROM THIS FILE ALONE: assumes getGalleries() resolves with the
    // unwrapped payload ({ results: [...] }), not a raw axios response. Confirm
    // against galleriesApi.js.
    const galleriesPromise = galleriesApi
      .getGalleries()
      .then((data) => {
        if (!mountedRef.current) return;
        setGalleries(data?.results || []);
      })
      .catch(() => {
        if (!mountedRef.current) return;
        setGalleries([]);
        setGalleriesError(true);
      });

    // UNVERIFIED FROM THIS FILE ALONE: assumes mySubscription() resolves with the
    // raw axios response (needs r.data) and that "no subscription" is a 404 on a
    // standard axios rejection shape (err.response.status). If subscriptionsApi
    // normalizes errors the way clientsApi.js does, this check needs to change.
    const subPromise = subscriptionsApi
      .getMyPlan()
      .then((sub) => {
        if (!mountedRef.current) return;
        setSub(sub); // no `.data` — getMyPlan() already returns the parsed body
      })
      .catch((err) => {
        if (!mountedRef.current) return;
        setSub(null);
        if (err?.response?.status !== 404) setSubError(true);
      });

    return Promise.all([statsPromise, galleriesPromise, subPromise]).finally(
      () => {
        if (mountedRef.current) setLoading(false);
      },
    );
  }, []);

  useEffect(() => {
    mountedRef.current = true;
    loadDashboard();
    return () => {
      mountedRef.current = false;
    };
  }, [loadDashboard]);

  const planName = sub?.plan?.name ?? "Free";

  const stats = useMemo(
    () => [
      {
        label: "Total Galleries",
        value: dashboardStats?.galleries_used ?? galleries.length,
      },
      {
        label: "Published",
        value:
          dashboardStats?.published_galleries ??
          galleries.filter((g) => g.is_published).length,
      },
      {
        label: "Protected",
        value:
          dashboardStats?.protected_galleries ??
          galleries.filter((g) => g.has_password).length,
      },
      { label: "Plan", value: planName },
    ],
    [dashboardStats, galleries, planName],
  );

  return (
    <div>
      {/* Greeting */}
      <div className="mb-10 animate-fade-up">
        <h1 className="font-serif text-4xl text-ink mb-1">
          Good morning, {user?.display_name?.split(" ")[0] || user?.username} ✦
        </h1>
        <p className="text-muted text-sm">
          Your studio at{" "}
          <code className="bg-cream-200 px-1.5 py-0.5 rounded text-xs text-ink">
            {user?.username}.kyapture.com
          </code>
        </p>
      </div>

      {/* Stats */}
      {!loading && (
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-10 animate-fade-up delay-100">
          {stats.map((s) => (
            <div
              key={s.label}
              className="bg-white rounded-2xl border border-cream-200 p-5"
            >
              <p className="text-xs text-muted mb-1">{s.label}</p>
              <p className="font-serif text-3xl text-ink">{s.value}</p>
            </div>
          ))}
        </div>
      )}

      {/* Subscription status */}
      {!loading && subError && (
        <div className="mb-10 animate-fade-up delay-200 bg-white rounded-2xl border border-red-200 p-5 flex items-center justify-between">
          <p className="text-sm text-muted">
            Couldn&apos;t load your subscription status.
          </p>
          <button
            onClick={loadDashboard}
            className="text-sm font-medium text-ink underline underline-offset-2"
          >
            Retry
          </button>
        </div>
      )}

      {!loading && !subError && sub && (
        <div className="mb-10 animate-fade-up delay-200 bg-white rounded-2xl border border-cream-200 p-5 flex items-center justify-between">
          <div>
            <p className="text-sm font-medium text-ink mb-1">{planName} Plan</p>
            <p className="text-xs text-muted">
              {sub.expires_at
                ? `Expires ${formatDate(sub.expires_at)}`
                : "No expiration"}{" "}
              · via {sub.payment_method}
            </p>
          </div>
          <Badge variant={STATUS_BADGE_VARIANT[sub.status] || "default"}>
            {sub.status}
          </Badge>
        </div>
      )}

      {/* Recent galleries */}
      <div className="animate-fade-up delay-300">
        <div className="flex items-center justify-between mb-5">
          <h2 className="font-serif text-2xl text-ink">Recent Galleries</h2>
          <Link
            to="/dashboard/galleries"
            className="text-sm text-muted hover:text-ink underline underline-offset-2"
          >
            View all
          </Link>
        </div>

        {loading ? (
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            {[1, 2, 3].map((i) => (
              <div key={i} className="skeleton h-40 rounded-2xl" />
            ))}
          </div>
        ) : galleriesError ? (
          <div className="py-16 text-center bg-white rounded-2xl border border-red-200 border-dashed">
            <p className="text-muted text-sm mb-4">
              Couldn&apos;t load your galleries.
            </p>
            <button
              onClick={loadDashboard}
              className="inline-flex items-center gap-2 bg-ink text-cream-50 px-5 py-2.5 rounded-xl text-sm font-medium hover:bg-stone-700 transition-colors"
            >
              Retry
            </button>
          </div>
        ) : galleries.length === 0 ? (
          <div className="py-16 text-center bg-white rounded-2xl border border-cream-200 border-dashed">
            <p className="text-muted text-sm mb-4">
              No galleries yet. Create your first one.
            </p>
            <Link
              to="/dashboard/galleries"
              className="inline-flex items-center gap-2 bg-ink text-cream-50 px-5 py-2.5 rounded-xl text-sm font-medium hover:bg-stone-700 transition-colors"
            >
              Create Gallery
            </Link>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            {galleries.slice(0, 6).map((gallery) => (
              <Link
                key={gallery.id}
                to={`/dashboard/galleries/${gallery.slug}`}
                className="group bg-white rounded-2xl border border-cream-200 overflow-hidden hover:border-cream-400 hover:shadow-sm transition-all duration-200"
              >
                <div className="h-36 bg-cream-100 relative overflow-hidden">
                  {gallery.cover_photo ? (
                    <img
                      src={
                        gallery.cover_photo.thumbnail ||
                        gallery.cover_photo.image
                      }
                      alt={
                        gallery.title
                          ? `${gallery.title} cover photo`
                          : "Gallery cover photo"
                      }
                      className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-500"
                    />
                  ) : (
                    <div className="w-full h-full flex items-center justify-center text-cream-300">
                      <svg
                        className="w-10 h-10"
                        fill="none"
                        stroke="currentColor"
                        viewBox="0 0 24 24"
                      >
                        <path
                          strokeLinecap="round"
                          strokeLinejoin="round"
                          strokeWidth={1}
                          d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z"
                        />
                      </svg>
                    </div>
                  )}
                  {gallery.branding_color && (
                    <div
                      className="absolute top-2 right-2 w-3 h-3 rounded-full"
                      style={{ backgroundColor: gallery.branding_color }}
                    />
                  )}
                </div>
                <div className="p-4">
                  <p className="font-medium text-ink text-sm truncate mb-1">
                    {gallery.title}
                  </p>
                  <div className="flex items-center gap-2">
                    <Badge
                      variant={gallery.is_published ? "success" : "default"}
                    >
                      {gallery.is_published ? "Published" : "Draft"}
                    </Badge>
                    {gallery.has_password && (
                      <Badge variant="warning">Protected</Badge>
                    )}
                  </div>
                </div>
              </Link>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
