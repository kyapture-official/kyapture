const EmptyState = ({ title = "Nothing here yet", message = "", action }) => {
  return (
    <div className="empty-state">
      <h3>{title}</h3>
      {message && <p>{message}</p>}
      {action && <button onClick={action.onClick}>{action.label}</button>}
    </div>
  );
};

export default EmptyState;