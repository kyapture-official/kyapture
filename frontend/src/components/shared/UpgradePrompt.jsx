// File Location: frontend/src/components/shared/UpgradePrompt.jsx
import { useNavigate } from "react-router-dom";
import { featureLabel, requiredPlan, usePlans } from "../../hooks/usePlans";

/**
 * The locked-feature state for plan-gated features (Branding, Watermark).
 * `feature` is the entitlement key; the title and the plan it names are read
 * from the plans API.
 * Shown instead of — or beside — the controls a Free plan can't use, with a
 * "View Plans" call to action that opens the existing Billing page. It is a
 * courtesy only: the API refuses the same writes for an unentitled account.
 */
export default function UpgradePrompt({ feature, message, className = "" }) {
  const navigate = useNavigate();
  // Plan name and feature label come from the plans API (owner-editable data),
  // never from copy written here.
  const { plans } = usePlans();
  const plan = requiredPlan(plans, feature);
  const label = featureLabel(plans, feature);
  const title = label ? `${label} is ${plan ? `a ${plan.name}` : "a paid"} feature` : "This is a paid feature";
  const availability = plan ? `Available on the ${plan.name} plan and above.` : "Available on paid plans.";
  return (
    <div
      role="note"
      className={`flex items-start gap-3 rounded-xl border border-amber-200 bg-amber-50 p-4 text-left ${className}`}
    >
      <svg
        className="mt-0.5 h-5 w-5 flex-shrink-0 text-amber-600"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.8"
        viewBox="0 0 24 24"
        aria-hidden="true"
      >
        <path
          strokeLinecap="round"
          strokeLinejoin="round"
          d="M16.5 10.5V6.75a4.5 4.5 0 10-9 0v3.75m-.75 11.25h10.5a2.25 2.25 0 002.25-2.25v-6.75a2.25 2.25 0 00-2.25-2.25H6.75a2.25 2.25 0 00-2.25 2.25v6.75a2.25 2.25 0 002.25 2.25z"
        />
      </svg>
      <div className="min-w-0 flex-1">
        <p className="text-sm font-semibold text-amber-900">{title}</p>
        <p className="mt-0.5 text-xs leading-relaxed text-amber-800">{message} {availability}</p>
        <button
          type="button"
          onClick={() => navigate("/dashboard/billing")}
          className="mt-3 inline-flex cursor-pointer items-center rounded-lg bg-ink px-4 py-2 text-xs font-medium text-white transition-colors hover:bg-ink/85 focus:outline-none focus-visible:ring-2 focus-visible:ring-ink focus-visible:ring-offset-2"
        >
          View Plans
        </button>
      </div>
    </div>
  );
}
