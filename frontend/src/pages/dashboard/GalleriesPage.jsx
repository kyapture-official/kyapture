import { useState, useCallback, useEffect, useRef } from 'react'
import { useGalleries } from '../../hooks/useGalleries'
import DashboardHeader    from '../../components/shared/DashboardHeader'
import LoadingSkeleton    from '../../components/shared/LoadingSkeleton'
import EmptyState         from '../../components/shared/EmptyState'
import GalleryCard        from '../../components/shared/GalleryCard'
import CreateGalleryModal from '../../components/shared/CreateGalleryModal'

// ── HOISTED MODULE-LEVEL UTILITIES ──────────────────────────────────────────

/**
 * Parses and normalizes backend exception payloads into a guaranteed string.
 *
 * Priority chain (matches Django global exception handler contract):
 *   1. String type guard    — useGalleries may already normalize to a plain string.
 *   2. response.data.error  — custom DRF exception handler's primary key.
 *   3. response.data.detail — DRF's built-in validation/permission key.
 *   4. err.message          — Axios network-level string (e.g. ECONNREFUSED).
 *   5. defaultMsg           — caller-supplied hard fallback.
 *
 * FIX (Bug 1): All property accesses on `err` now use optional chaining via
 * `err?.response?.data` and `err?.message`. The previous code wrote
 * `err.response?.data`, which guarded `.data` but NOT the initial `.response`
 * access — meaning any non-object thrown value (null, undefined, a number)
 * caused a secondary TypeError inside the error parser itself, masking the
 * original failure and producing an unrecoverable blank error state.
 *
 * FIX (Bug 2): The Array.isArray branch now maps each item through an explicit
 * string coercion and filters blanks before joining. The previous `raw.join(' ')`
 * relied on implicit JS coercion, which turns nested objects from malformed
 * middleware into the literal string "[object Object]" in the user-facing banner.
 *
 * Non-string DRF payloads are serialized to a flat string so they never reach
 * JSX as an unrenderable type, preventing "Objects are not valid as a React
 * child" production crashes.
 */
function parseActionError(err, defaultMsg) {
  // Guard 1 — already a plain string (pre-normalized by useGalleries or a re-throw).
  if (typeof err === 'string') return err || defaultMsg

  // Guard 2 — BUG 1 FIX: `err?.response?.data` instead of `err.response?.data`.
  // Protects against null, undefined, or primitive thrown values.
  const data = err?.response?.data
  if (data != null) {
    // `error` is the primary key from our custom Django exception handler.
    // `detail` is DRF's built-in key; it can be a string, string[], or field-error map.
    const raw = data.error ?? data.detail

    if (raw != null) {
      if (typeof raw === 'string') return raw

      // BUG 2 FIX: Explicitly coerce each item to a string and filter blank/falsy
      // entries before joining. Implicit coercion via Array.join() produces the
      // literal text "[object Object]" when middleware injects non-string items.
      if (Array.isArray(raw)) {
        const msg = raw
          .map(item => (typeof item === 'string' ? item : String(item)))
          .filter(Boolean)
          .join(' ')
        return msg || defaultMsg
      }

      // DRF field error map: { name: ["Too short."], slug: ["Already taken."] }
      // Flatten all field messages into a single banner string.
      const parsed = Object.values(raw).flat().join(' ')

      // Ensure the parsed string is non-empty before returning, preventing
      // silent blank alert boxes when `raw` is an empty object `{}`.
      if (parsed) return parsed
    }
  }

  // BUG 1 FIX: `err?.message` instead of `err.message`.
  // Covers Axios network errors (ECONNREFUSED, etc.) and guards against
  // null/undefined/non-object thrown values that would otherwise crash here.
  return err?.message || defaultMsg
}

/**
 * WHAT: Master Galleries Dashboard Page Orchestrator
 * WHY:  Coordinates our custom state hook, loading skeletons, empty states,
 *       and overlay modal into a single declarative, layout-reconciled view.
 */
export default function GalleriesPage() {
  const {
    galleries,
    loading,
    error,
    refetch,
    createGallery,
    deleteGallery,
    publishGallery,
  } = useGalleries()

  const [isModalOpen, setIsModalOpen] = useState(false)
  const [actionError, setActionError] = useState('')

  // ── UNMOUNT GUARD ─────────────────────────────────────────────────────────
  // Initialized to false — accurately reflects the pre-commit, pre-effect state.
  // Flipped to true inside useEffect after the first commit, then back to false
  // in the cleanup. Prevents setState on dead fibers when navigation occurs
  // mid-flight.
  const isMounted = useRef(false)
  useEffect(() => {
    isMounted.current = true
    return () => { isMounted.current = false }
  }, [])

  // ── IN-FLIGHT ACTION GUARDS ───────────────────────────────────────────────
  // Per-slug Set for publish/delete: allows concurrent actions on *different*
  // galleries while blocking duplicate requests on the *same* slug.
  const inFlightSlugs = useRef(new Set())

  // BUG 3 FIX: Boolean guard for create operations.
  // handlePublishToggle and handleDelete both guard against concurrent requests
  // via inFlightSlugs. handleCreate previously had no guard at all — on a slow
  // network a double-tap could fire two simultaneous createGallery calls.
  // A boolean ref is used here because no slug exists yet to key off.
  const isCreating = useRef(false)

  // ── MODAL OPEN/CLOSE LIFECYCLES ───────────────────────────────────────────
  // Clear stale action errors when the modal opens so the user starts fresh.
  const openModal = useCallback(() => {
    setActionError('')
    setIsModalOpen(true)
  }, [])

  const closeModal = useCallback(() => {
    setIsModalOpen(false)
  }, [])

  // ── CREATE ADAPTER ────────────────────────────────────────────────────────
  // The try-catch wraps ONLY the async createGallery call so it exclusively
  // handles backend/network errors. The null-result guard sits outside the
  // catch block — keeping two distinct failure paths semantically independent.
  //
  // BUG 3 FIX: isCreating ref added to guard against concurrent submissions.
  // The finally block always releases the lock so the ref never gets stuck,
  // even if createGallery rejects or the component unmounts mid-flight.
  const handleCreate = useCallback(async (payload) => {
    if (isCreating.current) return
    isCreating.current = true

    let result
    try {
      result = await createGallery(payload)
    } catch (err) {
      throw new Error(parseActionError(err, 'Failed to create collection.'))
    } finally {
      isCreating.current = false
    }

    // Null guard is outside the catch — this is an internal sentinel, not a
    // backend error, and must never be routed through parseActionError.
    if (result == null) throw new Error('Something went wrong. Please try again.')
    return result
  }, [createGallery])

  // ── ACTION HANDLERS ───────────────────────────────────────────────────────
  const handlePublishToggle = useCallback(async (slug, isPublished) => {
    if (inFlightSlugs.current.has(slug)) return
    inFlightSlugs.current.add(slug)
    try {
      setActionError('')
      await publishGallery(slug, isPublished)
    } catch (err) {
      if (isMounted.current) {
        setActionError(parseActionError(err, 'Failed to update publish status.'))
      }
    } finally {
      // Always release the lock — even on unmount — so the Set never leaks.
      inFlightSlugs.current.delete(slug)
    }
  }, [publishGallery])

  const handleDelete = useCallback(async (slug) => {
    if (inFlightSlugs.current.has(slug)) return
    inFlightSlugs.current.add(slug)
    try {
      setActionError('')
      await deleteGallery(slug)
    } catch (err) {
      if (isMounted.current) {
        setActionError(parseActionError(err, 'Failed to delete collection.'))
      }
    } finally {
      inFlightSlugs.current.delete(slug)
    }
  }, [deleteGallery])

  // ── ERROR NORMALIZATION ───────────────────────────────────────────────────
  // Routes query-level errors through parseActionError so Django's custom
  // exception payloads are surfaced here with the same fidelity as action errors.
  const queryErrorMsg = error ? parseActionError(error, 'Failed to load collections.') : ''

  // ── SAFE GALLERY COUNT ────────────────────────────────────────────────────
  // Guards against un-hydrated undefined array states on initial mount.
  const galleryCount = galleries?.length ?? 0

  return (
    // Note: animate-fadeUp is a custom animation defined inside index.css
    <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 animate-fadeUp">

      {/* 1. Global Page Header */}
      <DashboardHeader onCreateClick={openModal} />

      {/* Error Banner Container */}
      <div>
        {/* Ephemeral Action Error — exposes ✕ button to clear stale state */}
        {actionError && (
          <div
            role="alert"
            className="mb-4 p-4 rounded-xl bg-red-50 border border-red-200 text-sm text-red-700 font-sans flex items-start justify-between gap-3 animate-fadeUp"
          >
            <span>{actionError}</span>
            <button
              type="button"
              onClick={() => setActionError('')}
              className="shrink-0 text-red-400 hover:text-red-600 transition-colors cursor-pointer"
              aria-label="Dismiss error"
            >
              ✕
            </button>
          </div>
        )}

        {/* Static Query Error — suppressed while a retry is in-flight (!loading)
            so the skeleton and this banner never co-render simultaneously.
            Exposes a Retry trigger instead of a dismiss button. */}
        {!loading && queryErrorMsg && (
          <div
            role="alert"
            className="mb-4 p-4 rounded-xl bg-red-50 border border-red-200 text-sm text-red-700 font-sans flex items-start justify-between gap-3 animate-fadeUp"
          >
            <div className="flex flex-col sm:flex-row sm:items-center justify-between w-full gap-2">
              <span>{queryErrorMsg}</span>
              <button
                type="button"
                onClick={refetch}
                className="shrink-0 text-xs font-semibold px-2.5 py-1 bg-red-100 hover:bg-red-200 text-red-800 transition-colors rounded-lg cursor-pointer"
                aria-label="Retry loading collections"
              >
                Retry
              </button>
            </div>
          </div>
        )}
      </div>

      {/* 2. Centralised Content Lifecycle — explicit reconciler branches */}
      {loading && <LoadingSkeleton />}

      {!loading && !error && galleryCount === 0 && (
        <EmptyState onCreateClick={openModal} />
      )}

      {!loading && !error && galleryCount > 0 && (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6">
          {galleries.map((gallery) => (
            <GalleryCard
              key={gallery.slug}
              gallery={gallery}
              onPublishToggle={handlePublishToggle}
              onDeleteClick={handleDelete}
            />
          ))}
        </div>
      )}

      {/* 3. Modal Forms Layer */}
      <CreateGalleryModal
        isOpen={isModalOpen}
        onClose={closeModal}
        onCreateSubmit={handleCreate}
      />
    </main>
  )
}