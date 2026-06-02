/**
 * Reserved keywords that can NEVER be used as user subdomains
 */
export const RESERVED_SUBDOMAINS = [
  'app', 'www', 'api', 'admin', 'help', 'support', 'billing', 'assets',
  'static', 'mail', 'test', 'dev', 'prod', 'internal', 'portal', 'account',
  'billing', 'security', 'legal', 'terms', 'privacy', 'blog', 'news', 'kaypture'
];

/**
 * Validates and sanitizes username inputs for subdomain compatibility
 * @param {string} username 
 * @returns {{isValid: boolean, error: string | null}}
 */
export const validateSubdomain = (username) => {
  const clean = username.trim().toLowerCase();

  if (!clean) {
    return { isValid: false, error: 'Username/Subdomain is required.' };
  }

  if (clean.length < 3) {
    return { isValid: false, error: 'Subdomain must be at least 3 characters long.' };
  }

  if (clean.length > 20) {
    return { isValid: false, error: 'Subdomain cannot exceed 20 characters.' };
  }

  // Regex: Only lowercase letters, numbers, and hyphens. Cannot start or end with a hyphen, no consecutive hyphens.
  const regex = /^[a-z0-9]+(?:-[a-z0-9]+)*$/;
  if (!regex.test(clean)) {
    return { 
      isValid: false, 
      error: 'Can only contain lowercase letters, numbers, and single hyphens. Cannot start/end with hyphens.' 
    };
  }

  if (RESERVED_SUBDOMAINS.includes(clean)) {
    return { isValid: false, error: 'This subdomain is reserved for system use.' };
  }

  return { isValid: true, error: null };
};

/**
 * Validates basic email formatting
 */
export const validateEmail = (email) => {
  const regex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
  if (!email.trim()) return { isValid: false, error: 'Email address is required.' };
  if (!regex.test(email)) return { isValid: false, error: 'Invalid email address format.' };
  return { isValid: true, error: null };
};