import React, { useRef, useState } from 'react'

export default function DropZone({ onFiles, accept = 'image/*', multiple = true, children }) {
  const [dragging, setDragging] = useState(false)
  const inputRef = useRef()

  const handle = (files) => {
    if (files?.length) onFiles(Array.from(files))
  }

  return (
    <div
      onDragOver={(e) => { e.preventDefault(); setDragging(true) }}
      onDragLeave={() => setDragging(false)}
      onDrop={(e) => {
        e.preventDefault()
        setDragging(false)
        handle(e.dataTransfer.files)
      }}
      onClick={() => inputRef.current?.click()}
      className={`
        relative cursor-pointer rounded-2xl border-2 border-dashed p-10
        flex flex-col items-center justify-center gap-3 transition-all duration-200
        ${dragging
          ? 'border-cream-500 bg-cream-100'
          : 'border-cream-300 bg-cream-50 hover:border-cream-400 hover:bg-cream-100'
        }
      `}
    >
      <input
        ref={inputRef}
        type="file"
        accept={accept}
        multiple={multiple}
        className="hidden"
        onChange={(e) => handle(e.target.files)}
      />
      {children || (
        <>
          <div className="w-12 h-12 rounded-full bg-cream-200 flex items-center justify-center">
            <svg className="w-6 h-6 text-muted" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
                d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z"/>
            </svg>
          </div>
          <div className="text-center">
            <p className="text-sm font-medium text-ink">Drop photos here</p>
            <p className="text-xs text-muted mt-1">or click to browse — JPG, PNG, WEBP</p>
          </div>
        </>
      )}
    </div>
  )
}
