import { useEffect, useRef, useState } from "react";
import { NavLink, useNavigate } from "react-router-dom";
import { photosApi } from "../../api/photosApi";
import Modal from "../ui/Modal";
import { useToast } from "../ui/Toast";
import {
  Images,
  Brush,
  Settings,
  Rss,
  ChevronLeft,
  Camera,
  Plus,
  GripVertical,
  MoreHorizontal,
} from "lucide-react";

const NAV_ITEMS = [
  { to: "", end: true, label: "Photos", Icon: Images },
  { to: "design", label: "Design", Icon: Brush },
  { to: "settings", label: "Settings", Icon: Settings },
  { to: "activities", label: "Activities", Icon: Rss },
];

const resolvePath = (basePath, to) => (to ? `${basePath}/${to}` : basePath);

function RailTooltip({ children }) {
  return (
    <span
      aria-hidden="true"
      className="pointer-events-none absolute bottom-full left-1/2 mb-2 -translate-x-1/2 whitespace-nowrap rounded-md bg-slate-900 px-2.5 py-1 text-xs font-medium text-white opacity-0 shadow-lg transition-opacity duration-150 group-hover:opacity-100 group-focus-visible:opacity-100 z-50"
    >
      <span className="absolute -bottom-1 left-1/2 h-2 w-2 -translate-x-1/2 rotate-45 bg-slate-900" />
      {children}
    </span>
  );
}

function CollectionCover({ gallery }) {
  const coverUrl = gallery?.cover_url ?? null;
  const title = gallery?.title || "Collection";
  const [failed, setFailed] = useState(false);

  useEffect(() => setFailed(false), [coverUrl]);

  if (coverUrl && !failed) {
    return (
      <img
        src={coverUrl}
        alt={`${title} cover`}
        onError={() => setFailed(true)}
        className="h-[180px] w-full object-cover"
      />
    );
  }

  return (
    <div
      className="flex h-[180px] w-full items-center justify-center bg-cream-100"
      style={{ backgroundColor: gallery?.branding_color || "#0D9488" }}
    >
      <Camera className="h-8 w-8 text-white/70" aria-hidden="true" />
    </div>
  );
}

export default function GallerySecondarySidebar({
  basePath,
  gallery,
  slug,
  sets = [],
  setsLoading = false,
  setSets,
  refreshSets,
  activeSetId,
  onSetSelect,
}) {
  const navigate = useNavigate();
  const toast = useToast();
  const [createOpen, setCreateOpen] = useState(false);
  const [newSetName, setNewSetName] = useState("");
  const [newSetDescription, setNewSetDescription] = useState("");
  const [createError, setCreateError] = useState("");
  const [creating, setCreating] = useState(false);
  const [openMenuSetId, setOpenMenuSetId] = useState(null);
  const [editingSet, setEditingSet] = useState(null);
  const [editName, setEditName] = useState("");
  const [editDescription, setEditDescription] = useState("");
  const [editError, setEditError] = useState("");
  const [savingEdit, setSavingEdit] = useState(false);
  const [deletingSetId, setDeletingSetId] = useState(null);
  const [draggedSetId, setDraggedSetId] = useState(null);
  const [dragOverSetId, setDragOverSetId] = useState(null);
  const reorderInFlightRef = useRef(false);

  const getErrorMessage = (error, fallback) => {
    const data = error?.response?.data;
    if (typeof data === "string") {
      return /<[^>]+>/.test(data) ? fallback : data;
    }
    return (
      data?.error ||
      data?.detail ||
      data?.name?.[0] ||
      data?.description?.[0] ||
      error?.message ||
      fallback
    );
  };

  const openCreateModal = () => {
    setNewSetName("");
    setNewSetDescription("");
    setCreateError("");
    setCreateOpen(true);
  };

  const closeCreateModal = () => {
    if (!creating) setCreateOpen(false);
  };

  const handleCreateSet = async (event) => {
    event.preventDefault();
    const name = newSetName.trim();
    const description = newSetDescription;
    if (!name) {
      setCreateError("Photo set name is required.");
      return;
    }
    if (description.length > 500) {
      setCreateError("Description must be 500 characters or fewer.");
      return;
    }
    if (creating) return;

    setCreating(true);
    setCreateError("");
    const loadingToastId = toast("Creating photo set...", "loading");
    try {
      const created = await photosApi.createSet(slug, name, description);
      await refreshSets();
      onSetSelect?.(created.id);
      toast.dismiss(loadingToastId);
      toast("Photo set created.", "success");
      setCreateOpen(false);
    } catch (error) {
      toast.dismiss(loadingToastId);
      const message = getErrorMessage(error, "Failed to create photo set.");
      setCreateError(message);
      toast(message, "error");
    } finally {
      setCreating(false);
    }
  };

  const openEditModal = (set, mode) => {
    setOpenMenuSetId(null);
    setEditingSet({ ...set, mode });
    setEditName(set.name || "");
    setEditDescription(set.description || "");
    setEditError("");
  };

  const closeEditModal = () => {
    if (!savingEdit) setEditingSet(null);
  };

  const handleSaveEdit = async (event) => {
    event.preventDefault();
    if (!editingSet || savingEdit) return;

    const name = editName.trim();
    if (!name) {
      setEditError("Photo set name is required.");
      return;
    }
    if (editingSet.mode === "description" && editDescription.length > 500) {
      setEditError("Description must be 500 characters or fewer.");
      return;
    }

    setSavingEdit(true);
    setEditError("");
    const loadingToastId = toast("Saving photo set...", "loading");
    try {
      const fields = editingSet.mode === "description"
        ? { name, description: editDescription }
        : { name };
      await photosApi.updateSet(slug, editingSet.id, fields);
      await refreshSets();
      toast.dismiss(loadingToastId);
      toast("Photo set updated.", "success");
      setEditingSet(null);
    } catch (error) {
      toast.dismiss(loadingToastId);
      const message = getErrorMessage(error, "Failed to update photo set.");
      setEditError(message);
      toast(message, "error");
    } finally {
      setSavingEdit(false);
    }
  };

  const handleDeleteSet = async (set) => {
    setOpenMenuSetId(null);
    if (deletingSetId || !window.confirm(`Delete "${set.name}"? Photos will move to the first remaining set.`)) {
      return;
    }

    setDeletingSetId(set.id);
    const loadingToastId = toast("Deleting photo set...", "loading");
    try {
      await photosApi.deleteSet(slug, set.id);
      const refreshedSets = await refreshSets();
      if (String(activeSetId) === String(set.id)) {
        onSetSelect?.(refreshedSets[0]?.id ?? null);
      }
      toast.dismiss(loadingToastId);
      toast("Photo set deleted.", "success");
    } catch (error) {
      toast.dismiss(loadingToastId);
      toast(getErrorMessage(error, "Failed to delete photo set."), "error");
    } finally {
      setDeletingSetId(null);
    }
  };

  const handleDragStart = (event, setId) => {
    if (reorderInFlightRef.current) {
      event.preventDefault();
      return;
    }
    setDraggedSetId(setId);
    event.dataTransfer.effectAllowed = "move";
    event.dataTransfer.setData("text/plain", String(setId));
  };

  const handleDragOver = (event, setId) => {
    if (!draggedSetId || reorderInFlightRef.current) return;
    event.preventDefault();
    event.dataTransfer.dropEffect = "move";
    setDragOverSetId(setId);
  };

  const handleDrop = async (event, targetSetId) => {
    event.preventDefault();
    const sourceSetId = draggedSetId;
    setDraggedSetId(null);
    setDragOverSetId(null);
    if (!sourceSetId || sourceSetId === targetSetId || reorderInFlightRef.current) return;

    const sourceIndex = sets.findIndex((set) => String(set.id) === String(sourceSetId));
    const targetIndex = sets.findIndex((set) => String(set.id) === String(targetSetId));
    if (sourceIndex === -1 || targetIndex === -1) return;

    const previousSets = sets;
    const reordered = [...sets];
    const [movedSet] = reordered.splice(sourceIndex, 1);
    reordered.splice(targetIndex, 0, movedSet);
    setSets(reordered);

    reorderInFlightRef.current = true;
    const loadingToastId = toast("Saving photo set order...", "loading");
    try {
      await photosApi.reorderSets(slug, reordered.map((set) => set.id));
      toast.dismiss(loadingToastId);
      toast("Photo set order saved.", "success");
    } catch (error) {
      setSets(previousSets);
      toast.dismiss(loadingToastId);
      toast(getErrorMessage(error, "Failed to save photo set order."), "error");
    } finally {
      reorderInFlightRef.current = false;
    }
  };

  const handleDragEnd = () => {
    setDraggedSetId(null);
    setDragOverSetId(null);
  };

  return (
    <>
      {/* DESKTOP SIDEBAR */}
      <aside
        aria-label="Collection navigation"
        className="sticky top-0 z-30 hidden h-screen w-[300px] flex-shrink-0 flex-col border-r border-cream-200 bg-surface-light md:flex"
      >
        {/* 1. TOP HEADER: Back arrow, Title, Date & Published tag */}
        <div className="flex items-center p-3.5 border-b border-cream-200">
          <div className="flex items-center gap-2.5 overflow-hidden">
            <button
              type="button"
              onClick={() => navigate("/dashboard/galleries")}
              className="text-muted hover:text-ink transition-colors cursor-pointer shrink-0"
              aria-label="Back to collections"
            >
              <ChevronLeft className="h-5 w-5" />
            </button>
            <div className="truncate">
              <h2 className="text-sm font-semibold text-ink truncate leading-tight">
                {gallery?.title || "Collection"}
              </h2>
              <p className="text-[11px] text-muted">
                {gallery?.created_at
                  ? new Date(gallery.created_at).toLocaleDateString("en-US", {
                      month: "short",
                      day: "numeric",
                      year: "numeric",
                      })
                  : null}
              </p>
            </div>
          </div>
        </div>

        {/* 2. COVER IMAGE. */}
        <CollectionCover gallery={gallery} />

        {/* 3. ICON NAVIGATION */}
        <nav className="flex items-center justify-between border-b border-cream-200 px-5 py-2.5">
          {NAV_ITEMS.map(({ to, end, label, Icon }) => (
            <NavLink
              key={label}
              to={resolvePath(basePath, to)}
              end={end}
              aria-label={label}
              className={({ isActive }) =>
                `group relative flex items-center justify-center p-1.5 transition-colors ${
                  isActive
                    ? "text-ink border-b-2 border-brand-green-600 pb-2 -mb-2.5"
                    : "text-muted hover:text-muted"
                }`
              }
            >
              <Icon className="h-5 w-5" strokeWidth={1.75} />
              <RailTooltip>{label}</RailTooltip>
            </NavLink>
          ))}
        </nav>

        {/* 4. SETS LIST */}
        <div className="flex-1 overflow-y-auto p-4">
          <div className="flex items-center justify-between mb-3">
            <span className="text-[11px] font-bold text-muted tracking-wider">
              PHOTOS
            </span>
            <button
              type="button"
              onClick={openCreateModal}
              className="flex items-center gap-1 text-xs font-medium text-brand-green-600 hover:text-brand-green-700 cursor-pointer"
            >
              <Plus className="h-3.5 w-3.5" /> Add Set
            </button>
          </div>

          {setsLoading ? (
            <div className="space-y-2" aria-label="Loading photo sets">
              {[0, 1, 2].map((item) => (
                <div
                  key={item}
                  className="h-10 rounded-md border border-cream-200 bg-cream-100 animate-pulse"
                />
              ))}
            </div>
          ) : (
            <div className="space-y-1.5">
              {sets.map((set) => {
                const isActive = String(activeSetId) === String(set.id);
                const isDragging = String(draggedSetId) === String(set.id);
                const isDragTarget = String(dragOverSetId) === String(set.id);
                return (
                  <div
                    key={set.id}
                    draggable={!reorderInFlightRef.current}
                    onDragStart={(event) => handleDragStart(event, set.id)}
                    onDragOver={(event) => handleDragOver(event, set.id)}
                    onDrop={(event) => handleDrop(event, set.id)}
                    onDragEnd={handleDragEnd}
                    className={`relative flex w-full items-center justify-between rounded-md border p-2.5 text-left transition-colors ${
                      isActive
                        ? "border-slate-200 bg-slate-100 text-slate-900"
                        : "border-cream-200 bg-cream-100 text-ink hover:bg-cream-100"
                    } ${isDragging ? "opacity-50" : ""} ${isDragTarget ? "ring-2 ring-slate-300" : ""}`}
                  >
                    <button
                      type="button"
                      onClick={() => onSetSelect?.(set.id)}
                      className="flex min-w-0 flex-1 items-center gap-2.5 text-left cursor-pointer"
                    >
                      <GripVertical className="h-4 w-4 flex-shrink-0 text-muted" aria-hidden="true" />
                      <span className="truncate text-xs font-medium">
                        {set.name} ({set.photo_count ?? 0})
                      </span>
                    </button>
                    <div className="relative ml-2 flex-shrink-0">
                      <button
                        type="button"
                        onClick={(event) => {
                          event.stopPropagation();
                          setOpenMenuSetId((current) => current === set.id ? null : set.id);
                        }}
                        className="rounded p-0.5 text-muted hover:bg-cream-200 hover:text-ink cursor-pointer"
                        aria-label={`More actions for ${set.name}`}
                        aria-expanded={openMenuSetId === set.id}
                      >
                        <MoreHorizontal className="h-4 w-4" />
                      </button>
                      {openMenuSetId === set.id && (
                        <div className="absolute right-0 top-full z-20 mt-1 w-40 rounded-lg border border-cream-200 bg-surface-light p-1 shadow-lg">
                          <button
                            type="button"
                            onClick={() => openEditModal(set, "name")}
                            className="block w-full rounded-md px-3 py-2 text-left text-xs text-ink hover:bg-cream-100 cursor-pointer"
                          >
                            Rename
                          </button>
                          <button
                            type="button"
                            onClick={() => openEditModal(set, "description")}
                            className="block w-full rounded-md px-3 py-2 text-left text-xs text-ink hover:bg-cream-100 cursor-pointer"
                          >
                            Edit description
                          </button>
                          <button
                            type="button"
                            onClick={() => handleDeleteSet(set)}
                            disabled={deletingSetId === set.id}
                            className="block w-full rounded-md px-3 py-2 text-left text-xs text-red-700 hover:bg-red-50 disabled:opacity-50 cursor-pointer"
                          >
                            Delete
                          </button>
                        </div>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </aside>

      <Modal
        open={createOpen}
        onClose={closeCreateModal}
        title="NEW PHOTO SET"
        size="md"
      >
        <form onSubmit={handleCreateSet} className="space-y-4">
          <div>
            <label htmlFor="new-photo-set-name" className="mb-1.5 block text-xs font-semibold text-ink">
              Photo Set Name
            </label>
            <input
              id="new-photo-set-name"
              value={newSetName}
              onChange={(event) => setNewSetName(event.target.value)}
              placeholder="e.g. Ceremony, Reception, Getting ready"
              disabled={creating}
              className="w-full rounded-lg border border-cream-300 bg-cream-50 px-3 py-2.5 text-sm text-ink focus:border-ink focus:outline-none disabled:opacity-60"
            />
          </div>

          <div>
            <label htmlFor="new-photo-set-description" className="mb-1.5 block text-xs font-semibold text-ink">
              Description
            </label>
            <textarea
              id="new-photo-set-description"
              value={newSetDescription}
              onChange={(event) => setNewSetDescription(event.target.value)}
              maxLength={500}
              rows={4}
              disabled={creating}
              className="w-full resize-none rounded-lg border border-cream-300 bg-cream-50 px-3 py-2.5 text-sm text-ink focus:border-ink focus:outline-none disabled:opacity-60"
            />
            <p className="mt-1.5 text-xs text-muted">
              Description is shown to clients viewing this photo set for additional storytelling.
            </p>
            <p className="mt-1 text-right text-[11px] text-muted">
              {newSetDescription.length}/500
            </p>
          </div>

          {createError && <p role="alert" className="text-xs text-red-600">{createError}</p>}

          <div className="flex justify-end gap-2 border-t border-cream-200 pt-4">
            <button
              type="button"
              onClick={closeCreateModal}
              disabled={creating}
              className="rounded-lg px-3.5 py-2 text-xs font-medium text-muted hover:bg-cream-100 disabled:opacity-50 cursor-pointer"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={creating}
              className="rounded-lg bg-ink px-4 py-2 text-xs font-semibold text-white hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-50 cursor-pointer"
            >
              {creating ? "Saving…" : "Save"}
            </button>
          </div>
        </form>
      </Modal>

      <Modal
        open={Boolean(editingSet)}
        onClose={closeEditModal}
        title={editingSet?.mode === "description" ? "EDIT DESCRIPTION" : "RENAME PHOTO SET"}
        size="md"
      >
        <form onSubmit={handleSaveEdit} className="space-y-4">
          <div>
            <label htmlFor="edit-photo-set-name" className="mb-1.5 block text-xs font-semibold text-ink">
              Photo Set Name
            </label>
            <input
              id="edit-photo-set-name"
              value={editName}
              onChange={(event) => setEditName(event.target.value)}
              disabled={savingEdit || editingSet?.mode === "description"}
              className="w-full rounded-lg border border-cream-300 bg-cream-50 px-3 py-2.5 text-sm text-ink focus:border-ink focus:outline-none disabled:opacity-60"
            />
          </div>

          {editingSet?.mode === "description" && (
            <div>
              <label htmlFor="edit-photo-set-description" className="mb-1.5 block text-xs font-semibold text-ink">
                Description
              </label>
              <textarea
                id="edit-photo-set-description"
                value={editDescription}
                onChange={(event) => setEditDescription(event.target.value)}
                maxLength={500}
                rows={4}
                disabled={savingEdit}
                className="w-full resize-none rounded-lg border border-cream-300 bg-cream-50 px-3 py-2.5 text-sm text-ink focus:border-ink focus:outline-none disabled:opacity-60"
              />
              <p className="mt-1 text-right text-[11px] text-muted">{editDescription.length}/500</p>
            </div>
          )}

          {editError && <p role="alert" className="text-xs text-red-600">{editError}</p>}

          <div className="flex justify-end gap-2 border-t border-cream-200 pt-4">
            <button
              type="button"
              onClick={closeEditModal}
              disabled={savingEdit}
              className="rounded-lg px-3.5 py-2 text-xs font-medium text-muted hover:bg-cream-100 disabled:opacity-50 cursor-pointer"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={savingEdit}
              className="rounded-lg bg-ink px-4 py-2 text-xs font-semibold text-white hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-50 cursor-pointer"
            >
              {savingEdit ? "Saving…" : "Save"}
            </button>
          </div>
        </form>
      </Modal>

      {/* MOBILE PHOTO SET NAVIGATION */}
      <div
        aria-label="Photo sets"
        className="fixed inset-x-0 z-40 border-t border-cream-200 bg-white/95 px-3 py-2 backdrop-blur-md md:hidden"
        style={{ bottom: "calc(3.5rem + env(safe-area-inset-bottom))" }}
      >
        {setsLoading ? (
          <div className="h-8 rounded-md bg-cream-100 animate-pulse" aria-label="Loading photo sets" />
        ) : (
          <div className="flex items-center gap-2 overflow-x-auto">
              {sets.map((set) => (
                <div key={set.id} className="relative flex flex-shrink-0 items-center">
                  <button
                    type="button"
                    onClick={() => onSetSelect?.(set.id)}
                    className={`rounded-md px-2.5 py-1.5 pr-8 text-[11px] font-medium whitespace-nowrap ${
                      String(activeSetId) === String(set.id)
                        ? "bg-slate-100 text-slate-900"
                        : "bg-cream-100 text-muted"
                    }`}
                  >
                    {set.name} ({set.photo_count ?? 0})
                  </button>
                  <button
                    type="button"
                    onClick={() => setOpenMenuSetId((current) => current === set.id ? null : set.id)}
                    className="absolute right-1 rounded p-0.5 text-muted cursor-pointer"
                    aria-label={`More actions for ${set.name}`}
                  >
                    <MoreHorizontal className="h-3.5 w-3.5" />
                  </button>
                  {openMenuSetId === set.id && (
                    <div className="absolute bottom-full left-0 z-30 mb-1 w-40 rounded-lg border border-cream-200 bg-surface-light p-1 shadow-lg">
                      <button
                        type="button"
                        onClick={() => openEditModal(set, "name")}
                        className="block w-full rounded-md px-3 py-2 text-left text-xs text-ink hover:bg-cream-100 cursor-pointer"
                      >
                        Rename
                      </button>
                      <button
                        type="button"
                        onClick={() => openEditModal(set, "description")}
                        className="block w-full rounded-md px-3 py-2 text-left text-xs text-ink hover:bg-cream-100 cursor-pointer"
                      >
                        Edit description
                      </button>
                      <button
                        type="button"
                        onClick={() => handleDeleteSet(set)}
                        disabled={deletingSetId === set.id}
                        className="block w-full rounded-md px-3 py-2 text-left text-xs text-red-700 hover:bg-red-50 disabled:opacity-50 cursor-pointer"
                      >
                        Delete
                      </button>
                    </div>
                  )}
                </div>
              ))}
              <button
                type="button"
                onClick={openCreateModal}
                className="flex flex-shrink-0 items-center gap-1 rounded-md px-2.5 py-1.5 text-[11px] font-medium text-brand-green-600 bg-cream-50 cursor-pointer"
              >
                <Plus className="h-3.5 w-3.5" /> Add Set
              </button>
          </div>
        )}
      </div>

      {/* MOBILE BOTTOM TABS */}
      <nav
        aria-label="Collection sections"
        className="fixed inset-x-0 bottom-0 z-40 flex border-t border-cream-200 bg-white/95 pb-[env(safe-area-inset-bottom)] backdrop-blur-md md:hidden"
      >
        {NAV_ITEMS.map(({ to, end, label, Icon }) => (
          <NavLink
            key={label}
            to={resolvePath(basePath, to)}
            end={end}
            className={({ isActive }) =>
              `flex flex-1 flex-col items-center gap-1 py-2.5 text-[10px] font-medium ${
                isActive ? "text-brand-green-600" : "text-muted"
              }`
            }
          >
            <Icon className="h-5 w-5" strokeWidth={1.75} />
            {label}
          </NavLink>
        ))}
      </nav>
    </>
  );
}
