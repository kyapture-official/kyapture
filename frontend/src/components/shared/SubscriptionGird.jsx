// File Location: frontend/src/components/shared/SubscriptionGrid.jsx
// VERSION: Gold-Standard Production — Week 11
// Resolves scale-mismatches, prevents negative limits, and guards against NaN.

import { useSubscription } from "../../hooks/useSubscription";
import Spinner from "../ui/Spinner";

/**
 * WHAT: Visual Subscription Progress Grid
 * WHY:  Translates complex account metadata into clear, honest, and scannable
 *       usage metrics to support active plan gating controls [weekly tasks.txt].
 */
export default function SubscriptionGrid() {
  const { plan, limits, usage, loading } = useSubscription();

  if (loading) {
    return (
      <div className="flex py-10 items-center justify-center bg-white rounded-2xl border border-cream-200">
        <Spinner size="md" className="text-[#2C2825]" />
      </div>
    );
  }

  // ── DEFENSIVE PERCENTAGE CALCULATIONS ──────────────────────────────────────
  const calculatePercent = (used, max) => {
    const usedVal = parseFloat(used) || 0;
    const maxVal = parseFloat(max) || 0;
    if (maxVal <= 0) return 0;
    const percent = Math.round((usedVal / maxVal) * 100);
    return Math.min(percent, 100);
  };

  // BUG RESOLUTION: Implements float checks and enforces a bottom floor of 0
  // to prevent negative counts (e.g. "-3 remaining") on downgraded accounts.
  const remaining = (max, used) => {
    const maxVal = parseFloat(max) || 0;
    const usedVal = parseFloat(used) || 0;
    return Math.max(maxVal - usedVal, 0);
  };

  const galleryPercent = calculatePercent(
    usage.galleriesUsed,
    limits.max_galleries,
  );
  const storagePercent = calculatePercent(
    usage.storageUsedGb,
    limits.storage_gb,
  );

  // Dynamic capacity warning triggers
  const getProgressColor = (percent) => {
    if (percent >= 100) return "bg-red-500";
    if (percent >= 80) return "bg-[#C09A55]"; // Gold amber warning threshold
    return "bg-[#4a7c6f]"; // Standard green
  };

  return (
    <div className="space-y-4 animate-fadeUp font-sans">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-1.5 pb-2 border-b border-cream-100">
        <h3 className="font-serif text-lg text-ink font-bold">Usage Limits</h3>
        <span className="text-[10px] font-bold uppercase tracking-wider text-[#C09A55]">
          Current Plan: {plan?.name || "Free Tier"}
        </span>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        {/* 1. Collections: Comparing account-wide gallery count against an account-wide cap. */}
        <section className="bg-white p-5 rounded-2xl border border-cream-200 space-y-3 shadow-sm">
          <div className="flex justify-between items-baseline">
            <span className="text-xs text-muted font-bold uppercase tracking-wider">
              Collections
            </span>
            <span className="text-sm font-bold text-ink">
              {usage.galleriesUsed}{" "}
              <span className="text-xs text-muted font-light">
                /{" "}
                {limits.max_galleries == null
                  ? "Unlimited"
                  : limits.max_galleries}
              </span>
            </span>
          </div>
          {limits.max_galleries != null && (
            <div className="h-2 w-full bg-cream-100 rounded-full overflow-hidden">
              <div
                className={`h-full rounded-full transition-all duration-500 ${getProgressColor(galleryPercent)}`}
                style={{ width: `${galleryPercent}%` }}
              />
            </div>
          )}
          <p className="text-[10px] text-muted font-light">
            {limits.max_galleries == null
              ? "No limit on collections."
              : galleryPercent >= 100
                ? "Maximum galleries reached. Upgrade plan to create more."
                : `${remaining(limits.max_galleries, usage.galleriesUsed)} collections remaining.`}
          </p>
        </section>

        {/* 2. Photos: Displays honest aggregate upload metrics rather than a mathematically false ratio. */}
        <section className="bg-white p-5 rounded-2xl border border-cream-200 space-y-3 shadow-sm">
          <div className="flex justify-between items-baseline">
            <span className="text-xs text-muted font-bold uppercase tracking-wider">
              Photos Uploaded
            </span>
            <span className="text-sm font-bold text-ink">
              {usage.photosUsed}
            </span>
          </div>
          <p className="text-[10px] text-muted font-light leading-relaxed">
            {limits.max_photos_per_gallery == null ? (
              "No limit on photos per gallery."
            ) : (
              <>
                Each gallery can hold up to{" "}
                <strong className="text-ink font-semibold">
                  {limits.max_photos_per_gallery}
                </strong>{" "}
                photos.
              </>
            )}
            {!limits.allow_video && " Video uploads require a paid plan."}
          </p>
        </section>

        {/* 3. Disk Storage: Comparing account-wide GB used against an account-wide GB cap. */}
        <section className="bg-white p-5 rounded-2xl border border-cream-200 space-y-3 shadow-sm">
          <div className="flex justify-between items-baseline">
            <span className="text-xs text-muted font-bold uppercase tracking-wider">
              Disk Storage
            </span>
            <span className="text-sm font-bold text-ink">
              {parseFloat(usage.storageUsedGb).toFixed(2)}{" "}
              <span className="text-xs text-muted font-light">
                / {limits.storage_gb} GB
              </span>
            </span>
          </div>
          <div className="h-2 w-full bg-cream-100 rounded-full overflow-hidden">
            <div
              className={`h-full rounded-full transition-all duration-500 ${getProgressColor(storagePercent)}`}
              style={{ width: `${storagePercent}%` }}
            />
          </div>
          <p className="text-[10px] text-muted font-light">
            {storagePercent >= 100
              ? "Cloud storage space is full. Upgrade for more GBs."
              : `${remaining(limits.storage_gb, usage.storageUsedGb).toFixed(2)} GB storage remaining.`}
          </p>
        </section>
      </div>
    </div>
  );
}
