import { useState, useEffect, useCallback } from 'react';
import { galleriesApi } from '../api/galleriesApi';

/**
 * WHAT: Advanced, Aligned Gallery State Hook
 * WHY: Corrects optimistic state exposure, handles safe query parsing, and prevents stale error rendering.
 * HOW: Wraps galleriesApi, extracting clean error strings and exporting setGalleries.
 * WHERE: frontend/src/hooks/useGalleries.js
 */
export function useGalleries(initialParams = {}) {
  const [galleries, setGalleries] = useState([]);
  const [loading, setLoading]     = useState(true);
  const [error, setError]         = useState(null);
  
  // Track search, sort, and pagination filters
  const [params, setParams]       = useState(initialParams);

  const load = useCallback((queryParams = params) => {
    setLoading(true);
    setError(null); // Clear stale errors immediately on cycle start

    galleriesApi.list(queryParams)
      .then((r) => {
        // DRF paginated structures contain a results key; fallback to raw array
        const list = r.data.results || r.data;
        setGalleries(list);
      })
      .catch((e) => {
        // Sanitize raw Axios error objects to safe human-readable strings
        const errorMsg = e.response?.data?.error || e.message || 'Failed to sync galleries from server.';
        setError(errorMsg);
      })
      .finally(() => setLoading(false));
  }, [params]);

  // Sync state automatically whenever tracking query parameters change
  useEffect(() => { 
    load(); 
  }, [load]);

  return { 
    galleries, 
    setGalleries, // Required for Optimistic UI updates in your GalleriesPage [1.2.2]
    loading, 
    error, 
    reload: load, // Kept your legacy alias for backward compatibility
    params,
    setParams     // Allows UI to update parameters dynamically (e.g. searching)
  };
}