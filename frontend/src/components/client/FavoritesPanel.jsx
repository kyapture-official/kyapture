import { useCallback, useEffect, useRef, useState } from "react";
import { Heart, Pencil, Plus, Trash2, X } from "lucide-react";
import { clientsApi } from "../../api/clientsApi";
import ClientDialog from "./ClientDialog";

const fmt = (value) =>
  value ? new Date(value).toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" }) : "—";

const iconButton =
  "rounded p-2 text-muted transition hover:bg-cream-100 hover:text-ink focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-green-500";

/**
 * The visitor's OWN favorite lists for this gallery (Pixieset-style): each list
 * with a thumbnail, name, photo count and created / updated dates; create,
 * rename and delete lists; open one to see (and remove) its photos; sort
 * newest / oldest. The server only ever returns the lists that belong to this
 * browser's identity.
 */
export default function FavoritesPanel({
  open,
  onClose,
  username,
  slug,
  identity,
  galleryTitle,
  photographerName,
  profile,
  onChanged,
}) {
  const [sort, setSort] = useState("newest");
  const [lists, setLists] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [creating, setCreating] = useState(false);
  const [newName, setNewName] = useState("");
  const [renaming, setRenaming] = useState(null); // { id, value }
  const [confirmDelete, setConfirmDelete] = useState(null);
  const [busy, setBusy] = useState(false);

  const [openList, setOpenList] = useState(null); // list summary
  const [photos, setPhotos] = useState([]);
  const [photosNext, setPhotosNext] = useState(null);
  const [photosLoading, setPhotosLoading] = useState(false);
  const identityRef = useRef(identity);
  identityRef.current = identity;

  const loadLists = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const data = await clientsApi.getFavoriteLists(username, slug, identityRef.current, { sort });
      setLists(data.results || []);
    } catch (err) {
      setError(err?.message || "We couldn't load your favorites.");
    } finally {
      setLoading(false);
    }
  }, [username, slug, sort]);

  const loadPhotos = useCallback(
    async (list, page = 1) => {
      setPhotosLoading(true);
      setError("");
      try {
        const data = await clientsApi.getFavoriteListPhotos(username, slug, list.id, identityRef.current, { sort, page });
        setPhotos((previous) => (page === 1 ? data.results || [] : [...previous, ...(data.results || [])]));
        setPhotosNext(data.next ? page + 1 : null);
        if (data.list) setOpenList(data.list);
      } catch (err) {
        setError(err?.message || "We couldn't load this list.");
      } finally {
        setPhotosLoading(false);
      }
    },
    [username, slug, sort],
  );

  useEffect(() => {
    if (!open) return;
    if (openList) loadPhotos(openList, 1);
    else loadLists();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, sort, openList?.id]);

  const run = async (action, successMessage) => {
    if (busy) return;
    setBusy(true);
    setError("");
    setNotice("");
    try {
      await action();
      if (successMessage) setNotice(successMessage);
      onChanged?.();
      return true;
    } catch (err) {
      setError(err?.message || "Something went wrong. Please try again.");
      return false;
    } finally {
      setBusy(false);
    }
  };

  const createList = async (event) => {
    event.preventDefault();
    const name = newName.trim();
    if (!name) {
      setError("Give your list a name.");
      return;
    }
    const ok = await run(
      () => clientsApi.createFavoriteList(username, slug, name, identity, { email: profile?.email, visitorName: profile?.name }),
      "List created.",
    );
    if (ok) {
      setCreating(false);
      setNewName("");
      loadLists();
    }
  };

  const saveRename = async (event) => {
    event.preventDefault();
    const name = renaming.value.trim();
    if (!name) {
      setError("Give your list a name.");
      return;
    }
    const ok = await run(() => clientsApi.renameFavoriteList(username, slug, renaming.id, name, identity), "List renamed.");
    if (ok) {
      if (openList?.id === renaming.id) setOpenList((current) => ({ ...current, name }));
      setRenaming(null);
      loadLists();
    }
  };

  const removeList = async (list) => {
    const ok = await run(() => clientsApi.deleteFavoriteList(username, slug, list.id, identity), "List deleted.");
    if (ok) {
      setConfirmDelete(null);
      setOpenList(null);
      loadLists();
    }
  };

  const removePhoto = async (photo) => {
    const ok = await run(
      () => clientsApi.removeFavorite(username, slug, photo.id, identity, { listId: openList.id }),
      "Removed from your list.",
    );
    if (ok) {
      setPhotos((previous) => previous.filter((item) => item.id !== photo.id));
      setOpenList((current) => ({ ...current, photo_count: Math.max(0, (current.photo_count || 1) - 1) }));
    }
  };

  const sortSelect = (
    <label className="flex items-center gap-2 text-xs text-muted">
      Sort
      <select value={sort} onChange={(event) => setSort(event.target.value)} className="rounded border border-cream-300 bg-white px-2 py-1 text-xs text-ink" aria-label="Sort favorites">
        <option value="newest">Newest first</option>
        <option value="oldest">Oldest first</option>
      </select>
    </label>
  );

  const feedback = (
    <>
      {error && <p role="alert" className="rounded-lg bg-red-50 px-3 py-2 text-xs text-red-700">{error}</p>}
      {notice && !error && <p role="status" className="rounded-lg bg-cream-100 px-3 py-2 text-xs text-muted">{notice}</p>}
    </>
  );

  const goBack = () => {
    setOpenList(null);
    setPhotos([]);
    setNotice("");
    setError("");
  };

  return (
    <ClientDialog open={open} onClose={onClose} galleryTitle={galleryTitle} photographerName={photographerName} heading="Favorites" size="lg">
      {openList ? (
        // ── one list ────────────────────────────────────────────────────────
        <div className="space-y-4">
          <div className="flex items-center justify-between gap-3">
            <button type="button" onClick={goBack} className="text-xs uppercase tracking-widest text-muted hover:text-ink">← All lists</button>
            {sortSelect}
          </div>
          {renaming?.id === openList.id ? (
            <form onSubmit={saveRename} className="flex gap-2">
              <input autoFocus value={renaming.value} maxLength={80} onChange={(event) => setRenaming({ ...renaming, value: event.target.value })} className="min-w-0 flex-1 rounded-lg border border-cream-300 bg-white px-3 py-2 text-sm text-ink" aria-label="List name" />
              <button type="submit" disabled={busy} className="rounded-lg bg-ink px-4 text-xs uppercase tracking-widest text-white disabled:opacity-60">Save</button>
              <button type="button" onClick={() => setRenaming(null)} className="px-2 text-xs text-muted">Cancel</button>
            </form>
          ) : (
            <div className="flex items-center justify-between gap-3">
              <div className="min-w-0">
                <h4 className="truncate font-serif text-xl text-ink">{openList.name}</h4>
                <p className="text-xs text-muted">{openList.photo_count ?? photos.length} {openList.photo_count === 1 ? "photo" : "photos"}</p>
              </div>
              <div className="flex shrink-0">
                <button type="button" className={iconButton} onClick={() => setRenaming({ id: openList.id, value: openList.name })} aria-label="Rename list"><Pencil className="h-4 w-4" /></button>
                <button type="button" className={iconButton} onClick={() => setConfirmDelete(openList.id)} aria-label="Delete list"><Trash2 className="h-4 w-4" /></button>
              </div>
            </div>
          )}
          {confirmDelete === openList.id && (
            <div className="flex items-center justify-between gap-3 rounded-lg bg-red-50 px-3 py-2 text-xs text-red-700" role="alertdialog" aria-label="Confirm delete">
              <span>Delete &ldquo;{openList.name}&rdquo;? The photos stay in the gallery.</span>
              <span className="flex shrink-0 gap-2">
                <button type="button" onClick={() => removeList(openList)} disabled={busy} className="font-semibold underline">Delete</button>
                <button type="button" onClick={() => setConfirmDelete(null)} className="underline">Keep</button>
              </span>
            </div>
          )}
          {feedback}
          {photosLoading && photos.length === 0 ? (
            <div className="grid grid-cols-3 gap-2" role="status" aria-label="Loading photos">
              {Array.from({ length: 6 }, (_, index) => <div key={index} className="aspect-square animate-pulse rounded bg-cream-100" />)}
            </div>
          ) : photos.length === 0 ? (
            <p className="py-8 text-center text-sm text-muted">No photos in this list yet. Tap the heart on a photo to add it.</p>
          ) : (
            <ul className="grid grid-cols-3 gap-2 sm:grid-cols-4">
              {photos.map((photo) => (
                <li key={photo.id} className="group relative aspect-square overflow-hidden rounded bg-cream-100">
                  <img src={photo.thumbnail_url || photo.display_url} alt={photo.original_name || "Favorite photo"} loading="lazy" className="h-full w-full object-cover" />
                  <button type="button" onClick={() => removePhoto(photo)} disabled={busy} className="absolute right-1 top-1 rounded-full bg-black/55 p-1 text-white opacity-100 transition hover:bg-black/75 sm:opacity-0 sm:group-hover:opacity-100" aria-label={`Remove ${photo.original_name || "photo"} from this list`}>
                    <X className="h-3.5 w-3.5" />
                  </button>
                </li>
              ))}
            </ul>
          )}
          {photosNext && (
            <div className="flex justify-center">
              <button type="button" onClick={() => loadPhotos(openList, photosNext)} disabled={photosLoading} className="rounded-full border border-ink/30 px-5 py-2 text-xs uppercase tracking-widest text-ink hover:bg-ink/5 disabled:opacity-60">{photosLoading ? "Loading…" : "Load more"}</button>
            </div>
          )}
        </div>
      ) : (
        // ── all lists ───────────────────────────────────────────────────────
        <div className="space-y-4">
          <div className="flex items-center justify-between gap-3">
            <h4 className="font-serif text-xl uppercase tracking-[0.14em] text-ink">My Favorites</h4>
            {sortSelect}
          </div>
          {feedback}
          {creating ? (
            <form onSubmit={createList} className="flex gap-2">
              <input autoFocus value={newName} maxLength={80} onChange={(event) => setNewName(event.target.value)} placeholder="List name" className="min-w-0 flex-1 rounded-lg border border-cream-300 bg-white px-3 py-2 text-sm text-ink" aria-label="New list name" />
              <button type="submit" disabled={busy} className="rounded-lg bg-ink px-4 text-xs uppercase tracking-widest text-white disabled:opacity-60">Create</button>
              <button type="button" onClick={() => { setCreating(false); setNewName(""); }} className="px-2 text-xs text-muted">Cancel</button>
            </form>
          ) : (
            <button type="button" onClick={() => { setCreating(true); setError(""); }} className="flex items-center gap-2 text-sm text-brand-green-700 hover:underline">
              <Plus className="h-4 w-4" /> New Favorite List
            </button>
          )}

          {loading ? (
            <div className="space-y-2" role="status" aria-label="Loading favorites">
              {Array.from({ length: 2 }, (_, index) => <div key={index} className="h-16 animate-pulse rounded-lg bg-cream-100" />)}
            </div>
          ) : lists.length === 0 ? (
            <div className="py-10 text-center">
              <Heart className="mx-auto mb-3 h-7 w-7 text-muted" />
              <p className="text-sm text-muted">No favorites yet. Tap the heart on any photo to start your list.</p>
            </div>
          ) : (
            <ul className="divide-y divide-cream-200 rounded-lg border border-cream-200 bg-white">
              {lists.map((list) => (
                <li key={list.id} className="flex items-center gap-3 px-3 py-3">
                  <button type="button" onClick={() => { setOpenList(list); setNotice(""); setError(""); }} className="flex min-w-0 flex-1 items-center gap-3 text-left" aria-label={`Open ${list.name}`}>
                    <span className="h-14 w-14 shrink-0 overflow-hidden rounded bg-cream-100">
                      {list.thumbnail_url ? <img src={list.thumbnail_url} alt="" className="h-full w-full object-cover" /> : <Heart className="m-auto mt-4 h-5 w-5 text-muted" />}
                    </span>
                    <span className="min-w-0">
                      <span className="block truncate text-sm font-medium text-ink">{list.name}</span>
                      <span className="block text-xs text-muted">{list.photo_count} {list.photo_count === 1 ? "photo" : "photos"}</span>
                      <span className="block text-[11px] text-muted">Created {fmt(list.created_at)} · Updated {fmt(list.updated_at)}</span>
                    </span>
                  </button>
                  <span className="flex shrink-0">
                    <button type="button" className={iconButton} onClick={() => { setOpenList(list); setRenaming({ id: list.id, value: list.name }); }} aria-label={`Rename ${list.name}`}><Pencil className="h-4 w-4" /></button>
                    <button type="button" className={iconButton} onClick={() => { setOpenList(list); setConfirmDelete(list.id); }} aria-label={`Delete ${list.name}`}><Trash2 className="h-4 w-4" /></button>
                  </span>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </ClientDialog>
  );
}
