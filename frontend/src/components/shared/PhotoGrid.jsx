import { useState, useCallback, useRef, useEffect } from 'react'

// ── MODULE-LEVEL SYSTEM HELPERS ──────────────────────────────────────────────
// Folds a freshly-arrived photo list into the list currently on screen, preserving custom order.
// Used ONLY to replay structural changes that arrive while a drag is in progress.
function mergePreservingOrder(currentList, freshList) {
  const freshById = new Map(freshList.map((p) => [p.id, p]))
  const merged = currentList
    .filter((p) => freshById.has(p.id))
    .map((p) => freshById.get(p.id))
  const known = new Set(merged.map((p) => p.id))
  freshList.forEach((p) => {
    if (!known.has(p.id)) merged.push(p)
  })
  return merged
}

export default function PhotoGrid({
  photos = [],
  uploadQueue = [],
  onDeletePhotos,
  onReorderPhotos,
  onPhotoClick,
  readOnly = false, // Security gate: caller MUST pass true on unauthenticated/public routes
}) {
  const [selectedIds, setSelectedIds] = useState(new Set())
  const [deleting, setDeleting] = useState(false)
  const [deleteError, setDeleteError] = useState(null)
  const [localPhotos, setLocalPhotos] = useState(photos)
  const [draggedIndex, setDraggedIndex] = useState(null)

  // ── REFS (for stable callback access; do not trigger re-renders) ──────────
  const isMounted           = useRef(false)
  const draggedIndexRef     = useRef(null)
  const initialOrderRef     = useRef([])       // id list captured at drag-start
  const sortingActiveRef    = useRef(false)    // true only between dragstart → dragend
  const localPhotosRef      = useRef(localPhotos) // mirrors state for stable callbacks
  const pendingMergeRef     = useRef(null)

  // Keep ref mirrors current on every render so stable callbacks see latest values
  localPhotosRef.current = localPhotos

  useEffect(() => {
    isMounted.current = true
    return () => { isMounted.current = false }
  }, [])

  // ── PROP SYNCHRONIZATION ──────────────────────────────────────────────────
  // Keeps localPhotos aligned with the authoritative `photos` prop.
  // During an active drag, structural changes are queued, while attributes are patched.
  useEffect(() => {
    // If a drag is active, queue structural changes but patch attributes in place.
    if (draggedIndexRef.current !== null) {
      pendingMergeRef.current = photos
      const freshById = new Map(photos.map((p) => [p.id, p]))
      setLocalPhotos((current) =>
        current.map((p) => {
          const fresh = freshById.get(p.id)
          return fresh ? { ...p, ...fresh } : p
        })
      )
      return
    }

    // Steady state: `photos` is the source of truth for both content and order.
    // Adopt it outright. This handles external reorders, new uploads, etc.
    setLocalPhotos(photos)

    // Prune selected IDs that no longer exist in the `photos` list.
    const validIds = new Set(photos.map((p) => p.id))
    setSelectedIds((prev) => {
      const next = new Set([...prev].filter((id) => validIds.has(id)))
      return next.size !== prev.size ? next : prev
    })
  }, [photos])

  const totalPhotos  = localPhotos.length
  const selectedCount = selectedIds.size

  // Sorting and dragging are disabled in readOnly mode, during bulk selection,
  // and while a deletion is in flight.
  const disabledSorting = readOnly || selectedCount > 0 || deleting

  // ── SELECTION HANDLERS ────────────────────────────────────────────────────

  const handleToggleSelect = useCallback((id, e) => {
    e.stopPropagation()
    if (readOnly) return
    setSelectedIds((prev) => {
      const next = new Set(prev)
      next.has(id) ? next.delete(id) : next.add(id)
      return next
    })
  }, [readOnly])

  const handleSelectAll = useCallback(() => {
    if (readOnly) return
    setSelectedIds(new Set(localPhotosRef.current.map((p) => p.id)))
  }, [readOnly])

  const handleClearSelection = useCallback(() => {
    setSelectedIds(new Set())
  }, [])

  const handleDeleteSelected = useCallback(async () => {
    if (selectedCount === 0 || deleting || readOnly) return

    const confirmed = window.confirm(
      `Delete ${selectedCount} selected ${
        selectedCount === 1 ? 'photo' : 'photos'
      }? This cannot be undone.`
    )
    if (!confirmed) return

    setDeleting(true)
    setDeleteError(null)
    try {
      await onDeletePhotos?.(Array.from(selectedIds))
      if (isMounted.current) setSelectedIds(new Set())
    } catch (err) {
      console.error('Bulk deletion failed:', err)
      if (isMounted.current) setDeleteError('Deletion failed — please try again.')
    } finally {
      if (isMounted.current) setDeleting(false)
    }
  }, [selectedCount, deleting, selectedIds, onDeletePhotos, readOnly])

  const handlePhotoKeyDown = useCallback((e, index) => {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault()
      onPhotoClick?.(index)
    }
  }, [onPhotoClick])

  // ── DRAG-AND-DROP HANDLERS ────────────────────────────────────────────────

  const handleDragStart = useCallback((e, index) => {
    if (disabledSorting) return
    initialOrderRef.current   = localPhotosRef.current.map((p) => p.id)
    sortingActiveRef.current  = true
    draggedIndexRef.current   = index
    setDraggedIndex(index)
    e.dataTransfer.effectAllowed = 'move'
    e.dataTransfer.setData('text/plain', String(index))
  }, [disabledSorting])

  const handleDragOverCard = useCallback((e, targetIndex) => {
    e.preventDefault()
    const current = draggedIndexRef.current
    if (current === null || current === targetIndex || disabledSorting) return

    setLocalPhotos((prev) => {
      const reordered = [...prev]
      const [item] = reordered.splice(current, 1)
      reordered.splice(targetIndex, 0, item)
      return reordered
    })

    draggedIndexRef.current = targetIndex
    setDraggedIndex(targetIndex)
  }, [disabledSorting])

  const handleDragEnd = useCallback(async () => {
    draggedIndexRef.current = null
    setDraggedIndex(null)

    if (sortingActiveRef.current) {
      sortingActiveRef.current = false // Clear active sorting lock
      const orderedIds = localPhotosRef.current.map((p) => p.id)
      const hasChanged = orderedIds.some((id, i) => id !== initialOrderRef.current[i])

      if (hasChanged) {
        try {
          await onReorderPhotos?.(orderedIds)
        } catch (err) {
          console.error('Failed to persist sort order:', err)
          if (isMounted.current) setLocalPhotos(photos)
        }
      }
    }

    // Replay any structural update that arrived mid-drag instead of letting it vanish.
    // Order is preserved for existing items; additions/removals are folded in.
    if (pendingMergeRef.current) {
      const fresh = pendingMergeRef.current
      pendingMergeRef.current = null

      if (isMounted.current) {
        setLocalPhotos((prev) => mergePreservingOrder(prev, fresh))
        const freshIds = new Set(fresh.map((p) => p.id))
        setSelectedIds((prev) => {
          const next = new Set([...prev].filter((id) => freshIds.has(id)))
          return next.size !== prev.size ? next : prev
        })
      }
    }
  }, [onReorderPhotos, photos]) // Removed disabledSorting, localPhotos from deps due to refs

  // ── RENDER ────────────────────────────────────────────────────────────────

  if (totalPhotos === 0 && uploadQueue.length === 0) return null

  return (
    <div className="relative pt-6 border-t border-gray-200 mt-8 animate-fadeUp">

      {/* Floating bulk-action toolbar — only rendered when photos are selected */}
      {!readOnly && selectedCount > 0 && (
        <div
          role="toolbar"
          aria-label="Bulk actions"
          className="fixed bottom-6 left-1/2 -translate-x-1/2 bg-gray-900 text-white rounded-full px-6 py-3 shadow-2xl flex items-center gap-6 z-40 animate-fadeUp border border-gray-800"
        >
          <span className="text-xs font-semibold font-mono tracking-tight text-gray-300">
            {selectedCount} selected
          </span>

          {deleteError && (
            <span role="alert" className="text-xs font-medium text-red-400">
              {deleteError}
            </span>
          )}

          <div className="h-4 w-px bg-gray-700" aria-hidden="true" />

          <button
            type="button"
            onClick={selectedCount === totalPhotos ? handleClearSelection : handleSelectAll}
            className="text-xs font-medium text-gray-300 hover:text-white transition-colors cursor-pointer focus-visible:outline-none"
          >
            {selectedCount === totalPhotos ? 'Deselect all' : 'Select all'}
          </button>

          <button
            type="button"
            onClick={handleDeleteSelected}
            disabled={deleting}
            className="text-xs font-semibold text-red-400 hover:text-red-300 disabled:opacity-50 transition-colors cursor-pointer focus-visible:outline-none"
          >
            {deleting ? 'Deleting…' : 'Delete'}
          </button>

          <div className="h-4 w-px bg-gray-700" aria-hidden="true" />

          <button
            type="button"
            onClick={handleClearSelection}
            disabled={deleting}
            className="p-1 rounded-full bg-gray-800 hover:bg-gray-700 text-gray-400 hover:text-white transition-colors cursor-pointer focus-visible:outline-none"
            aria-label="Clear selection"
          >
            <svg
              className="w-3.5 h-3.5"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
              strokeLinecap="round"
              strokeLinejoin="round"
              aria-hidden="true"
            >
              <line x1="18" y1="6" x2="6" y2="18" />
              <line x1="6" y1="6" x2="18" y2="18" />
            </svg>
          </button>
        </div>
      )}

      {/* ── GRID ── */}
      <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-4">

        {/* In-flight upload placeholders */}
        {uploadQueue.map((item) => (
          <div
            key={item.id}
            aria-label={`Uploading ${item.file?.name || 'photo'}`}
            aria-busy="true"
            className="relative aspect-square rounded-xl overflow-hidden border border-gray-200 bg-gray-50 shadow-sm flex flex-col items-center justify-center p-4"
          >
            <img
              src={item.previewUrl}
              alt=""
              aria-hidden="true"
              className="absolute inset-0 w-full h-full object-cover opacity-20 blur-[1px]"
            />
            <div className="relative z-10 flex flex-col items-center gap-2">
              <div className="relative w-12 h-12 flex items-center justify-center">
                <svg
                  className="absolute inset-0 w-full h-full -rotate-90"
                  viewBox="0 0 64 64"
                  xmlns="http://www.w3.org/2000/svg"
                  aria-hidden="true"
                >
                  <circle cx="32" cy="32" r="28" stroke="#e5e7eb" strokeWidth="4" fill="transparent" />
                  <circle
                    cx="32" cy="32" r="28"
                    stroke="#111827" strokeWidth="4" fill="transparent"
                    strokeDasharray={`${2 * Math.PI * 28}`}
                    strokeDashoffset={`${2 * Math.PI * 28 * (1 - item.progress / 100)}`}
                    className="transition-all duration-100 ease-out"
                  />
                </svg>
                <span
                  aria-live="polite"
                  className="text-[10px] font-bold text-gray-900 font-mono"
                >
                  {item.progress}%
                </span>
              </div>
              <span className="text-[10px] font-semibold text-gray-500 uppercase tracking-wider">
                Uploading
              </span>
            </div>
          </div>
        ))}

        {/* Active photo cards */}
        {localPhotos.map((photo, index) => {
          const isSelected = selectedIds.has(photo.id)
          const isBeingDragged = index === draggedIndex

          return (
            <div
              key={photo.id}
              role="button"
              tabIndex={0}
              aria-label={`${photo.original_name || 'Photo'} — press Enter to open`}
              onClick={() => onPhotoClick?.(index)}
              onKeyDown={(e) => handlePhotoKeyDown(e, index)}
              draggable={!disabledSorting}
              onDragStart={(e) => handleDragStart(e, index)}
              onDragOver={(e) => handleDragOverCard(e, index)}
              onDragEnd={handleDragEnd}
              className={[
                'group relative aspect-square rounded-xl overflow-hidden border bg-gray-50',
                'shadow-sm hover:shadow-md transition-all duration-200',
                isBeingDragged
                  ? 'border-gray-300 bg-gray-100 opacity-40 scale-[0.98]'
                  : isSelected
                    ? 'border-gray-900 ring-2 ring-gray-900/10'
                    : 'border-gray-200 hover:border-gray-300',
                disabledSorting ? 'cursor-pointer' : 'cursor-grab active:cursor-grabbing',
              ].join(' ')}
            >
              <img
                src={photo.image_url}
                alt={photo.original_name || 'Gallery photo'}
                loading="lazy"
                className={`w-full h-full object-cover transition-transform duration-300 ease-out ${
                  isSelected ? 'scale-[0.98]' : 'group-hover:scale-[1.02]'
                }`}
                draggable="false"
              />

              {/* Selection checkbox — hidden unconditionally in readOnly mode */}
              {!readOnly && (
                <div
                  className={`absolute top-3 left-3 z-10 transition-opacity duration-200 ${
                    isSelected ? 'opacity-100' : 'opacity-0 group-hover:opacity-100'
                  }`}
                >
                  <button
                    type="button"
                    aria-pressed={isSelected}
                    onClick={(e) => handleToggleSelect(photo.id, e)}
                    aria-label={isSelected ? 'Deselect photo' : 'Select photo'}
                    className={`w-5 h-5 rounded-md flex items-center justify-center border transition-all cursor-pointer shadow-sm ${
                      isSelected
                        ? 'bg-gray-900 border-gray-900 text-white'
                        : 'bg-white/90 backdrop-blur-sm border-gray-300 hover:border-gray-400 hover:bg-white'
                    }`}
                  >
                    {isSelected && (
                      <svg
                        xmlns="http://www.w3.org/2000/svg"
                        width="12"
                        height="12"
                        viewBox="0 0 24 24"
                        fill="none"
                        stroke="currentColor"
                        strokeWidth="4"
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        aria-hidden="true"
                      >
                        <polyline points="20 6 9 17 4 12" />
                      </svg>
                    )}
                  </button>
                </div>
              )}

              {/* Per-card delete hover action — hidden during multi-select and in readOnly mode */}
              {!readOnly && selectedCount === 0 && (
                <div className="absolute inset-0 bg-gray-900/10 opacity-0 group-hover:opacity-100 transition-opacity flex items-start justify-end p-2.5 z-10">
                  <button
                    type="button"
                    onClick={(e) => {
                      e.stopPropagation()
                      if (window.confirm('Delete this photo? This cannot be undone.')) {
                        onDeletePhotos?.([photo.id])
                      }
                    }}
                    aria-label={`Delete ${photo.original_name || 'this photo'}`}
                    className="p-1.5 rounded-lg bg-white/95 hover:bg-white text-gray-500 hover:text-red-600 shadow-sm border border-gray-200 transition-all cursor-pointer"
                  >
                    <svg
                      xmlns="http://www.w3.org/2000/svg"
                      width="14"
                      height="14"
                      viewBox="0 0 24 24"
                      fill="none"
                      stroke="currentColor"
                      strokeWidth="2.5"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      aria-hidden="true"
                    >
                      <polyline points="3 6 5 6 21 6" />
                      <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" />
                    </svg>
                  </button>
                </div>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}