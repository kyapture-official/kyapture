import { NavLink, Link } from "react-router-dom";
import { formatDate } from "../../utils/formatters";

/**
 * WHAT: Gallery Workspace Navigation Sidebar
 * WHY:  Handles contextual navigation across standard views within a single gallery.
 *       Defends against parsing crashes during initial fetch states.
 */
export default function CollectionSidebar({ gallery }) {
  if (!gallery) {
    return (
      <aside className="w-full md:w-72 md:min-h-screen flex-shrink-0 bg-white border-b md:border-b-0 md:border-r border-slate-200 px-5 py-6 flex flex-col justify-center items-center">
        <div className="animate-pulse w-full h-8 bg-slate-100 rounded-xl mb-4" />
        <div className="animate-pulse w-full aspect-[4/3] bg-slate-100 rounded-2xl mb-6" />
      </aside>
    );
  }
  return (
    <aside className="w-full md:w-72 md:min-h-screen flex-shrink-0 bg-white border-b md:border-b-0 md:border-r border-slate-200 flex flex-col">
      {/* Gallery Header */}
      <div className="px-5 py-5 border-b border-slate-200">
        <h2 className="font-serif text-xl text-ink font-semibold truncate">
          {gallery.title}
        </h2>
        <p className="text-xs text-muted mt-1">
          {gallery.event_date ? (
            formatDate(gallery.event_date)
          ) : (
            <>Created {formatDate(gallery.created_at)}</>
          )}
        </p>
      </div>

      {/* Cover Image */}
      <div className="mx-5 mt-4 w-[calc(100%-2.5rem)] aspect-[4/3] rounded-2xl overflow-hidden bg-slate-100 border border-slate-200">
        {gallery.cover_url ? (
          <img
            src={gallery.cover_url}
            alt={`${gallery.title} cover`}
            className="w-full h-full object-cover"
          />
        ) : (
          <div
            className="w-full h-full flex items-center justify-center"
            style={{ backgroundColor: gallery.branding_color || "#0D9488" }}
          >
            <svg
              xmlns="http://www.w3.org/2000/svg"
              width="32"
              height="32"
              viewBox="0 0 24 24"
              fill="none"
              stroke="white"
              strokeOpacity="0.6"
              strokeWidth="1.5"
            >
              <path d="M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2 2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 1 2 2z" />
              <circle cx="12" cy="13" r="4" />
            </svg>
          </div>
        )}
      </div>

      {/* Navigation */}
      <nav className="flex flex-row md:flex-col gap-1 px-3 py-4">
        <NavLink
          to={`/dashboard/galleries/${gallery.slug}`}
          end
          className={({ isActive }) =>
            `flex items-center gap-2.5 px-3 py-2.5 rounded-xl text-sm font-medium transition-all duration-200 relative ${
              isActive
                ? "bg-teal-500/10 text-teal-600 font-semibold"
                : "text-slate-500 hover:text-ink hover:bg-slate-50"
            }`
          }
        >
          {({ isActive }) => (
            <>
              {isActive && (
                <div className="absolute left-0 top-1/2 -translate-y-1/2 w-[3px] h-5 rounded-r-full bg-teal-500" />
              )}
              <svg className="w-4 h-4 flex-shrink-0" fill="none" stroke="currentColor" strokeWidth="1.8" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" d="M2.25 15.75l5.159-5.159a2.25 2.25 0 013.182 0l5.159 5.159m-1.5-1.5l1.409-1.409a2.25 2.25 0 013.182 0l2.909 2.909m-18 3.75h16.5a1.5 1.5 0 001.5-1.5V6a1.5 1.5 0 00-1.5-1.5H3.75A1.5 1.5 0 002.25 6v12a1.5 1.5 0 001.5 1.5z" />
              </svg>
              Photos
            </>
          )}
        </NavLink>
        <NavLink
          to={`/dashboard/galleries/${gallery.slug}/settings`}
          className={({ isActive }) =>
            `flex items-center gap-2.5 px-3 py-2.5 rounded-xl text-sm font-medium transition-all duration-200 relative ${
              isActive
                ? "bg-teal-500/10 text-teal-600 font-semibold"
                : "text-slate-500 hover:text-ink hover:bg-slate-50"
            }`
          }
        >
          {({ isActive }) => (
            <>
              {isActive && (
                <div className="absolute left-0 top-1/2 -translate-y-1/2 w-[3px] h-5 rounded-r-full bg-teal-500" />
              )}
              <svg className="w-4 h-4 flex-shrink-0" fill="none" stroke="currentColor" strokeWidth="1.8" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" d="M9.594 3.94c.09-.542.56-.94 1.11-.94h2.593c.55 0 1.02.398 1.11.94l.213 1.281c.063.374.313.686.645.87.074.04.147.083.22.127.324.196.72.257 1.075.124l1.217-.456a1.125 1.125 0 011.37.49l1.296 2.247a1.125 1.125 0 01-.26 1.43l-1.003.828c-.293.241-.438.613-.43.992a7.723 7.723 0 010 .255c-.008.378.137.75.43.991l1.004.827c.424.35.534.954.26 1.43l-1.297 2.247a1.125 1.125 0 01-1.369.491l-1.217-.456c-.355-.133-.75-.072-1.076.124a6.47 6.47 0 01-.22.128c-.331.183-.581.495-.644.869l-.213 1.281c-.09.543-.56.94-1.11.94h-2.594c-.552 0-1.02-.398-1.11-.94l-.213-1.281c-.062-.374-.312-.686-.644-.87a6.52 6.52 0 01-.22-.127c-.325-.196-.72-.257-1.076-.124l-1.217.456a1.125 1.125 0 01-1.369-.49l-1.297-2.247a1.125 1.125 0 01.26-1.43l1.004-.827c.292-.24.437-.613.43-.991a6.932 6.932 0 010-.255c.007-.38-.138-.751-.43-.992l-1.004-.827a1.125 1.125 0 01-.26-1.43l1.297-2.247a1.125 1.125 0 011.37-.491l1.216.456c.356.133.751.072 1.076-.124.072-.044.146-.086.22-.128.332-.183.582-.495.644-.869l.214-1.28Z" />
                <path strokeLinecap="round" strokeLinejoin="round" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
              </svg>
              Settings
            </>
          )}
        </NavLink>
      </nav>

      {/* Back Link */}
      <div className="mt-auto px-5 py-4 border-t border-slate-200">
        <Link
          to="/dashboard/galleries"
          className="flex items-center gap-1.5 text-xs text-slate-500 hover:text-ink transition-colors group"
        >
          <svg className="w-3.5 h-3.5 group-hover:-translate-x-0.5 transition-transform" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" d="M10.5 19.5L3 12m0 0l7.5-7.5M3 12h18" />
          </svg>
          Back to Collections
        </Link>
      </div>
    </aside>
  );
}
