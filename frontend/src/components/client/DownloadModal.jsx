// File Location: frontend/src/components/client/DownloadModal.jsx
import { useState } from "react";
import { useToast } from "../ui/Toast";
import { useClientStore } from "../../store/clientStore";
import { gateNeeds, initialStep, photoGateIntro } from "../../utils/downloadFlow.js";
import ClientDialog from "./ClientDialog";
import DownloadAuthStep from "./DownloadAuthStep";
import PhotoDownloadChoose from "./PhotoDownloadChoose";

/**
 * The single-photo "Download photo" dialog, opened by an explicit click on a
 * photo tile's download icon or in the lightbox — never on gallery entry.
 *
 *   step 1 (only when this visitor still owes something): the same email / PIN
 *          fields as the gallery download's Page 1, then NEXT
 *   step 2: DOWNLOAD PHOTO — size, destination, remember, button. The photo then
 *          downloads directly (no ZIP, no preparing page).
 *
 * A centered box on desktop, a full-width bottom sheet on phones (ClientDialog).
 * Downloading a whole gallery or set is a separate full page.
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
    <ClientDialog open onClose={onClose} galleryTitle={galleryTitle} photographerName={photographerName} heading="Download photo" variant="plain">
      <PhotoDownloadFlow
        // Re-mount per photo so step/size/error state never leaks from one download into the next.
        key={photo.id}
        username={username}
        slug={slug}
        galleryToken={galleryToken}
        studio={photographerName}
        hasDownloadPin={hasDownloadPin}
        policy={downloadPolicy}
        photo={photo}
        onClose={onClose}
      />
    </ClientDialog>
  );
}

function PhotoDownloadFlow({ username, slug, galleryToken, studio, hasDownloadPin, policy, photo, onClose }) {
  const toast = useToast();
  const sessionKey = `${username}:${slug}`;
  const stored = useClientStore((state) => state.downloadAccess[sessionKey]);
  const access = stored?.token && stored.expiresAt > Date.now() ? stored : null;
  const needs = gateNeeds({ policy, hasPin: hasDownloadPin, access });
  const [step, setStep] = useState(() => initialStep(needs));
  const [notice, setNotice] = useState("");

  if (step === "auth" && needs.needsGate) {
    return (
      <DownloadAuthStep
        username={username}
        slug={slug}
        galleryToken={galleryToken}
        studio={studio}
        needsEmail={needs.needsEmail}
        needsPin={needs.needsPin}
        notice={notice}
        heading="Download Photo"
        intro={photoGateIntro({ ...needs, studio })}
        onGranted={() => { setNotice(""); setStep("choose"); }}
      />
    );
  }

  return (
    <PhotoDownloadChoose
      username={username}
      slug={slug}
      galleryToken={galleryToken}
      policy={policy}
      studio={studio}
      photo={photo}
      access={access}
      onNeedAccess={(message) => { setNotice(message); setStep("auth"); }}
      onDone={() => { toast("Your download has started", "success"); onClose(); }}
    />
  );
}
