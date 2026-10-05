/**
 * Applies the same optimistic heart transition used by the client gallery.
 * Keeping this Set transition pure makes the visible toggle and rollback
 * behavior independently testable without replacing the browser or API.
 */
export function nextFavoriteIds(currentIds, photoId, wasFavorited) {
  const next = new Set(currentIds);
  if (wasFavorited) next.delete(photoId);
  else next.add(photoId);
  return next;
}
