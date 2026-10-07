// frontend/src/hooks/useNoIndex.js
import { useEffect } from 'react'

/**
 * 7-C: keeps a page out of search engines and sends no Referer from it, while
 * it is mounted (the forgot and reset password pages). The SPA has one
 * index.html, so the tags are added on mount and removed on unmount.
 */
export function useNoIndex() {
  useEffect(() => {
    const tags = [
      ['robots', 'noindex, nofollow'],
      ['referrer', 'no-referrer'],
    ].map(([name, content]) => {
      const meta = document.createElement('meta')
      meta.name = name
      meta.content = content
      meta.dataset.kyNoindex = 'true'
      document.head.appendChild(meta)
      return meta
    })
    return () => tags.forEach((meta) => meta.remove())
  }, [])
}
