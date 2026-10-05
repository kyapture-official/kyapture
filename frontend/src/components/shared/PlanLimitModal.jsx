// File Location: frontend/src/components/shared/PlanLimitModal.jsx
import { useNavigate } from "react-router-dom";
import Modal from "../ui/Modal";

/**
 * "Your plan's limit was reached" dialog, shared by every plan-limit refusal
 * (collections now; video minutes reuse it). It only presents what the server
 * refused with: `children` carries the backend's own message and figures, and
 * "View Plans" goes to Billing, where the plan table is shown.
 */
export default function PlanLimitModal({ open, title, children, onClose }) {
  const navigate = useNavigate();
  return (
    <Modal open={open} onClose={onClose} title={title} size="sm">
      <div className="space-y-5" role="alertdialog" aria-label={title}>
        <div className="text-sm leading-relaxed text-muted">{children}</div>
        <div className="flex justify-end gap-2">
          <button
            type="button"
            onClick={onClose}
            className="cursor-pointer rounded-lg px-4 py-2.5 text-sm text-muted transition hover:text-ink"
          >
            Close
          </button>
          <button
            type="button"
            onClick={() => {
              onClose();
              navigate("/dashboard/billing");
            }}
            className="cursor-pointer rounded-lg bg-brand-green-600 px-5 py-2.5 text-sm font-medium text-white transition hover:bg-brand-green-700"
          >
            View Plans
          </button>
        </div>
      </div>
    </Modal>
  );
}
