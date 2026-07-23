// File Location: frontend/src/components/shared/ErrorBoundary.jsx

import React, { Component } from 'react'

// Vite-correct dev detection: compiled statically to a boolean literal during build.
// False on all production built outputs, completely securing local QA tests.
const isDev = import.meta.env.DEV

/**
 * WHAT: Isomorphic React Error Boundary Class Component
 * WHY:  Captures runtime rendering exceptions inside child subtrees,
 *       preventing entire Single Page Application (SPA) white-screen blackouts [weekly tasks.txt].
 */
export default class ErrorBoundary extends Component {
  constructor(props) {
    super(props)
    this.state = {
      hasError:    false,
      error:       null,
      errorInfo:   null,
      showDetails: false,
    }
  }

  // Runs synchronously during the render commit pass — synchronously updates state
  // before the browser paints to prevent visual flickering.
  static getDerivedStateFromError(error) {
    return { hasError: true, error }
  }

  // Captures side-effects and logs active exception stacks
  componentDidCatch(error, errorInfo) {
    this.setState({ errorInfo })

    // Production log tracking: dispatch exception stack parameters to Sentry/logs
    if (!isDev) {
      console.error('[ErrorBoundary]', error, errorInfo)
    }

    // Call the optional onError hook to let parent routing contexts capture the crash
    this.props.onError?.(error, errorInfo)
  }

  handleReload = () => {
    window.location.reload()
  }

  // Erases all persistent states and session caches on local storage.
  // Serves as the ultimate self-healing fallback for corrupted state variables.
  handleClearCache = () => {
    try {
      localStorage.clear()
      sessionStorage.clear()
    } catch {
      // Proceed to force reload even if storage mechanisms are blocked
    }
    window.location.reload()
  }

  render() {
    const { hasError, error, errorInfo, showDetails } = this.state

    if (!hasError) {
      return this.props.children
    }

    return (
      <div
        role="alert" // Immediately announces the crash state to assistive technologies
        aria-live="assertive"
        className="min-h-screen flex flex-col items-center justify-center bg-[#fdfbf7] px-6 text-center select-none"
      >
        <div className="w-full max-w-md bg-white border border-cream-200 p-8 rounded-2xl shadow-sm space-y-6 animate-fadeUp">

          {/* System Warning Icon */}
          <div
            className="w-12 h-12 rounded-full bg-red-50 text-red-600 flex items-center justify-center mx-auto"
            aria-hidden="true"
          >
            <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
                d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"/>
            </svg>
          </div>

          {/* Branded Error Message */}
          <div className="space-y-2">
            <h1 className="font-serif text-3xl text-ink tracking-tight">Something went wrong</h1>
            <p className="text-xs text-muted leading-relaxed max-w-sm mx-auto">
              An unexpected error interrupted this session. Your files and gallery settings are safe.
            </p>
          </div>

          {/* Dynamic Recovery Control Center */}
          <div className="flex flex-col gap-2 pt-2">
            <button
              type="button"
              onClick={this.handleReload}
              className="w-full py-3 bg-ink text-white rounded-lg text-xs uppercase tracking-widest hover:opacity-90 active:scale-[0.98] transition-all cursor-pointer font-medium font-sans"
            >
              Reload Application
            </button>
            <button
              type="button"
              onClick={this.handleClearCache}
              className="w-full py-2.5 bg-transparent text-xs text-muted hover:text-ink uppercase tracking-widest border border-cream-300 hover:border-cream-400 transition-colors rounded-lg cursor-pointer font-sans"
            >
              Reset Session Cache
            </button>
          </div>

          {/* Dev-Only Diagnostic Accordion */}
          {isDev && error && (
            <div className="pt-4 border-t border-cream-100 text-left space-y-2 select-text font-sans">
              <button
                type="button"
                onClick={() => this.setState((s) => ({ showDetails: !s.showDetails }))}
                className="text-[10px] uppercase tracking-wider text-muted hover:text-ink font-semibold flex items-center gap-1 cursor-pointer focus:outline-none"
                aria-expanded={showDetails} // Informs accessibility tree of state expansion
                aria-controls="error-stack-trace" // Links control trigger to target DOM element [1]
              >
                {showDetails ? 'Hide Stack Trace' : 'Show Stack Trace'}
                <svg
                  className={`w-3.5 h-3.5 transition-transform duration-200 ${showDetails ? 'rotate-180' : ''}`}
                  fill="none" viewBox="0 0 24 24" stroke="currentColor"
                  aria-hidden="true"
                >
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7"/>
                </svg>
              </button>

              {showDetails && (
                <div
                  id="error-stack-trace"
                  className="p-3 bg-red-50/50 border border-red-100 rounded-lg max-h-40 overflow-y-auto text-[10px] font-mono text-red-700 space-y-1.5 leading-relaxed select-text"
                >
                  <p className="font-bold">{error.toString()}</p>
                  {errorInfo?.componentStack && (
                    <pre className="whitespace-pre-wrap font-sans text-red-600">
                      {errorInfo.componentStack}
                    </pre>
                  )}
                </div>
              )}
            </div>
          )}

        </div>
      </div>
    )
  }
}