// Placeholder tiles shown while a photo set's first page loads. It uses the
// same column breakpoints as PublicMasonryGrid, so the page keeps its height
// and the real grid replaces it without a jump.
const TILE_ASPECTS = ["3 / 2", "2 / 3", "4 / 3", "3 / 2", "1 / 1", "2 / 3", "4 / 3", "3 / 2"];

export default function GallerySkeleton({ count = 8 }) {
  return (
    <div
      className="columns-1 gap-3 sm:columns-2 lg:columns-3 xl:columns-4"
      role="status"
      aria-busy="true"
      aria-label="Loading photos"
    >
      {Array.from({ length: count }, (_, index) => (
        <div
          key={index}
          className="mb-3 w-full break-inside-avoid animate-pulse bg-cream-100"
          style={{ aspectRatio: TILE_ASPECTS[index % TILE_ASPECTS.length] }}
        />
      ))}
      <span className="sr-only">Loading photos…</span>
    </div>
  );
}
