import React, { useEffect, useState } from 'react'
import { galleriesApi } from '../../api/galleriesApi'
import { photosApi } from '../../api/photosApi'
import DropZone from '../../components/ui/DropZone'
import Button from '../../components/ui/Button'
import { useToast } from '../../components/ui/Toast'

export default function UploadPage() {
  const toast = useToast()
  const [galleries, setGalleries] = useState([])
  const [selected, setSelected] = useState('')
  const [files, setFiles] = useState([])
  const [uploading, setUploading] = useState(false)
  const [results, setResults] = useState([])

  useEffect(() => {
    galleriesApi.list().then((r) => {
      const all = r.data.results || r.data
      setGalleries(all)
      if (all.length) setSelected(all[0].id)
    })
  }, [])

  const handleUpload = async () => {
    if (!selected || !files.length) return
    setUploading(true)
    setResults([])
    const out = []
    for (const file of files) {
      const fd = new FormData()
      fd.append('image', file)
      fd.append('gallery', selected)
      fd.append('original_name', file.name)
      fd.append('file_size', file.size)
      try {
        await photosApi.upload(selected, fd)
        out.push({ name: file.name, ok: true })
      } catch {
        out.push({ name: file.name, ok: false })
      }
      setResults([...out])
    }
    setUploading(false)
    const succeeded = out.filter((x) => x.ok).length
    toast(`${succeeded} / ${files.length} photos uploaded.`, succeeded === files.length ? 'success' : 'warning')
  }

  return (
    <div className="max-w-2xl">
      <div className="mb-8 animate-fade-up">
        <h1 className="font-serif text-4xl text-ink mb-1">Upload Photos</h1>
        <p className="text-sm text-muted">Select a gallery and drop your photos in.</p>
      </div>

      {/* Gallery selector */}
      <div className="mb-6 animate-fade-up delay-100">
        <label className="text-sm font-medium text-ink/80 block mb-2">Target Gallery</label>
        <select
          className="w-full px-4 py-2.5 bg-white border border-cream-300 rounded-lg text-sm text-ink focus:outline-none focus:border-cream-500 focus:ring-2 focus:ring-cream-200"
          value={selected}
          onChange={(e) => setSelected(e.target.value)}
        >
          {galleries.map((g) => (
            <option key={g.id} value={g.id}>{g.title}</option>
          ))}
        </select>
      </div>

      {/* Drop zone */}
      <div className="animate-fade-up delay-200 mb-6">
        <DropZone onFiles={setFiles} multiple>
          <div className="w-12 h-12 rounded-full bg-cream-200 flex items-center justify-center mb-3">
            <svg className="w-6 h-6 text-muted" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
                d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12"/>
            </svg>
          </div>
          {files.length > 0 ? (
            <div className="text-center">
              <p className="text-sm font-medium text-ink">{files.length} files selected</p>
              <p className="text-xs text-muted mt-1">Click to change selection</p>
            </div>
          ) : (
            <div className="text-center">
              <p className="text-sm font-medium text-ink">Drop photos here</p>
              <p className="text-xs text-muted mt-1">or click to browse — JPG, PNG, WEBP</p>
            </div>
          )}
        </DropZone>
      </div>

      {files.length > 0 && (
        <div className="mb-6 bg-white rounded-2xl border border-cream-200 overflow-hidden animate-fade-up">
          <div className="px-4 py-3 border-b border-cream-100 flex items-center justify-between">
            <span className="text-sm font-medium text-ink">{files.length} files queued</span>
            <button onClick={() => setFiles([])} className="text-xs text-muted hover:text-red-500">Clear</button>
          </div>
          <div className="max-h-48 overflow-y-auto divide-y divide-cream-100">
            {files.map((f, i) => {
              const result = results[i]
              return (
                <div key={i} className="flex items-center gap-3 px-4 py-2.5">
                  <svg className="w-4 h-4 text-muted shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
                      d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14"/>
                  </svg>
                  <span className="flex-1 text-sm text-ink truncate">{f.name}</span>
                  <span className="text-xs">
                    {result ? (result.ok ? '✓' : '✕') : '—'}
                  </span>
                </div>
              )
            })}
          </div>
        </div>
      )}

      <Button
        onClick={handleUpload}
        loading={uploading}
        disabled={!files.length || !selected}
        className="animate-fade-up delay-300"
      >
        Upload {files.length > 0 ? `${files.length} Photos` : 'Photos'}
      </Button>
    </div>
  )
}
