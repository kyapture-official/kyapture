import React, { createContext, useContext, useState, useCallback } from 'react'

const ToastCtx = createContext(null)

let id = 0

export function ToastProvider({ children }) {
  const [toasts, setToasts] = useState([])

  const show = useCallback((message, type = 'info') => {
    const tid = ++id
    setToasts((t) => [...t, { id: tid, message, type }])
    setTimeout(() => setToasts((t) => t.filter((x) => x.id !== tid)), 3500)
  }, [])

  const icons = {
    success: '✓',
    error:   '✕',
    info:    'ℹ',
    warning: '⚠',
  }

  const colors = {
    success: 'bg-emerald-50 border-emerald-200 text-emerald-800',
    error:   'bg-red-50 border-red-200 text-red-800',
    info:    'bg-cream-100 border-cream-300 text-ink',
    warning: 'bg-amber-50 border-amber-200 text-amber-800',
  }

  return (
    <ToastCtx.Provider value={show}>
      {children}
      <div className="fixed bottom-5 right-5 z-[100] flex flex-col gap-2 pointer-events-none">
        {toasts.map((t) => (
          <div
            key={t.id}
            className={`
              flex items-center gap-3 px-4 py-3 rounded-xl border shadow-lg
              text-sm font-medium animate-fade-up pointer-events-auto
              ${colors[t.type]}
            `}
          >
            <span className="font-bold">{icons[t.type]}</span>
            {t.message}
          </div>
        ))}
      </div>
    </ToastCtx.Provider>
  )
}

export const useToast = () => useContext(ToastCtx)
