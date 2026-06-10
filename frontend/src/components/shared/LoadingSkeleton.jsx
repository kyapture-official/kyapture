const LoadingSkeleton = ({ count = 6 }) => {
  return (
    <div className="loading-skeleton-grid">
      {Array.from({ length: count }).map((_, i) => (
        <div key={i} className="skeleton-card" />
      ))}
    </div>
  );
};

export default LoadingSkeleton;