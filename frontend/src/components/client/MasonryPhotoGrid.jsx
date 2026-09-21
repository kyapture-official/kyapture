import PhotoCard from "./PhotoCard";

export default function MasonryPhotoGrid({
  photos,
  token,
  username,
  slug,
  onPhotoClick,
  favorites,
  onToggleFavorite,
}) {
  if (!photos || photos.length === 0) return null;

  return (
    <div className="columns-1 sm:columns-2 md:columns-3 lg:columns-4 gap-4 px-4 sm:px-6 lg:px-8 max-w-7xl mx-auto">
      {photos.map((photo, index) => (
        <PhotoCard
          key={photo.id ?? index}
          photo={photo}
          index={index}
          token={token}
          username={username}
          slug={slug}
          onPhotoClick={onPhotoClick}
          isFavorited={favorites?.has(photo.id)}
          onToggleFavorite={onToggleFavorite}
        />
      ))}
    </div>
  );
}
