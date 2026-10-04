// File Location: frontend/src/components/client/DownloadModal.jsx
import ClientDialog from "./ClientDialog";
import DownloadForm from "./DownloadForm";

/**
 * The client "Download" dialog: ONE box. Email and/or the download PIN appear at
 * the top only when this visitor still has to give them, followed by size choice
 * and a single Download button. Opened by an explicit Download click from the
 * gallery toolbar, a photo tile, or the lightbox — never on gallery entry. A
 * centered card on desktop, a full-width bottom sheet on phones (see ClientDialog).
 */
export default function DownloadModal({
  open,
  onClose,
  username,
  slug,
  galleryToken,
  galleryTitle,
  photographerName,
  hasDownloadPin,
  downloadPolicy,
  target,
  photoSets,
  photoCount,
}) {
  if (!open || !target) return null;

  return (
    <ClientDialog
      open={open}
      onClose={onClose}
      galleryTitle={galleryTitle}
      photographerName={photographerName}
      heading={target.type === "photo" ? "Download photo" : "Download"}
    >
      <DownloadForm
        // Re-mount per target so scope/size/error state never leaks from one
        // download into the next.
        key={target.type === "photo" ? target.photo?.id : `gallery:${target.setId || ""}`}
        username={username}
        slug={slug}
        galleryToken={galleryToken}
        hasDownloadPin={hasDownloadPin}
        downloadPolicy={downloadPolicy}
        target={target}
        photoSets={photoSets}
        photoCount={photoCount}
        onCancel={onClose}
      />
    </ClientDialog>
  );
}
