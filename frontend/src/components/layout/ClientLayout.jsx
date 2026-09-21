// C:/Users/LENOVO/Desktop/kyapture/frontend/src/components/layout/ClientLayout.jsx
import React from 'react'

export default function ClientLayout({ children, photographer }) {
  return (
    <div className="min-h-screen bg-slate-50">
      {/* Minimal sticky header */}
      <header className="border-b border-slate-200 bg-white/80 backdrop-blur-md sticky top-0 z-30">
        <div className="max-w-6xl mx-auto px-4 sm:px-6 py-3.5 flex items-center justify-between">
          <div className="flex items-center gap-3 min-w-0">
            {photographer?.avatar ? (
              <img
                src={photographer.avatar}
                alt=""
                className="w-8 h-8 rounded-full object-cover ring-2 ring-slate-200"
              />
            ) : (
              <div className="w-8 h-8 rounded-full bg-teal-500 flex items-center justify-center flex-shrink-0">
                <span className="text-white text-xs font-semibold">
                  {(photographer?.display_name || photographer?.username || "K")[0].toUpperCase()}
                </span>
              </div>
            )}
            <span className="font-serif text-lg text-ink truncate">
              {photographer?.display_name || photographer?.username}
            </span>
          </div>
          <div className="text-[10px] uppercase tracking-widest text-muted font-medium hidden sm:block">
            Delivered via Kyapture
          </div>
        </div>
      </header>
      <main>
        {children}
      </main>
    </div>
  );
}
