import { Link } from "react-router-dom";
import { pageButtonClass } from "./DownloadShell";

/**
 * What a download link shows once its 7 days are over (or the files were
 * purged, or the link is unknown): a plain sentence and a way back, never a raw
 * error page.
 */
export default function DownloadExpired({ username, slug }) {
  return (
    <div className="space-y-8 text-center" role="alert">
      <h2 className="font-serif text-xl font-bold uppercase tracking-[0.16em] text-ink">Download expired</h2>
      <p className="text-[15px] leading-8 text-muted">
        This download has expired. Visit the gallery to request a new download.
      </p>
      <div className="flex justify-center">
        <Link to={`/g/${username}/${slug}`} className={pageButtonClass}>Visit gallery</Link>
      </div>
    </div>
  );
}
