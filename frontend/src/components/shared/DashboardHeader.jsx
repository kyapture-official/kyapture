const DashboardHeader = ({ title, subtitle }) => {
  return (
    <div className="dashboard-header">
      <h1>{title}</h1>
      {subtitle && <p>{subtitle}</p>}
    </div>
  );
};

export default DashboardHeader;