// import { useState, useEffect, useRef } from 'react'
// import { useParams, Link, useNavigate } from 'react-router-dom'
// import { galleriesApi } from '../../api/galleriesApi'
// import { photosApi }    from '../../api/photosApi'
// import { mockGalleries } from '../../utils/mockGalleries'
// import Spinner from '../../components/ui/Spinner'
// import DropZone from '../../components/ui/DropZone'
// import PhotoGrid from '../../components/shared/PhotoGrid'

// const USE_MOCK_DATA = import.meta.env.VITE_USE_MOCK_DATA === 'true'

// export default function GalleryDetailPage() {
//   const { id } = useParams()   // holds the gallery SLUG despite the param's name
//   const navigate = useNavigate()

//   const [gallery, setGallery]       = useState(null)
//   const [loading, setLoading]       = useState(true)
//   const [errorMsg, setErrorMsg]     = useState('')
//   const [updating, setUpdating]     = useState(false)
//   const [copied, setCopied]         = useState(false)
//   const [copyFailed, setCopyFailed] = useState(false)

//   const [photos, setPhotos]           = useState([])
//   const [uploadQueue, setUploadQueue] = useState([])   // in-progress uploads, rendered separately from PhotoGrid

//   const [title, setTitle]                   = useState('')
//   const [brandingColor, setBrandingColor]   = useState('#000000')
//   const [isDownloadable, setIsDownloadable] = useState(false)
//   const [password, setPassword]             = useState('')
//   const [hasPassword, setHasPassword]       = useState(false)

//   const isMountedRef    = useRef(false)
//   const copyTimeoutRef  = useRef(null)
//   const skipNextLoadRef = useRef(false)
//   const blobUrlsRef     = useRef([])   // preview blob: URLs still awaiting revocation

//   useEffect(() => {
//     isMountedRef.current = true
//     return () => {
//       isMountedRef.current = false
//       if (copyTimeoutRef.current) clearTimeout(copyTimeoutRef.current)
//       // Safety net for any blob URLs never explicitly revoked
//       // (e.g. a failed upload the user never dismissed).
//       blobUrlsRef.current.forEach(url => URL.revokeObjectURL(url))
//     }
//   }, [])

//   const syncFormFromGallery = (data) => {
//     setGallery(data)
//     setTitle(data.title)
//     setBrandingColor(data.branding_color)
//     setIsDownloadable(data.is_downloadable)
//     setHasPassword(data.has_password)
//   }

//   // ── DATA LOADING ─────────────────────────────────────────────────────────
//   useEffect(() => {
//     async function loadGallery() {
//       if (skipNextLoadRef.current) {
//         skipNextLoadRef.current = false
//         setLoading(false)
//         return
//       }

//       setLoading(true)
//       setErrorMsg('')

//       if (USE_MOCK_DATA) {
//         setTimeout(() => {
//           const match = mockGalleries.find((g) => g.slug === id)
//           if (!match) {
//             if (isMountedRef.current) {
//               setErrorMsg('Collection not found.')
//               setLoading(false)
//             }
//             return
//           }
//           if (isMountedRef.current) {
//             syncFormFromGallery(match)
//             setPhotos(match.slug === 'mila-portraits' ? [
//               { id: 'mock-img-1', thumbnail_url: 'https://images.unsplash.com/photo-1534528741775-53994a69daeb?auto=format&fit=crop&w=400&q=80' },
//               { id: 'mock-img-2', thumbnail_url: 'https://images.unsplash.com/photo-1544005313-94ddf0286df2?auto=format&fit=crop&w=400&q=80' },
//             ] : [])
//             setLoading(false)
//           }
//         }, 300)
//         return
//       }

//       try {
//         const [galleryData, photosData] = await Promise.all([
//           galleriesApi.getGallery(id),
//           photosApi.list(id),
//         ])
//         if (isMountedRef.current) {
//           syncFormFromGallery(galleryData)
//           setPhotos(photosData || [])
//         }
//       } catch (err) {
//         if (isMountedRef.current) {
//           setErrorMsg(err.response?.data?.detail || 'Failed to retrieve collection configurations.')
//         }
//       } finally {
//         if (isMountedRef.current) setLoading(false)
//       }
//     }

//     loadGallery()
//   }, [id])

//   // ── PHOTO UPLOAD ─────────────────────────────────────────────────────────
//   const handleFilesSelected = async (files) => {
//     if (!files?.length) return

//     if (USE_MOCK_DATA) {
//       const queueItems = files.map(file => {
//         const previewUrl = URL.createObjectURL(file)
//         blobUrlsRef.current.push(previewUrl)
//         return { id: Math.random().toString(36).slice(2, 9), file, previewUrl, progress: 0 }
//       })
//       setUploadQueue(prev => [...prev, ...queueItems])
//       queueItems.forEach(item => {
//         let progress = 0
//         const interval = setInterval(() => {
//           progress += Math.floor(Math.random() * 15) + 5
//           if (progress >= 100) {
//             clearInterval(interval)
//             if (isMountedRef.current) {
//               setPhotos(prev => [...prev, { id: item.id, thumbnail_url: item.previewUrl, original_name: item.file.name }])
//               setUploadQueue(prev => prev.filter(q => q.id !== item.id))
//               // Mock preview becomes the PERMANENT thumbnail_url for this
//               // photo in mock mode — do not revoke, it's still in use.
//             }
//           } else if (isMountedRef.current) {
//             setUploadQueue(prev => prev.map(q => q.id === item.id ? { ...q, progress } : q))
//           }
//         }, 300)
//       })
//       return
//     }

//     const queueItems = files.map(file => {
//       const previewUrl = URL.createObjectURL(file)
//       blobUrlsRef.current.push(previewUrl)
//       return { id: Math.random().toString(36).slice(2, 9), file, previewUrl, progress: 0 }
//     })
//     setUploadQueue(prev => [...prev, ...queueItems])

//     for (const item of queueItems) {
//       const formData = new FormData()
//       formData.append('image', item.file)

//       try {
//         const uploaded = await photosApi.uploadBulk(
//           id,
//           formData,
//           (pct) => {
//             if (isMountedRef.current) {
//               setUploadQueue(prev => prev.map(q => q.id === item.id ? { ...q, progress: pct } : q))
//             }
//           }
//         )
//         if (isMountedRef.current) {
//           const newAssets = Array.isArray(uploaded) ? uploaded : [uploaded]
//           setPhotos(prev => [...prev, ...newAssets])
//           setUploadQueue(prev => prev.filter(q => q.id !== item.id))
//         }

//         // BUG FIX (blob memory leak): revoke immediately on success.
//         // PhotoGrid now renders this photo from the server's thumbnail_url —
//         // the local blob preview is no longer referenced anywhere and would
//         // otherwise sit in browser memory until the whole page unmounts.
//         // Safe to revoke unconditionally here: the queue item (and its
//         // <img src={item.previewUrl}>) has already been removed above.
//         URL.revokeObjectURL(item.previewUrl)
//         blobUrlsRef.current = blobUrlsRef.current.filter(u => u !== item.previewUrl)

//       } catch (err) {
//         if (isMountedRef.current) {
//           setUploadQueue(prev => prev.map(q => q.id === item.id ? { ...q, error: true } : q))
//           setErrorMsg(err.response?.data?.image?.[0] || `Failed to upload ${item.file.name}.`)
//         }
//         // NOT revoked here on purpose: the failed row stays visible in the
//         // queue (see handleDismissFailed below) still rendering
//         // item.previewUrl so the user can see WHICH photo failed. Revoking
//         // now would instantly break that thumbnail into a broken-image
//         // icon. It's revoked when the user dismisses the row instead, or
//         // by the unmount safety net if they navigate away first.
//       }
//     }
//   }

//   // Lets the user clear a failed upload row and reclaim its blob memory —
//   // closes the gap left by not revoking on error above.
//   const handleDismissFailed = (itemId) => {
//     setUploadQueue(prev => {
//       const item = prev.find(q => q.id === itemId)
//       if (item) {
//         URL.revokeObjectURL(item.previewUrl)
//         blobUrlsRef.current = blobUrlsRef.current.filter(u => u !== item.previewUrl)
//       }
//       return prev.filter(q => q.id !== itemId)
//     })
//   }

//   // ── PHOTO DELETE ─────────────────────────────────────────────────────────
//   const handleDeletePhoto = async (photoId) => {
//     // BUG FIX (rollback reorders the grid): capture the full array with its
//     // original ordering BEFORE the optimistic removal. On failure, restore
//     // this exact snapshot instead of appending the photo to the end —
//     // appending would move a deleted-then-restored photo from, say,
//     // position 3 of 10 to position 10 of 10, visibly scrambling the grid.
//     const originalPhotos = photos
//     const photo = originalPhotos.find(p => p.id === photoId)

//     setPhotos(prev => prev.filter(p => p.id !== photoId))

//     if (photo?.thumbnail_url?.startsWith('blob:')) {
//       URL.revokeObjectURL(photo.thumbnail_url)
//       blobUrlsRef.current = blobUrlsRef.current.filter(u => u !== photo.thumbnail_url)
//     }

//     if (USE_MOCK_DATA) return

//     try {
//       // Confirmed against photosApi.js: deletePhotos (plural) takes an
//       // array of IDs and fans out to DELETE /photos/photo/{id}/ per ID via
//       // Promise.allSettled. There is no singular deletePhoto method in this
//       // codebase — this call is already correct as written.
//       await photosApi.deletePhotos([photoId])
//     } catch {
//       if (isMountedRef.current) {
//         setPhotos(originalPhotos)   // restores exact original order/position
//         setErrorMsg('Failed to delete photo. Please try again.')
//       }
//     }
//   }

//   // ── SETTINGS ─────────────────────────────────────────────────────────────
//   const handleSaveSettings = async (e) => {
//     e.preventDefault()
//     if (!title.trim() || updating) return

//     setUpdating(true)
//     setErrorMsg('')

//     const payload = {
//       title: title.trim(),
//       branding_color: brandingColor,
//       is_downloadable: isDownloadable,
//     }

//     try {
//       let updated
//       if (USE_MOCK_DATA) {
//         const mockSlug = payload.title.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '')
//         updated = { ...gallery, ...payload, slug: mockSlug }
//       } else {
//         updated = await galleriesApi.updateGallery(id, payload)
//       }

//       syncFormFromGallery(updated)

//       if (updated.slug !== id) {
//         skipNextLoadRef.current = true
//         navigate(`/dashboard/galleries/${updated.slug}`, { replace: true })
//       }
//     } catch (err) {
//       if (isMountedRef.current) {
//         setErrorMsg(err.response?.data?.detail || 'Failed to save collection configurations.')
//       }
//     } finally {
//       if (isMountedRef.current) setUpdating(false)
//     }
//   }

//   // NOTE (backend gap): galleries/urls.py currently registers only two
//   // routes — '' and '<slug:slug>/'. Neither /publish/ nor /set-password/
//   // exist yet on the backend. These calls are written correctly against
//   // the documented API contract — flag to the backend, not a frontend fix.
//   const handleTogglePublish = async () => {
//     if (updating || !gallery) return
//     setUpdating(true)
//     setErrorMsg('')

//     const nextState = !gallery.is_published

//     try {
//       if (USE_MOCK_DATA) {
//         setGallery(prev => ({ ...prev, is_published: nextState }))
//       } else {
//         await galleriesApi.publishGallery(id, nextState)
//         setGallery(prev => ({ ...prev, is_published: nextState }))
//       }
//     } catch (err) {
//       if (isMountedRef.current) {
//         setErrorMsg(err.response?.data?.detail || 'Failed to update publication status.')
//       }
//     } finally {
//       if (isMountedRef.current) setUpdating(false)
//     }
//   }

//   const handleSavePassword = async (e) => {
//     e.preventDefault()
//     if (updating) return

//     if (!password && hasPassword) {
//       const confirmed = window.confirm(
//         'Remove password protection from this gallery? Clients will no longer need to authenticate.'
//       )
//       if (!confirmed) return
//     }

//     setUpdating(true)
//     setErrorMsg('')

//     try {
//       if (USE_MOCK_DATA) {
//         const newHasPassword = Boolean(password)
//         setHasPassword(newHasPassword)
//         setGallery(prev => ({ ...prev, has_password: newHasPassword }))
//         setPassword('')
//       } else {
//         const response = await galleriesApi.setGalleryPassword(id, password || null)
//         setHasPassword(response.has_password)
//         setGallery(prev => ({ ...prev, has_password: response.has_password }))
//         setPassword('')
//       }
//     } catch (err) {
//       if (isMountedRef.current) {
//         setErrorMsg(err.response?.data?.detail || 'Failed to update security credentials.')
//       }
//     } finally {
//       if (isMountedRef.current) setUpdating(false)
//     }
//   }

//   const handleCopyLink = async () => {
//     if (!gallery) return
//     const ownerUsername = gallery.owner_username ?? gallery.photographer_username ?? 'unknown'
//     const clientURL = `${window.location.protocol}//${window.location.host}/g/${ownerUsername}/${gallery.slug}`

//     try {
//       await navigator.clipboard.writeText(clientURL)
//       setCopied(true)
//       setCopyFailed(false)
//       if (copyTimeoutRef.current) clearTimeout(copyTimeoutRef.current)
//       copyTimeoutRef.current = setTimeout(() => setCopied(false), 2000)
//     } catch (err) {
//       console.error('Failed to copy link:', err)
//       setCopyFailed(true)
//       if (copyTimeoutRef.current) clearTimeout(copyTimeoutRef.current)
//       copyTimeoutRef.current = setTimeout(() => setCopyFailed(false), 2000)
//     }
//   }

//   // ── RENDER ───────────────────────────────────────────────────────────────
//   if (loading) {
//     return (
//       <div className="min-h-[60vh] flex items-center justify-center">
//         <Spinner size="lg" />
//       </div>
//     )
//   }

//   if (errorMsg && !gallery) {
//     return (
//       <div className="max-w-4xl mx-auto px-4 py-12">
//         <div role="alert" className="p-4 rounded-xl bg-red-50 border border-red-200 text-sm text-red-700 mb-6">
//           {errorMsg}
//         </div>
//         <Link to="/dashboard/galleries" className="text-sm font-semibold text-ink hover:underline">
//           ← Back to galleries
//         </Link>
//       </div>
//     )
//   }

//   const ownerUsername = gallery.owner_username ?? gallery.photographer_username ?? 'unknown'

//   return (
//     <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 animate-fadeUp">

//       <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4 pb-6 border-b border-cream-200 mb-8">
//         <div>
//           <div className="flex items-center gap-2 mb-1">
//             <Link to="/dashboard/galleries" className="text-xs font-medium text-muted hover:text-ink hover:underline">
//               Collections
//             </Link>
//             <span className="text-xs text-cream-300">/</span>
//             <span className="text-xs font-semibold text-ink">{gallery.title}</span>
//           </div>
//           <h1 className="text-2xl font-semibold text-ink tracking-tight font-sans">
//             {gallery.title}
//           </h1>
//         </div>

//         <div className="flex flex-wrap items-center gap-2">
//           <button
//             type="button"
//             onClick={handleCopyLink}
//             className="px-3.5 py-2 border border-cream-300 text-ink/80 hover:text-ink bg-white hover:bg-cream-50 text-sm font-medium rounded-lg transition-colors cursor-pointer shadow-sm flex items-center gap-2"
//           >
//             {copied ? 'Copied! ✓' : copyFailed ? 'Copy failed ✗' : 'Share Link'}
//           </button>

//           <button
//             type="button"
//             onClick={handleTogglePublish}
//             disabled={updating}
//             className={`px-4 py-2 text-sm font-medium rounded-lg transition-colors cursor-pointer shadow-sm ${
//               gallery.is_published
//                 ? 'bg-green-50 text-green-700 border border-green-200 hover:bg-green-100'
//                 : 'bg-ink text-white hover:opacity-90'
//             }`}
//           >
//             {gallery.is_published ? 'Published' : 'Publish Collection'}
//           </button>
//         </div>
//       </div>

//       {errorMsg && (
//         <div role="alert" className="mb-6 p-4 rounded-xl bg-red-50 border border-red-200 text-sm text-red-700 font-sans">
//           {errorMsg}
//         </div>
//       )}

//       <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">

//         <div className="lg:col-span-2 space-y-8">

//           {/* Card 1: Configuration */}
//           <div className="bg-white rounded-2xl border border-cream-200 shadow-sm p-6">
//             <h2 className="text-base font-semibold text-ink mb-6 border-b border-cream-100 pb-3">
//               Collection Configurations
//             </h2>
//             <form onSubmit={handleSaveSettings} noValidate className="space-y-6">
//               <div className="flex flex-col gap-1">
//                 <label className="text-xs font-semibold text-ink/80" htmlFor="gallery-title">
//                   Gallery Title
//                 </label>
//                 <input
//                   id="gallery-title"
//                   type="text"
//                   value={title}
//                   maxLength={100}
//                   onChange={(e) => setTitle(e.target.value)}
//                   disabled={updating}
//                   className="w-full px-3 py-2 text-sm rounded-lg border border-cream-300 focus:border-ink focus:outline-none focus:ring-2 focus:ring-cream-200 transition-all disabled:opacity-50"
//                   required
//                 />
//               </div>

//               <div className="p-4 bg-cream-50 rounded-xl border border-cream-100 text-xs">
//                 <span className="font-semibold text-muted uppercase tracking-wider block text-[10px]">
//                   Live Slug Link
//                 </span>
//                 <p className="mt-1 font-semibold text-ink/70 truncate">
//                   yourname.kyapture.com/g/{ownerUsername}/
//                   <span className="text-ink font-bold font-mono">
//                     {title.toLowerCase().trim().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '') || 'your-slug'}
//                   </span>
//                 </p>
//               </div>

//               <div className="flex flex-col gap-1">
//                 <label className="text-xs font-semibold text-ink/80" htmlFor="gallery-color">
//                   Photographer Brand Accent
//                 </label>
//                 <div className="flex items-center gap-3">
//                   <input
//                     id="gallery-color"
//                     type="color"
//                     value={brandingColor}
//                     onChange={(e) => setBrandingColor(e.target.value)}
//                     disabled={updating}
//                     className="w-10 h-10 rounded-lg border border-cream-300 cursor-pointer overflow-hidden p-0 bg-transparent disabled:cursor-not-allowed"
//                   />
//                   <span className="text-xs text-muted font-medium font-mono uppercase">
//                     {brandingColor}
//                   </span>
//                 </div>
//               </div>

//               <div className="flex items-center gap-2 pt-2 border-t border-cream-100">
//                 <input
//                   id="gallery-download"
//                   type="checkbox"
//                   checked={isDownloadable}
//                   onChange={(e) => setIsDownloadable(e.target.checked)}
//                   disabled={updating}
//                   className="w-4 h-4 rounded border-cream-300 text-ink focus:ring-ink cursor-pointer disabled:cursor-not-allowed"
//                 />
//                 <label className="text-xs font-semibold text-ink/80 cursor-pointer select-none" htmlFor="gallery-download">
//                   Allow clients to download high-resolution photos
//                 </label>
//               </div>

//               <div className="flex justify-end pt-4 border-t border-cream-100">
//                 <button
//                   type="submit"
//                   disabled={
//                     updating ||
//                     !title.trim() ||
//                     (
//                       title.trim() === gallery.title &&
//                       brandingColor === gallery.branding_color &&
//                       isDownloadable === gallery.is_downloadable
//                     )
//                   }
//                   className="px-4 py-2 bg-ink text-white text-sm font-medium rounded-lg hover:opacity-90 transition-colors cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed"
//                 >
//                   {updating ? 'Saving...' : 'Save Settings'}
//                 </button>
//               </div>
//             </form>
//           </div>

//           {/* Card 2: Password Protection */}
//           <div className="bg-white rounded-2xl border border-cream-200 shadow-sm p-6">
//             <h2 className="text-base font-semibold text-ink mb-2 border-b border-cream-100 pb-3">
//               Password Protection
//             </h2>
//             <p className="text-xs text-muted mb-6">
//               When password protection is enabled, clients must authenticate before entering the public photo grid.
//             </p>

//             <form onSubmit={handleSavePassword} className="space-y-4">
//               <div className="flex flex-col gap-1">
//                 <label className="text-xs font-semibold text-ink/80" htmlFor="gallery-password">
//                   {hasPassword ? 'Update/Clear Password' : 'Set Protection Password'}
//                 </label>
//                 <div className="flex gap-3">
//                   <input
//                     id="gallery-password"
//                     type="password"
//                     placeholder={hasPassword ? '••••••••' : 'Enter security password'}
//                     value={password}
//                     onChange={(e) => setPassword(e.target.value)}
//                     disabled={updating}
//                     className="flex-1 px-3 py-2 text-sm rounded-lg border border-cream-300 focus:border-ink focus:outline-none focus:ring-2 focus:ring-cream-200 transition-all disabled:opacity-50"
//                   />
//                   <button
//                     type="submit"
//                     disabled={updating}
//                     className="px-4 py-2 border border-cream-300 text-ink/80 hover:text-ink hover:bg-cream-50 text-sm font-medium rounded-lg transition-colors cursor-pointer disabled:opacity-50"
//                   >
//                     {password ? 'Save' : hasPassword ? 'Clear Protection' : 'Set Lock'}
//                   </button>
//                 </div>
//               </div>
//             </form>
//           </div>

//           {/* Card 3: Photo Management */}
//           <div className="bg-white rounded-2xl border border-cream-200 shadow-sm p-6">
//             <h2 className="text-base font-semibold text-ink mb-2 border-b border-cream-100 pb-3">
//               Photo Management
//             </h2>
//             <p className="text-xs text-muted mb-6">
//               Upload multiple images to populate this collection. Once uploaded, clients can browse, view in lightbox, and download.
//             </p>

//             <DropZone onFiles={handleFilesSelected} disabled={updating} />

//             {uploadQueue.length > 0 && (
//               <div className="mt-4 space-y-2">
//                 {uploadQueue.map(item => (
//                   <div key={item.id} className="flex items-center gap-3 p-2 rounded-lg bg-cream-50">
//                     <div className="w-8 h-8 rounded overflow-hidden flex-shrink-0 bg-cream-200">
//                       <img src={item.previewUrl} alt="" className="w-full h-full object-cover" />
//                     </div>
//                     <div className="flex-1">
//                       <div className="text-xs text-ink/70 truncate">{item.file.name}</div>
//                       <div className="h-1.5 bg-cream-200 rounded-full overflow-hidden mt-1">
//                         <div
//                           className={`h-full rounded-full transition-all ${item.error ? 'bg-red-400' : 'bg-ink'}`}
//                           style={{ width: `${item.error ? 100 : item.progress}%` }}
//                         />
//                       </div>
//                     </div>
//                     {item.error ? (
//                       <button
//                         type="button"
//                         onClick={() => handleDismissFailed(item.id)}
//                         className="text-[10px] text-red-600 hover:text-red-700 font-medium flex-shrink-0 cursor-pointer"
//                       >
//                         Failed · Dismiss
//                       </button>
//                     ) : (
//                       <span className="text-[10px] text-muted flex-shrink-0">
//                         {item.progress}%
//                       </span>
//                     )}
//                   </div>
//                 ))}
//               </div>
//             )}

//             <div className="mt-6">
//               <PhotoGrid photos={photos} onDelete={handleDeletePhoto} showActions />
//             </div>
//           </div>
//         </div>

//         {/* RIGHT COLUMN: BRAND PREVIEW */}
//         <div className="space-y-8">
//           <div className="bg-white rounded-2xl border border-cream-200 shadow-sm overflow-hidden p-6 flex flex-col items-center justify-center text-center py-10 min-h-[300px]">
//             {gallery.cover_url ? (
//               <img
//                 src={gallery.cover_url}
//                 alt={`${gallery.title} cover`}
//                 className="w-24 h-24 rounded-full object-cover border border-cream-100 mb-4 shadow-sm"
//               />
//             ) : (
//               <div
//                 className="w-16 h-16 rounded-full flex items-center justify-center text-white/30 mb-4"
//                 style={{ backgroundColor: brandingColor }}
//               >
//                 <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
//                   <path d="M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 1 2 2z"/>
//                   <circle cx="12" cy="13" r="4"/>
//                 </svg>
//               </div>
//             )}
//             <h3 className="text-sm font-semibold text-ink">{gallery.title}</h3>
//             <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-medium border mt-2 ${
//               gallery.is_published
//                 ? 'bg-green-50 text-green-700 border-green-200'
//                 : 'bg-yellow-50 text-yellow-700 border-yellow-200'
//             }`}>
//               {gallery.is_published ? 'Published' : 'Draft'}
//             </span>
//           </div>
//         </div>
//       </div>
//     </div>
//   )
// }