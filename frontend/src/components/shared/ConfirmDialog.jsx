// File Location: frontend/src/components/shared/ConfirmDialog.jsx
import Modal from "../ui/Modal";

/**
 * A real confirmation step before something irreversible. Nothing happens until
 * the confirm button is pressed; while `busy` the buttons are disabled so a
 * second click can't fire the action twice.
 */
export default function ConfirmDialog({
  open,
  title,
  children,
  confirmLabel = "Delete permanently",
  cancelLabel = "Cancel",
  busy = false,
  danger = true,
  onConfirm,
  onCancel,
}) {
  return (
    <Modal open={open} onClose={busy ? () => {} : onCancel} title={title} size="sm">
      <div className="space-y-5" role="alertdialog" aria-label={title}>
        <div className="text-sm leading-relaxed text-muted">{children}</div>
        <div className="flex justify-end gap-2">
          <button
            type="button"
            onClick={onCancel}
            disabled={busy}
            className="cursor-pointer rounded-lg px-4 py-2.5 text-sm text-muted transition hover:text-ink disabled:opacity-50"
          >
            {cancelLabel}
          </button>
          <button
            type="button"
            onClick={onConfirm}
            disabled={busy}
            className={`cursor-pointer rounded-lg px-5 py-2.5 text-sm font-medium text-white transition disabled:cursor-not-allowed disabled:opacity-60 ${
              danger ? "bg-red-600 hover:bg-red-700" : "bg-ink hover:bg-ink/85"
            }`}
          >
            {busy ? "Working…" : confirmLabel}
          </button>
        </div>
      </div>
    </Modal>
  );
}
