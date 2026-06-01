/**
 * Extracts subdomain from current hostname.
 * e.g. johndoe.kyapture.com -> 'johndoe'
 */
export const getSubdomain = () => {
  const host = window.location.hostname
  const parts = host.split('.')
  if (parts.length >= 3) return parts[0]
  return null
}

export const isClientPortal = () => Boolean(getSubdomain())
