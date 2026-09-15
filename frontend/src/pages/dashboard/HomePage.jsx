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

// Stat card gradient configurations
const STAT_STYLES = [
  { accent: 'from-teal-500 to-teal-400', bg: 'bg-teal-50', icon: 'text-teal-600' },
  { accent: 'from-emerald-500 to-emerald-400', bg: 'bg-emerald-50', icon: 'text-emerald-600' },
  { accent: 'from-blue-500 to-blue-400', bg: 'bg-blue-50', icon: 'text-blue-600' },
  { accent: 'from-violet-500 to-violet-400', bg: 'bg-violet-50', icon: 'text-violet-600' },
]

const STAT_ICONS = [
  // Galleries
  <svg key="g" className="w-5 h-5" fill="none" stroke="currentColor" strokeWidth="1.8" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" d="M2.25 15.75l5.159-5.159a2.25 2.25 0 013.182 0l5.159 5.159m-1.5-1.5l1.409-1.409a2.25 2.25 0 013.182 0l2.909 2.909m-18 3.75h16.5a1.5 1.5 0 001.5-1.5V6a1.5 1.5 0 00-1.5-1.5H3.75A1.5 1.5 0 002.25 6v12a1.5 1.5 0 001.5 1.5z" /></svg>,
  // Published
  <svg key="p" className="w-5 h-5" fill="none" stroke="currentColor" strokeWidth="1.8" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" d="M12 21a9.004 9.004 0 008.716-6.747M12 21a9.004 9.004 0 01-8.716-6.747M12 21c2.485 0 4.5-4.03 4.5-9S14.485 3 12 3m0 18c-2.485 0-4.5-4.03-4.5-9S9.515 3 12 3m0 0a8.997 8.997 0 017.843 4.582M12 3a8.997 8.997 0 00-7.843 4.582m15.686 0A11.953 11.953 0 0112 10.5c-2.998 0-5.74-1.1-7.843-2.918m15.686 0A8.959 8.959 0 0121 12c0 .778-.099 1.533-.284 2.253m0 0A17.919 17.919 0 0112 16.5c-3.162 0-6.133-.815-8.716-2.247m0 0A9.015 9.015 0 013 12c0-1.605.42-3.113 1.157-4.418" /></svg>,
  // Protected
  <svg key="l" className="w-5 h-5" fill="none" stroke="currentColor" strokeWidth="1.8" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" d="M16.5 10.5V6.75a4.5 4.5 0 10-9 0v3.75m-.75 11.25h10.5a2.25 2.25 0 002.25-2.25v-6.75a2.25 2.25 0 00-2.25-2.25H6.75a2.25 2.25 0 00-2.25 2.25v6.75a2.25 2.25 0 002.25 2.25z" /></svg>,
  // Plan
  <svg key="s" className="w-5 h-5" fill="none" stroke="currentColor" strokeWidth="1.8" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" d="M3.75 13.5l10.5-11.25L12 10.5h8.25L9.75 21.75 12 13.5H3.75z" /></svg>,
]

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

    const subPromise = subscriptionsApi
      .getMyPlan()
      .then((sub) => {
        if (!mountedRef.current) return;
        setSub(sub);
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
  const studioUrl = user?.username ? `${user.username}.kyapture.com` : '';

  // Time-based greeting
  const greeting = useMemo(() => {
    const hour = new Date().getHours();
    if (hour < 12) return "Good morning";
    if (hour < 17) return "Good afternoon";
    return "Good evening";
  }, []);

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
      { label: "Current Plan", value: planName },
    ],
    [dashboardStats, galleries, planName],
  );

  return (
    <div className="max-w-7xl mx-auto space-y-8 animate-fade-up">

      {/* ── GREETING HERO ── */}
      <div className="relative overflow-hidden rounded-2xl bg-gradient-to-br from-white to-slate-100 border border-slate-200 p-6 md:p-8">
        {/* Decorative gradient orb */}
        <div className="absolute -top-20 -right-20 w-60 h-60 bg-gradient-to-br from-teal-500/10 to-emerald-500/5 rounded-full blur-3xl pointer-events-none" />
        <div className="absolute -bottom-16 -left-16 w-40 h-40 bg-gradient-to-tr from-blue-500/8 to-transparent rounded-full blur-2xl pointer-events-none" />

        <div className="relative z-10">
          <h1 className="font-serif text-3xl md:text-4xl text-ink mb-1">
            {greeting}, {user?.display_name?.split(" ")[0] || user?.username}
          </h1>
          <p className="text-slate-500 text-sm flex items-center gap-1.5 mt-2">
            Your studio at
            <code className="bg-slate-200/80 px-2 py-0.5 rounded-md text-xs text-ink font-mono">
              {studioUrl}
            </code>
          </p>
        </div>
      </div>

      {/* ── STAT CARDS ── */}
      {!loading && (
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          {stats.map((s, i) => {
            const style = STAT_STYLES[i]
            return (
              <div
                key={s.label}
                className="group relative bg-white rounded-2xl border border-slate-200 p-5 overflow-hidden hover:shadow-stat-hover hover:border-slate-300 transition-all duration-300 cursor-default"
              >
                {/* Gradient top accent */}
                <div className={`absolute top-0 left-0 right-0 h-[2px] bg-gradient-to-r ${style.accent}`} />

                {/* Background icon watermark */}
                <div className={`absolute -bottom-2 -right-2 ${style.icon} opacity-[0.04] group-hover:opacity-[0.08] transition-opacity`}>
                  {STAT_ICONS[i]}
                </div>

                <div className="relative z-10">
                  <div className={`w-9 h-9 rounded-xl ${style.bg} flex items-center justify-center mb-3`}>
                    <span className={style.icon}>{STAT_ICONS[i]}</span>
                  </div>
                  <p className="text-[11px] font-semibold text-slate-500 uppercase tracking-wider mb-1">
                    {s.label}
                  </p>
                  <p className="font-serif text-3xl text-ink leading-none">
                    {s.value}
                  </p>
                </div>
              </div>
            )
          })}
        </div>
      )}

      {/* ── SUBSCRIPTION STATUS ── */}
      {!loading && subError && (
        <div className="bg-white rounded-2xl border border-red-200 p-5 flex items-center justify-between animate-fade-up delay-200">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-xl bg-red-50 flex items-center justify-center">
              <svg className="w-5 h-5 text-red-500" fill="none" stroke="currentColor" strokeWidth="1.8" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126zM12 15.75h.007v.008H12v-.008z" />
              </svg>
            </div>
            <div>
              <p className="text-sm font-medium text-ink">Subscription unavailable</p>
              <p className="text-xs text-slate-500">Could not load your plan status.</p>
            </div>
          </div>
          <button
            onClick={loadDashboard}
            className="text-xs font-semibold text-ink px-4 py-2 rounded-xl border border-slate-200 hover:border-slate-300 hover:bg-slate-50 transition-all cursor-pointer"
          >
            Retry
          </button>
        </div>
      )}

      {!loading && !subError && sub && (
        <div className="bg-white rounded-2xl border border-slate-200 p-5 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 animate-fade-up delay-200">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-xl bg-emerald-50 flex items-center justify-center">
              <svg className="w-5 h-5 text-emerald-600" fill="none" stroke="currentColor" strokeWidth="1.8" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" d="M3.75 13.5l10.5-11.25L12 10.5h8.25L9.75 21.75 12 13.5H3.75z" />
              </svg>
            </div>
            <div>
              <p className="text-sm font-medium text-ink">{planName} Plan</p>
              <p className="text-xs text-slate-500">
                {sub.expires_at
                  ? `Expires ${formatDate(sub.expires_at)}`
                  : "No expiration"}{" "}
                &middot; via {sub.payment_method}
              </p>
            </div>
          </div>
          <Badge variant={STATUS_BADGE_VARIANT[sub.status] || "default"}>
            {sub.status}
          </Badge>
        </div>
      )}

      {/* ── RECENT GALLERIES ── */}
      <div className="animate-fade-up delay-300">
        <div className="flex items-center justify-between mb-5">
          <h2 className="font-serif text-2xl text-ink">Recent Galleries</h2>
          <Link
            to="/dashboard/galleries"
            className="text-xs font-semibold text-slate-500 hover:text-ink transition-colors flex items-center gap-1"
          >
            View all
            <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" strokeWidth="2.5" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" d="M8.25 4.5l7.5 7.5-7.5 7.5" />
            </svg>
          </Link>
        </div>

        {loading ? (
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            {[1, 2, 3].map((i) => (
              <div key={i} className="skeleton h-56 rounded-2xl" />
            ))}
          </div>
        ) : galleriesError ? (
          <div className="py-16 text-center bg-white rounded-2xl border border-red-200 border-dashed">
            <div className="w-12 h-12 rounded-full bg-red-50 flex items-center justify-center mx-auto mb-4">
              <svg className="w-6 h-6 text-red-400" fill="none" stroke="currentColor" strokeWidth="1.5" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v3.75m9-.75a9 9 0 11-18 0 9 9 0 0118 0zm-9 3.75h.008v.008H12v-.008z" />
              </svg>
            </div>
            <p className="text-slate-500 text-sm mb-4">
              Couldn&apos;t load your galleries.
            </p>
            <button
              onClick={loadDashboard}
              className="inline-flex items-center gap-2 bg-teal-600 text-white px-5 py-2.5 rounded-xl text-sm font-medium hover:bg-teal-700 transition-colors cursor-pointer"
            >
              Retry
            </button>
          </div>
        ) : galleries.length === 0 ? (
          <div className="py-16 text-center bg-white rounded-2xl border border-slate-200 border-dashed">
            <div className="w-12 h-12 rounded-full bg-slate-100 flex items-center justify-center mx-auto mb-4">
              <svg className="w-6 h-6 text-slate-400" fill="none" stroke="currentColor" strokeWidth="1.5" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" d="M12 4.5v15m7.5-7.5h-15" />
              </svg>
            </div>
            <p className="text-slate-500 text-sm mb-4">
              No galleries yet. Create your first one to start delivering photos.
            </p>
            <Link
              to="/dashboard/galleries"
              className="inline-flex items-center gap-2 bg-teal-600 text-white px-5 py-2.5 rounded-xl text-sm font-medium hover:bg-teal-700 transition-colors"
            >
              Create Gallery
            </Link>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {galleries.slice(0, 6).map((gallery) => (
              <Link
                key={gallery.id}
                to={`/dashboard/galleries/${gallery.slug}`}
                className="group bg-white rounded-2xl border border-slate-200 overflow-hidden hover:shadow-card-hover hover:border-slate-300 transition-all duration-300"
              >
                {/* Cover Image */}
                <div className="h-40 bg-slate-100 relative overflow-hidden">
                  {gallery.cover_photo ? (
                    <img
                      src={gallery.cover_photo.thumbnail || gallery.cover_photo.image}
                      alt={gallery.title ? `${gallery.title} cover photo` : "Gallery cover photo"}
                      className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-700 ease-out"
                    />
                  ) : (
                    <div className="w-full h-full flex items-center justify-center">
                      <svg className="w-10 h-10 text-slate-300" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1} d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z" />
                      </svg>
                    </div>
                  )}

                  {/* Branding color indicator */}
                  {gallery.branding_color && (
                    <div
                      className="absolute top-3 right-3 w-3 h-3 rounded-full ring-2 ring-white shadow-sm"
                      style={{ backgroundColor: gallery.branding_color }}
                    />
                  )}

                  {/* Badges overlay */}
                  <div className="absolute bottom-3 left-3 flex gap-1.5">
                    <Badge variant={gallery.is_published ? "success" : "default"}>
                      {gallery.is_published ? "Published" : "Draft"}
                    </Badge>
                    {gallery.has_password && (
                      <Badge variant="warning">Protected</Badge>
                    )}
                  </div>
                </div>

                {/* Card Body */}
                <div className="p-4">
                  <p className="font-medium text-ink text-sm truncate mb-1 group-hover:text-slate-700 transition-colors">
                    {gallery.title}
                  </p>
                  <div className="flex items-center justify-between">
                    <span className="text-[11px] text-slate-500 font-medium">
                      {gallery.photo_count || 0} photo{(gallery.photo_count || 0) !== 1 ? 's' : ''}
                    </span>
                    <span className="text-[11px] text-teal-600 font-semibold opacity-0 group-hover:opacity-100 transition-opacity flex items-center gap-0.5">
                      Manage
                      <svg className="w-3 h-3" fill="none" stroke="currentColor" strokeWidth="2.5" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" d="M8.25 4.5l7.5 7.5-7.5 7.5" />
                      </svg>
                    </span>
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
