import { useState, useEffect } from "react";

export default function Admin() {
  const [adminUser, setAdminUser] = useState(null);
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch("/api/admin/me")
      .then((r) => {
        if (r.status === 403) {
          window.location.href = "/";
          return null;
        }
        return r.json();
      })
      .then((data) => {
        if (!data) return;
        setAdminUser(data);
        return fetch("/api/admin/stats").then((r) => r.json());
      })
      .then((data) => {
        if (data) setStats(data);
        setLoading(false);
      })
      .catch(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <div className="container py-5 text-center">
        <div
          className="spinner-border"
          role="status"
          style={{ color: "#8c1d40" }}
        >
          <span className="visually-hidden">Loading...</span>
        </div>
      </div>
    );
  }

  return (
    <div className="container py-5">
      <div className="row mb-4">
        <div className="col">
          <h1 style={{ color: "#8c1d40" }}>Admin Panel</h1>
          {adminUser && (
            <p className="text-muted">
              Logged in as <strong>{adminUser.asurite_id}</strong> (
              {adminUser.discord_username})
            </p>
          )}
        </div>
      </div>

      {stats && (
        <div className="row g-3 mb-4">
          <div className="col-md-4">
            <div className="card text-center p-3">
              <h2 style={{ color: "#8c1d40" }}>{stats.total_users}</h2>
              <p className="mb-0 text-muted">Total Users</p>
            </div>
          </div>
          <div className="col-md-4">
            <div className="card text-center p-3">
              <h2 style={{ color: "#8c1d40" }}>{stats.verified_count}</h2>
              <p className="mb-0 text-muted">Verified Users</p>
            </div>
          </div>
          <div className="col-md-4">
            <div className="card text-center p-3">
              <h2 style={{ color: "#8c1d40" }}>{stats.today_verifications}</h2>
              <p className="mb-0 text-muted">Verified Today</p>
            </div>
          </div>
        </div>
      )}

      <div className="alert alert-info" role="alert">
        Admin Panel — more features coming soon.
      </div>
    </div>
  );
}
