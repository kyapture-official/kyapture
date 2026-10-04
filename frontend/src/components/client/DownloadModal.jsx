// File Location: frontend/src/components/client/DownloadModal.jsx
import ClientDialog from "./ClientDialog";
import DownloadForm from "./DownloadForm";

/**
 * The single-photo "Download" dialog: ONE box with email and/or the download PIN
 * at the top only when this visitor still has to give them, then size choice and
 * a Download button. Opened by an explicit Download click on a photo tile or in
 * the lightbox — never on gallery entry. A centered card on desktop, a
 * full-width bottom sheet on phones (see ClientDialog). Downloading a whole
 * gallery or set is a separate full page (/g/{user}/{slug}/download).
 */
export default function DownloadModal({
  photo,
  onClose,
  username,
  slug,
  galleryToken,
  galleryTitle,
  photographerName,
  hasDownloadPin,
  downloadPolicy,
}) {
  if (!photo) return null;

  return (
    <ClientDialog
      open
      onClose={onClose}
      galleryTitle={galleryTitle}
      photographerName={photographerName}
      heading="Download photo"
    >
      <DownloadForm
        // Re-mount per photo so size/error state never leaks from one download into the next.
        key={photo.id}
        username={username}
        slug={slug}
        galleryToken={galleryToken}
        hasDownloadPin={hasDownloadPin}
        downloadPolicy={downloadPolicy}
        photo={photo}
        onCancel={onClose}
      />
    </ClientDialog>
  );
}
