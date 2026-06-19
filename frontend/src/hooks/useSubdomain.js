import {
  createContext,
  useContext,
  useSyncExternalStore,
  useCallback,
  useMemo,
} from 'react'
import { useParams } from 'react-router-dom'
import { subdomainHelper } from '../utils/subdomainHelper'

// ── HOSTNAME NORMALIZER ───────────────────────────────────────────────────────
// Extracts the bare hostname, stripping any port suffix while remaining fully
// safe for standard IPv4, IPv6, and bracketed loopback addresses.
//
// We avoid the raw URL constructor because bare IPv6 addresses (e.g., '::1')
// are invalid inside URL strings without square brackets [::1], causing the
// constructor to throw and fall back to incorrect string-splits.
export function normalizeHostname(host) {
  if (!host || typeof host !== 'string') return null

  const cleanHost = host.toLowerCase().trim()

  // Symmetrical bracketed IPv6 verification
  if (cleanHost.startsWith('[')) {
    const closeBracket = cleanHost.indexOf(']')
    return closeBracket === -1 ? cleanHost : cleanHost.slice(1, closeBracket)
  }

  const colonCount = (cleanHost.match(/:/g) || []).length
  if (colonCount > 1) return cleanHost // Bare IPv6 address — no port to strip

  return cleanHost.split(':')[0] || null
}

// ── SERVER-SIDE REQUEST HOSTNAME CONTEXT ─────────────────────────────────────
export const RequestHostnameContext = createContext(null)

// ── CONVENIENCE PROVIDER ──────────────────────────────────────────────────────
// Wraps your server-side rendering root to normalize the raw host header
// before injecting it into the context tree, preventing port mismatches.
export function RequestHostnameProvider({ hostname, children }) {
  return (
    <RequestHostnameContext.Provider value={normalizeHostname(hostname)}>
      {children}
    </RequestHostnameContext.Provider>
  )
}

// ── STORE SUBSCRIPTION ────────────────────────────────────────────────────────
// window.location.hostname is fixed for the lifetime of the page.
// We return a standard, zero-cost no-op unsubscribe function.
const subscribe = (_onStoreChange) => () => {}

// ── CLIENT SNAPSHOT ───────────────────────────────────────────────────────────
// window.location.hostname never includes a port, but per the URL spec it
// DOES retain brackets for IPv6 literals (e.g. '[::1]'). We run it through
// normalizeHostname so the client snapshot is byte-for-byte consistent with
// the server snapshot — otherwise useSyncExternalStore sees a mismatch on
// hydration, and subdomainHelper.detectSubdomain ends up handling two
// different shapes of the same host depending on render origin.
const getClientSnapshot = () =>
  typeof window !== 'undefined'
    ? normalizeHostname(window.location.hostname)
    : ''

// ── THE HOOK ──────────────────────────────────────────────────────────────────
/**
 * Reactive Subdomain and Tenant Resolver
 *
 * Resolves the active tenant slug from the production DNS subdomain, falling
 * back to the React Router :username path parameter in local development.
 *
 * Hydration Safety (how it works):
 *   useSyncExternalStore accepts three arguments: subscribe, getClientSnapshot,
 *   and getServerSnapshot. During SSR and the very first client paint (hydration),
 *   React calls getServerSnapshot. If that returns the real tenant hostname
 *   (injected via RequestHostnameContext), the pre-rendered HTML and the hydrated
 *   DOM are identical from frame zero — no layout shift, no blank-tenant flash,
 *   no hydration warnings, no SEO damage.
 *
 * @returns {string | null} The resolved tenant slug, or null if unresolvable.
 */
export function useSubdomain() {
  const { username } = useParams()

  // Read the server-injected, normalized hostname from context
  const rawServerHostname = useContext(RequestHostnameContext)

  // Memoized: Ensures we do not re-run normalizations on stable inputs
  const serverHostname = useMemo(
    () => normalizeHostname(rawServerHostname),
    [rawServerHostname]
  )

  // Stable server snapshot reference
  const getServerSnapshot = useCallback(
    () => serverHostname,
    [serverHostname]
  )

  // Synchronously reads window.location.hostname in a tearing-free manner
  const hostname = useSyncExternalStore(
    subscribe,
    getClientSnapshot,
    getServerSnapshot
  )

  // Memoized: Skips redundant calculations on stable hostnames
  const subdomain = useMemo(
    () => (hostname ? subdomainHelper.detectSubdomain(hostname) : null),
    [hostname]
  )

  // Production subdomain takes priority; falls back to path segment in development.
  return subdomain || username || null
}