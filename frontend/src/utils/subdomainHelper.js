// Base Domain Configuration (e.g. 'kyapture.com' or 'localhost')
// Resolved and normalized once at module load to prevent redundant execution loops
const APP_DOMAIN = (import.meta.env.VITE_APP_DOMAIN || 'kyapture.com')
  .toLowerCase()
  .trim()

// Subdomains reserved strictly for infrastructure or administrative use [18]
const RESERVED_SUBDOMAINS = new Set([
  'app', 'www', 'api', 'admin', 'mail',
  'ftp', 'cdn', 'static', 'assets', 'auth',
])

// Standard loopback hostnames representing local development setups [18]
const LOCAL_HOSTNAMES = new Set(['localhost', '127.0.0.1', '0.0.0.0', '::1'])

// Strict W3C DNS label validation pattern [18]
// Enforces alphanumeric boundaries, allows hyphens, blocks underscores, and limits labels to 63 chars.
const DNS_LABEL_RE = /^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?$/

// ── PRIVATE SYSTEM HELPERS ───────────────────────────────────────────────────

/**
 * Strips a port from a hostname — IPv6-safe.
 *
 * Handles three shapes:
 *  - 'kroman.localhost:3000' -> 'kroman.localhost'  (regular host, single colon = port)
 *  - '::1'                   -> '::1'                (bare IPv6; location.hostname never carries a port)
 *  - '[::1]:3000' / '[::1]'  -> '::1'                (bracketed IPv6, e.g. from location.host)
 */
const stripPort = (host) => {
  if (host.startsWith('[')) {
    const closeBracket = host.indexOf(']')
    return closeBracket === -1 ? host : host.slice(1, closeBracket)
  }

  const colonCount = (host.match(/:/g) || []).length
  if (colonCount > 1) return host // bare IPv6 address — nothing to strip

  return host.split(':')[0]
}

/**
 * Encodes each segment of a URL path independently, preserving '/' separators [18].
 * Prevents slugs like 'galleries/wedding' from being corrupted into 'galleries%2Fwedding' [18].
 */
const encodePathSegments = (path) =>
  path
    .split('/')
    .map((segment) => encodeURIComponent(segment))
    .join('/')

// ── PUBLIC API EXPORTS ───────────────────────────────────────────────────────

export const subdomainHelper = Object.freeze({
  /**
   * WHAT: Tenant Subdomain Extractor
   * WHY:  Parses browser hostnames to isolate tenant subdomains [18].
   *       Returns null for root, reserved, multi-level, or malformed DNS labels.
   *
   * @param {string} hostname - Target host string (handles both host and hostname)
   * @returns {string | null}
   */
  detectSubdomain(hostname) {
    if (!hostname || typeof hostname !== 'string') return null

    const cleanHost = stripPort(hostname.toLowerCase().trim())

    // Case 1: Exact root domain match (no subdomain present)
    if (cleanHost === APP_DOMAIN) return null

    // Case 2: Subdomain suffix match
    if (cleanHost.endsWith(`.${APP_DOMAIN}`)) {
      const subdomain = cleanHost.slice(0, -(APP_DOMAIN.length + 1))

      if (!subdomain) return null
      if (subdomain.includes('.')) return null
      if (RESERVED_SUBDOMAINS.has(subdomain)) return null
      if (!DNS_LABEL_RE.test(subdomain)) return null

      return subdomain
    }

    return null
  },

  /**
   * WHAT: Tenant URL Builder
   * WHY:  Generates fully-qualified public client portal links.
   *       Validates the username against the exact same identity rules
   *       detectSubdomain enforces, guaranteeing that they are true mathematical inverses [18].
   *
   * @param {string} username              - Tenant username / subdomain handle
   * @param {string} slug                  - Gallery or page slug (may contain '/' path separators)
   * @param {string} [hostname]            - Override; defaults to window.location.hostname
   * @param {string} [protocol]            - Override; defaults to window.location.protocol
   * @returns {string}                       Fully-qualified URL, or '' on invalid input
   */
  buildPublicURL(
    username,
    slug,
    // SSR Fix: Check typeof window defensively to prevent call-time crashes on the server [26]
    hostname = typeof window !== 'undefined' ? window.location.hostname : 'localhost',
    protocol = typeof window !== 'undefined' ? window.location.protocol : 'https:',
  ) {
    if (!username || typeof username !== 'string') return ''
    if (!slug || typeof slug !== 'string') return ''

    const cleanUsername = username.trim().toLowerCase()
    const cleanSlug = slug.trim()

    if (!cleanUsername || !cleanSlug) return ''

    // Symmetrical Identity Rule validation check [18]
    if (RESERVED_SUBDOMAINS.has(cleanUsername)) return ''
    if (!DNS_LABEL_RE.test(cleanUsername)) return ''

    const cleanHost = stripPort(hostname.toLowerCase())
    const isLocal = LOCAL_HOSTNAMES.has(cleanHost)

    const encodedSlug = encodePathSegments(cleanSlug)

    if (isLocal) {
      // Local development fallback pathing [14]
      return `/g/${cleanUsername}/${encodedSlug}`
    }

    const safeProtocol = protocol.endsWith(':') ? protocol : `${protocol}:`

    return `${safeProtocol}//${cleanUsername}.${APP_DOMAIN}/${encodedSlug}`
  },
})