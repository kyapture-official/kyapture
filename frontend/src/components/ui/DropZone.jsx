import { useRef, useState, useEffect, useCallback } from 'react'

/**
 * WHAT: Accessible Drag-and-Drop File Upload Zone
 * WHY:  Handles bulk file selection via direct drag-over gestures or local system explorer.
 *       Hardened against child-node flickering, same-file re-upload blocks, and browser escapes.
 *
 * Key architectural decisions:
 *   dragCounter ref       — increments on enter, decrements on leave; only resets visual state
 *                           when counter hits zero, preventing flicker on child-element traversal.
 *   relatedTarget check   — null relatedTarget at window level is the spec-defined signal for a
 *                           true viewport exit (OS desktop, browser chrome, Escape cancellation).
 *                           No coordinate fallback: geometry checks fail on fast drags because the
 *                           last recorded position can be well inside the viewport, causing stuck
 *                           isDragging state. relatedTarget survives bubbling unchanged.
 *   input.value reset     — cleared after processFiles so onChange fires again on repeat selection
 *                           of the same file; without this the browser sees no change in value.
 *   'Files' type guard    — dataTransfer.types checked before activating state so text/link drags
 *                           never trigger the drop zone UI.
 */
export default function DropZone({
  onFiles,
  accept   = 'image/*',
  multiple = true,
  disabled = false,
  label    = 'Upload files',
  children,
}) {
  const [isDragging, setIsDragging] = useState(false)
  const inputRef    = useRef(null)
  const dragCounter = useRef(0)

  useEffect(() => {
    // Prevent the browser from opening a missed drop as a new page.
    const preventBrowserOpen = (e) => e.preventDefault()

    const resetDragState = () => {
      dragCounter.current = 0
      setIsDragging(false)
    }

    // relatedTarget is null when the pointer leaves to a non-document location:
    // the OS desktop, browser chrome, another application, or Escape cancellation.
    // This is the spec-defined signal for a viewport exit — reset immediately.
    const handleViewportExit = (e) => {
      if (!e.relatedTarget) resetDragState()
    }

    window.addEventListener('dragover',  preventBrowserOpen)
    window.addEventListener('drop',      preventBrowserOpen)
    window.addEventListener('dragleave', handleViewportExit)

    return () => {
      window.removeEventListener('dragover',  preventBrowserOpen)
      window.removeEventListener('drop',      preventBrowserOpen)
      window.removeEventListener('dragleave', handleViewportExit)
    }
  }, [])

  const processFiles = useCallback(
    (files) => {
      if (files?.length) {
        onFiles(Array.from(files))
        // Reset so the same file can be re-selected on the next interaction.
        if (inputRef.current) {
          inputRef.current.value = ''
        }
      }
    },
    [onFiles],
  )

  // Increment counter only for genuine file drags — not text or link drags.
  const handleDragEnter = useCallback(
    (e) => {
      e.preventDefault()
      e.stopPropagation()
      if (disabled) return
      if (!e.dataTransfer.types.includes('Files')) return
      dragCounter.current++
      setIsDragging(true)
    },
    [disabled],
  )

  // Must preventDefault to allow drop — no state change needed here.
  const handleDragOver = useCallback((e) => {
    e.preventDefault()
    e.stopPropagation()
  }, [])

  // Only clear visual state when the pointer truly left the zone,
  // not when it moved over a child element (counter > 0 still).
  const handleDragLeave = useCallback(
    (e) => {
      e.preventDefault()
      e.stopPropagation()
      if (disabled) return
      dragCounter.current--
      if (dragCounter.current <= 0) {
        dragCounter.current = 0
        setIsDragging(false)
      }
    },
    [disabled],
  )

  const handleDrop = useCallback(
    (e) => {
      e.preventDefault()
      e.stopPropagation()
      dragCounter.current = 0
      setIsDragging(false)
      if (disabled) return
      if (
        e.dataTransfer.types.includes('Files') &&
        e.dataTransfer.files?.length > 0
      ) {
        processFiles(e.dataTransfer.files)
      }
    },
    [disabled, processFiles],
  )

  const handleKeyDown = useCallback(
    (e) => {
      if (disabled) return
      if (e.key === ' ' || e.key === 'Enter') {
        e.preventDefault()
        inputRef.current?.click()
      }
    },
    [disabled],
  )

  const handleClick = useCallback(
    () => { if (!disabled) inputRef.current?.click() },
    [disabled],
  )

  return (
    <div
      role="button"
      tabIndex={disabled ? -1 : 0}
      aria-label={label}
      aria-disabled={disabled}
      onDragEnter={handleDragEnter}
      onDragOver={handleDragOver}
      onDragLeave={handleDragLeave}
      onDrop={handleDrop}
      onKeyDown={handleKeyDown}
      onClick={handleClick}
      className={[
        'relative cursor-pointer rounded-2xl border-2 border-dashed p-10',
        'flex flex-col items-center justify-center gap-3',
        'transition-colors duration-200',
        'focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2',
        disabled
          ? 'border-gray-200 bg-gray-50/50 opacity-50 cursor-not-allowed'
          : isDragging
            ? 'border-blue-400 bg-blue-50'
            : 'border-gray-300 bg-gray-50 hover:border-gray-400 hover:bg-gray-100',
      ].join(' ')}
    >
      <input
        ref={inputRef}
        type="file"
        accept={accept}
        multiple={multiple}
        disabled={disabled}
        className="hidden"
        onChange={(e) => processFiles(e.target.files)}
      />

      {children ?? (
        <>
          <div className="w-12 h-12 rounded-full bg-gray-200 flex items-center justify-center border border-gray-300">
            <svg
              className="w-6 h-6 text-gray-500"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
              aria-hidden="true"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={1.5}
                d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z"
              />
            </svg>
          </div>
          <div className="text-center">
            <p className="text-sm font-medium text-gray-900">Drop photos here</p>
            <p className="text-xs text-gray-500 mt-1">or click to browse — JPG, PNG, WEBP</p>
          </div>
        </>
      )}
    </div>
  )
}