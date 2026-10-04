// File Location: frontend/src/pages/client/DownloadPage.jsx

import { useCallback, useEffect, useState } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import { clientsApi } from "../../api/clientsApi";
import { useClientStore } from "../../store/clientStore";
import DownloadAuthStep from "../../components/client/DownloadAuthStep";
import DownloadChooseStep from "../../components/client/DownloadChooseStep";
import DownloadExpired from "../../components/client/DownloadExpired";
import DownloadShell, { useDownloadGallery } from "../../components/client/DownloadShell";
import { blockedMessage, gateNeeds, initialStep, isBlockedCode, jobPagePath } from "../../utils/downloadFlow.js";

/**
 * Full-page gallery download for /g/:username/:slug/download — opened in a new
 * tab by the gallery header's Download icon. It never relies on router state: the
 * gallery's effective download policy comes from the API.
 *
 *   auth    Page 1  "Download Photos": email and/or Download PIN, only when still owed
 *   choose  Page 2  Choose Photos / Download Size / Download To
 *
 * START DOWNLOAD asks the server to prepare the ZIP and moves on to that job's own
 * page (Page 3 preparing, Page 4 ready — see DownloadFilePage). Page 1 is skipped
 * when nothing is owed (no email required, no PIN) or the session already earned
 * access; skipping it is only a convenience: the server checks email and PIN again
 * on every request.
 */
export default function DownloadPage() {
  const { username, slug } = useParams();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  // The server sends a browser that opened a dead file link here.
  const linkExpired = searchParams.get("link") === "expired";

  const gallery = useDownloadGallery(username, slug);
  const { view, galleryToken, sessionKey, studio, gallery: data } = gallery;
  const setDownloadAccess = useClientStore((state) => state.setDownloadAccess);

  const [step, setStep] = useState(null);
  const [access, setAccess] = useState(null);
  const [starting, setStarting] = useState(false);
  const [notice, setNotice] = useState("");

  const policy = data?.download_policy;
  const hasPin = Boolean(data?.has_download_pin);

  // The first page is decided once, when the policy first arrives (a remembered
  // token from earlier in this session already counts as access).
  useEffect(() => {
    if (view.status !== "ready" || step !== null) return;
    const remembered = useClientStore.getState().getDownloadAccess(sessionKey);
    setAccess(remembered);
    setStep(initialStep({ needsGate: gateNeeds({ policy, hasPin, access: remembered }).needsGate }));
  }, [view.status, step, policy, hasPin, sessionKey]);

  const needs = gateNeeds({ policy, hasPin, access });

  const goToPage2 = (grantedAccess) => {
    setAccess(grantedAccess);
    setNotice("");
    setStep("choose");
  };

  // The server said the session token is no good any more: ask again on Page 1.
  const sessionExpired = useCallback(() => {
    setDownloadAccess(sessionKey, null);
    setAccess(null);
    setNotice("Your download session expired. Please confirm your details again.");
    setStep("auth");
  }, [sessionKey, setDownloadAccess]);

  const startDownload = async (choice) => {
    if (starting) return;
    setStarting(true);
    setNotice("");
    try {
      const job = await clientsApi.prepareGalleryDownload(username, slug, {
        downloadToken: access?.token, token: galleryToken, ...choice,
      });
      navigate(jobPagePath(username, slug, job.job_id, job.link_token), { replace: true, state: { justPrepared: true } });
    } catch (err) {
      setStarting(false);
      if (err?.code === "download_access_expired") sessionExpired();
      else if (err?.status === 429) setNotice("Too many attempts. Please wait a minute and try again.");
      else if (isBlockedCode(err?.code)) setNotice(blockedMessage(err.code, studio, err.message));
      else setNotice(err?.message || "We couldn't start preparing your photos. Please try again.");
    }
  };

  // Nothing to ask once the total download limit is hit.
  const limitBlocked = Boolean(policy?.limit_reached);
  const showSteps = !linkExpired && !limitBlocked;

  return (
    <DownloadShell username={username} slug={slug} gallery={gallery} showBack={!linkExpired}>
      {linkExpired && <DownloadExpired username={username} slug={slug} />}

      {!linkExpired && limitBlocked && (
        <p role="alert" className="bg-red-50 px-3 py-3 text-center text-sm text-red-700">
          Download limit reached. Contact {studio}.
        </p>
      )}

      {showSteps && step === "auth" && (
        <DownloadAuthStep
          username={username}
          slug={slug}
          galleryToken={galleryToken}
          studio={studio}
          needsEmail={needs.needsEmail}
          needsPin={needs.needsPin}
          notice={notice}
          onGranted={goToPage2}
        />
      )}

      {showSteps && step === "choose" && (
        <DownloadChooseStep
          policy={policy}
          photoSets={data.photo_sets || []}
          photoCount={data.photos_count || 0}
          studio={studio}
          notice={notice}
          starting={starting}
          onStart={startDownload}
        />
      )}
    </DownloadShell>
  );
}
