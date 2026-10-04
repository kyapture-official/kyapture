import { useId, useMemo, useState } from "react";
import {
  allSetIds, defaultSize, isAllSelected, photoLabel, scopeModel, selectionRequest, sizeOptions,
  toggleAll, toggleSet,
} from "../../utils/downloadFlow.js";
import { pageButton } from "./DownloadAuthStep";

const sectionHeading = "mb-4 font-serif text-xl text-ink";
const checkClass = "h-5 w-5 shrink-0 cursor-pointer accent-ink";

/**
 * Download page 2 — "Choose Photos", "Choose Download Size:", "Download To:".
 * Everything shown comes from the server's effective policy: only the sets
 * enabled in Download > Advanced, only the enabled sizes. The only destination is
 * this device. START DOWNLOAD hands the choice up as { resolution, setId? | setIds? }.
 */
export default function DownloadChooseStep({ policy, photoSets, photoCount, studio, notice = "", onStart }) {
  const uid = useId();
  const model = useMemo(() => scopeModel({ policy, photoSets, photoCount }), [policy, photoSets, photoCount]);
  const sizes = useMemo(() => sizeOptions(policy), [policy]);
  const [selected, setSelected] = useState(() => allSetIds(model));
  const [resolution, setResolution] = useState(() => defaultSize(sizes));

  const allSelected = isAllSelected(model, selected);
  const request = selectionRequest(model, selected);
  const limitReached = Boolean(policy?.limit_reached);
  const noSets = model.sets.length === 0;

  const handleStart = (event) => {
    event.preventDefault();
    if (!request || limitReached) return;
    onStart({ resolution, ...request });
  };

  return (
    <form onSubmit={handleStart} noValidate className="space-y-10">
      {notice && <p role="alert" className="bg-red-50 px-3 py-2 text-sm text-red-700">{notice}</p>}

      <fieldset>
        <legend className={sectionHeading}>Choose Photos</legend>
        <div className="space-y-4">
          <label className="flex cursor-pointer items-center gap-3 text-[15px] text-ink">
            <input
              type="checkbox"
              checked={allSelected}
              disabled={noSets}
              onChange={() => setSelected(toggleAll(model, selected))}
              className={checkClass}
            />
            <span className="flex-1">All photos</span>
            <span className="text-sm text-muted">{photoLabel(model.allCount)}</span>
          </label>
          {model.sets.map((set) => (
            <label key={set.id} className="flex cursor-pointer items-center gap-3 text-[15px] text-ink">
              <input
                type="checkbox"
                checked={selected.includes(set.id)}
                onChange={() => setSelected(toggleSet(selected, set.id))}
                className={checkClass}
              />
              <span className="min-w-0 flex-1 truncate">{set.name}</span>
              <span className="text-sm text-muted">{photoLabel(set.photo_count)}</span>
            </label>
          ))}
        </div>
        {!request && <p role="alert" className="mt-3 text-sm text-red-600">Choose at least one set of photos.</p>}
      </fieldset>

      <fieldset>
        <legend className={sectionHeading}>Choose Download Size:</legend>
        <div className="space-y-4">
          {sizes.map((option) => (
            <label key={option.value} className="flex cursor-pointer items-center gap-3 text-[15px] text-ink">
              <input
                type="radio"
                name={`${uid}-size`}
                value={option.value}
                checked={resolution === option.value}
                onChange={() => setResolution(option.value)}
                className={checkClass}
              />
              {option.label}
            </label>
          ))}
        </div>
      </fieldset>

      <div>
        <p className={sectionHeading}>Download To:</p>
        <div className="flex items-center justify-center gap-3 border border-cream-300 bg-white px-4 py-4 text-[15px] text-ink">
          <svg className="h-4 w-4 shrink-0 text-ink" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" /></svg>
          <svg className="h-5 w-5 shrink-0 text-ink" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M4 6a2 2 0 012-2h12a2 2 0 012 2v9H4V6zm-2 11h20v1a2 2 0 01-2 2H4a2 2 0 01-2-2v-1z" /></svg>
          Save to My Device
        </div>
      </div>

      {limitReached && (
        <p role="alert" className="bg-red-50 px-3 py-2 text-sm text-red-700">
          Download limit reached. Contact {studio || "the photographer"}.
        </p>
      )}

      <div className="flex justify-center">
        <button type="submit" disabled={!request || limitReached} className={pageButton}>Start Download</button>
      </div>
    </form>
  );
}
