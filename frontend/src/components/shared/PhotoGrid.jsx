import { useState, useCallback, useRef, useEffect } from 'react'

// ── MODULE-LEVEL SYSTEM HELPERS ──────────────────────────────────────────────
// Hoisted outside the React lifecycle to prevent unnecessary allocations.

/**
 * Folds a freshly-arrived photo list into the list currently on screen
 * without disturbing any in-progress manual ordering: items that still
 * exist keep their current (possibly drag-reordered) position, items that
 * were removed upstream drop out, and new items are appended at the end.
 *
 * Used ONLY to replay a structural change that arrived mid-drag (see
 * `handleDragEnd`). It is intentionally NOT used for routine prop syncing.
 */
function mergePreservingOrder(currentList, freshList) {
  const freshById = new Map(freshList.map((p) => [p.id, p]))
  const merged = currentList.filter((p) => freshById.has(p.id)).map((p) => freshById.get(p.id))
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
}) {
  const [selectedIds, setSelectedIds] = useState(new Set())
  const [deleting, setDeleting] = useState(false)

  // Seed local state directly from the initial prop so the grid doesn't
  // flash empty for one frame while waiting on the sync effect.
  const [localPhotos, setLocalPhotos] = useState(photos)
  const [draggedIndex, setDraggedIndex] = useState(null)

  const isMounted = useRef(false)
  const draggedIndexRef = useRef(null)
  const initialOrderRef = useRef([])

  // Holds a `photos` update that arrived while a drag was in progress, so
  // its structural part (additions/removals) can be folded in once the
  // drag ends instead of being silently dropped.
  const pendingMergeRef = useRef(null)

  useEffect(() => {
    isMounted.current = true
    return () => { isMounted.current = false }
  }, [])

  // ── PROP SYNC & STATED ALIGNMENTS ─────────────────────────────────────────
  // We drop the reference-equality gate entirely. If a parent re-renders and
  // passes an un-memoized array, React's minor re-render is highly optimal.
  //
  // Outside of an active drag, the backend photos array serves as the absolute,
  // authoritative source of truth, allowing server-side sorts and collaborative
  // reorders to render immediately.
  useEffect(() => {
    if (draggedIndexRef.current !== null) {
      // Active drag: never let an incoming update reorder cards out from
      // under the user. Queue the structural part (additions/removals) for
      // replay once the drag ends, but patch attribute-only changes onto
      // the existing cards in place, in their current drag-reordered
      // positions, so a live update (e.g. a publish-status badge) doesn't
      // go stale just because a card happens to be mid-drag.
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

    // Steady state: `photos` is the source of truth for both content and
    // order — adopt it outright.
    setLocalPhotos(photos)

    const validIds = new Set(photos.map((p) => p.id))
    setSelectedIds((prev) => {
      const next = new Set([...prev].filter((id) => validIds.has(id)))
      return next.size !== prev.size ? next : prev
    })
  }, [photos])

  const totalPhotos = localPhotos.length
  const selectedCount = selectedIds.size
  const disabledSorting = selectedCount > 0 || deleting

  // ── SELECTION HANDLERS ────────────────────────────────────────────────

  const handleToggleSelect = useCallback((id, e) => {
    e.stopPropagation()
    setSelectedIds((prev) => {
      const next = new Set(prev)
      next.has(id) ? next.delete(id) : next.add(id)
      return next
    })
  }, [])

  const handleSelectAll = useCallback(() => {
    setSelectedIds(new Set(localPhotos.map((p) => p.id)))
  }, [localPhotos])

  const handleClearSelection = useCallback(() => {
    setSelectedIds(new Set())
  }, [])

  const handleDeleteSelected = useCallback(async () => {
    if (selectedCount === 0 || deleting) return

    const confirmed = window.confirm(
      `Are you sure you want to delete ${selectedCount} selected ${
        selectedCount === 1 ? 'photo' : 'photos'
      }? This action is irreversible.`
    )
    if (!confirmed) return

    setDeleting(true)
    try {
      await onDeletePhotos?.(Array.from(selectedIds))
      if (isMounted.current) setSelectedIds(new Set())
    } catch (err) {
      console.error('Bulk deletion failed:', err)
    } finally {
      if (isMounted.current) setDeleting(false)
    }
  }, [selectedCount, deleting, selectedIds, onDeletePhotos])

  const handlePhotoKeyDown = useCallback(
    (e, index) => {
      if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault()
        onPhotoClick?.(index)
      }
    },
    [onPhotoClick]
  )

  // ── DRAG-AND-DROP HANDLERS ────────────────────────────────────────────

  const handleDragStart = useCallback(
    (e, index) => {
      if (disabledSorting) return
      initialOrderRef.current = localPhotos.map((p) => p.id)
      draggedIndexRef.current = index
      setDraggedIndex(index)
      e.dataTransfer.effectAllowed = 'move'
      e.dataTransfer.setData('text/plain', String(index))
    },
    [disabledSorting, localPhotos]
  )

  const handleDragOverCard = useCallback(
    (e, targetIndex) => {
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
    },
    [disabledSorting]
  )

  const handleDragEnd = useCallback(async () => {
    draggedIndexRef.current = null
    setDraggedIndex(null)

    if (!disabledSorting) {
      const orderedIds = localPhotos.map((p) => p.id)
      const hasChanged = orderedIds.some((id, i) => id !== initialOrderRef.current[i])

      if (hasChanged) {
        try {
          await onReorderPhotos?.(orderedIds)
        } catch (err) {
          console.error('Failed to persist sorting order:', err)
          setLocalPhotos(photos)
        }
      }
    }

    // Replay any structural update that arrived mid-drag instead of letting
    // it vanish. This is the one place order preservation is correct: the
    // user's just-finished manual order should win for items that still
    // exist, while anything added or removed upstream during the drag gets
    // folded in.
    if (pendingMergeRef.current) {
      const fresh = pendingMergeRef.current
      pendingMergeRef.current = null

      setLocalPhotos((prev) => mergePreservingOrder(prev, fresh))

      const freshIds = new Set(fresh.map((p) => p.id))
      setSelectedIds((prev) => {
        const next = new Set([...prev].filter((id) => freshIds.has(id)))
        return next.size !== prev.size ? next : prev
      })
    }
  }, [disabledSorting, localPhotos, onReorderPhotos, photos])

  // ── RENDER ───────────────────────────────────────────────────────────

  const isGridActive = totalPhotos > 0 || uploadQueue.length > 0
  if (!isGridActive) return null

  return (
    <div className="relative pt-6 border-t border-gray-200 mt-8 animate-fadeUp">

      {/* ── FLOATING BULK SELECTION TOOLBAR ── */}
      {selectedCount > 0 && (
        <div
          role="toolbar"
          aria-label="Bulk actions toolbar"
          className="fixed bottom-6 left-1/2 -translate-x-1/2 bg-gray-900 text-white rounded-full px-6 py-3 shadow-2xl flex items-center gap-6 z-40 animate-fadeUp border border-gray-800"
        >
          <span className="text-xs font-semibold font-mono tracking-tight text-gray-300">
            {selectedCount} Selected
          </span>

          <div className="h-4 w-px bg-gray-800" aria-hidden="true" />

          <button
            type="button"
            onClick={selectedCount === totalPhotos ? handleClearSelection : handleSelectAll}
            className="text-xs font-medium text-gray-300 hover:text-white transition-colors cursor-pointer focus-visible:outline-none"
          >
            {selectedCount === totalPhotos ? 'Deselect All' : 'Select All'}
          </button>

          <button
            type="button"
            onClick={handleDeleteSelected}
            disabled={deleting}
            className="text-xs font-semibold text-red-400 hover:text-red-500 disabled:opacity-50 transition-colors cursor-pointer focus-visible:outline-none"
          >
            {deleting ? 'Deleting…' : 'Delete'}
          </button>

          <div className="h-4 w-px bg-gray-800" aria-hidden="true" />

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

      {/* ── PHOTO CARD GRID ── */}
      <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-4">

        {/* Upload progress cards */}
        {uploadQueue.map((item) => (
          <div
            key={item.id}
            className="relative aspect-square rounded-xl overflow-hidden border border-gray-200 bg-gray-50 shadow-sm flex flex-col items-center justify-center p-4"
          >
            <img
              src={item.previewUrl}
              alt={`Uploading ${item.file?.name || 'photo'}`}
              className="absolute inset-0 w-full h-full object-cover opacity-20 blur-[1px]"
            />
            <div className="relative z-10 flex flex-col items-center gap-2">
              <div className="relative w-12 h-12 flex items-center justify-center">
                <svg
                  className="absolute inset-0 w-full h-full -rotate-90"
                  viewBox="0 0 64 64"
                  xmlns="http://www.w3.org/2000/svg"
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
                <span className="text-[10px] font-bold text-gray-900 font-mono">
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
              aria-pressed={isSelected}
              aria-label={`${photo.original_name || 'Photo'}${isSelected ? ' — selected' : ''}`}
              onClick={() => onPhotoClick?.(index)}
              onKeyDown={(e) => handlePhotoKeyDown(e, index)}
              draggable={!disabledSorting}
              onDragStart={(e) => handleDragStart(e, index)}
              onDragOver={(e) => handleDragOverCard(e, index)}
              onDragEnd={handleDragEnd}
              className={`group relative aspect-square rounded-xl overflow-hidden border bg-gray-50 shadow-sm hover:shadow-md transition-all duration-200 ${
                isBeingDragged
                  ? 'border-gray-300 bg-gray-100 opacity-40 scale-[0.98]'
                  : isSelected
                    ? 'border-gray-900 ring-2 ring-gray-900/10'
                    : 'border-gray-200 hover:border-gray-300'
              } ${disabledSorting ? 'cursor-pointer' : 'cursor-grab active:cursor-grabbing'}`}
            >
              <img
                src={photo.image_url}
                alt={photo.original_name || 'Gallery item'}
                loading="lazy"
                className={`w-full h-full object-cover transition-transform duration-300 ease-out ${
                  isSelected ? 'scale-[0.98]' : 'group-hover:scale-[1.02]'
                }`}
                draggable="false"
              />

              {/* Selection checkbox */}
              <div
                className={`absolute top-3 left-3 z-10 transition-opacity duration-200 ${
                  isSelected ? 'opacity-100' : 'opacity-0 group-hover:opacity-100'
                }`}
              >
                <button
                  type="button"
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

              {/* Single-photo hover delete (hidden during multi-select) */}
              {selectedCount === 0 && (
                <div className="absolute inset-0 bg-gray-900/10 opacity-0 group-hover:opacity-100 transition-opacity flex items-start justify-end p-2.5 z-10">
                  <button
                    type="button"
                    onClick={(e) => {
                      e.stopPropagation()
                      if (window.confirm('Are you sure you want to delete this photo?')) {
                        onDeletePhotos?.([photo.id])
                      }
                    }}
                    className="p-1.5 rounded-lg bg-white/95 hover:bg-white text-gray-500 hover:text-red-600 shadow-sm border border-gray-200 transition-all cursor-pointer"
                    aria-label="Delete photo"
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