import { useState, useEffect, useCallback } from "react";
import ActivityChart from "./ActivityChart.jsx";

const todayISO = () => new Date().toISOString().slice(0, 10);
const daysAgoISO = (n) => {
  const d = new Date();
  d.setDate(d.getDate() - n);
  return d.toISOString().slice(0, 10);
};

function Avatar({ userId, avatarHash, username }) {
  const src =
    userId && avatarHash
      ? `https://cdn.discordapp.com/avatars/${userId}/${avatarHash}.png?size=64`
      : null;
  const initial = (username || "?")[0].toUpperCase();

  return src ? (
    <img
      src={src}
      alt={username}
      style={{ width: 36, height: 36, borderRadius: "50%", objectFit: "cover", flexShrink: 0 }}
      onError={(e) => { e.target.style.display = "none"; }}
    />
  ) : (
    <div style={{
      width: 36, height: 36, borderRadius: "50%", background: "#8c1d40",
      color: "#fff", display: "flex", alignItems: "center", justifyContent: "center",
      fontWeight: 700, fontSize: 14, flexShrink: 0,
    }}>
      {initial}
    </div>
  );
}

export default function ServerJoins({ isDark }) {
  const [filters, setFilters] = useState({
    from_date: daysAgoISO(30),
    to_date: todayISO(),
    role: "",
  });
  const [applied, setApplied] = useState(filters);
  const [roles, setRoles] = useState([]);
  const [data, setData] = useState(null);
  const [chart, setChart] = useState(null);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);

  // Load role options once
  useEffect(() => {
    fetch("/api/admin/roles")
      .then((r) => r.json())
      .then(setRoles)
      .catch(() => {});
  }, []);

  const buildQS = useCallback(
    (extra = {}) => {
      const p = { ...applied, page, ...extra };
      return Object.entries(p)
        .filter(([, v]) => v !== "" && v != null)
        .map(([k, v]) => `${k}=${encodeURIComponent(v)}`)
        .join("&");
    },
    [applied, page]
  );

  // Fetch list
  useEffect(() => {
    setLoading(true);
    fetch(`/api/admin/server-joins?${buildQS({ per_page: 25 })}`)
      .then((r) => r.json())
      .then((d) => { setData(d); setLoading(false); })
      .catch(() => setLoading(false));
  }, [buildQS]);

  // Fetch chart (independent of page)
  useEffect(() => {
    const qs = Object.entries(applied)
      .filter(([, v]) => v !== "")
      .map(([k, v]) => `${k}=${encodeURIComponent(v)}`)
      .join("&");
    fetch(`/api/admin/server-joins/chart?${qs}`)
      .then((r) => r.json())
      .then(setChart)
      .catch(() => setChart([]));
  }, [applied]);

  const handleApply = () => {
    setPage(1);
    setApplied(filters);
  };

  return (
    <>
      <h2 className="mb-1">Server Joins</h2>
      <p className="text-muted small mb-3">
        {data ? `${data.total.toLocaleString()} members joined in this range.` : "Loading…"}
      </p>

      {/* Filters */}
      <div className="card p-3 mb-3">
        <div className="row g-2 align-items-end">
          <div className="col-auto">
            <label className="form-label small mb-1 fw-semibold">From</label>
            <input
              type="date"
              className="form-control form-control-sm"
              value={filters.from_date}
              onChange={(e) => setFilters((f) => ({ ...f, from_date: e.target.value }))}
            />
          </div>
          <div className="col-auto">
            <label className="form-label small mb-1 fw-semibold">To</label>
            <input
              type="date"
              className="form-control form-control-sm"
              value={filters.to_date}
              onChange={(e) => setFilters((f) => ({ ...f, to_date: e.target.value }))}
            />
          </div>
          <div className="col-auto">
            <label className="form-label small mb-1 fw-semibold">Role</label>
            <select
              className="form-select form-select-sm"
              style={{ minWidth: 160 }}
              value={filters.role}
              onChange={(e) => setFilters((f) => ({ ...f, role: e.target.value }))}
            >
              <option value="">All roles</option>
              {roles.map((r) => (
                <option key={r.role_name} value={r.role_name}>
                  {r.role_name} ({r.count})
                </option>
              ))}
            </select>
          </div>
          <div className="col-auto">
            <button className="btn btn-sm btn-maroon text-white" onClick={handleApply}>
              Apply
            </button>
          </div>
        </div>
      </div>

      {/* Chart */}
      <div className="card p-3 mb-3">
        <p className="small fw-semibold text-muted mb-2">Daily Joins</p>
        <ActivityChart data={chart} label="Joins" isDark={isDark} />
      </div>

      {/* List */}
      {loading ? (
        <div className="text-center py-4">
          <div className="spinner-border spinner-border-sm" role="status" style={{ color: "#8c1d40" }}>
            <span className="visually-hidden">Loading…</span>
          </div>
        </div>
      ) : (
        <>
          <div className="card p-0" style={{ overflow: "hidden" }}>
            {!data?.users?.length ? (
              <p className="text-muted small p-3 mb-0">No joins in this range.</p>
            ) : (
              data.users.map((u, i) => (
                <div
                  key={u.id}
                  className="d-flex align-items-center gap-3 px-3 py-2"
                  style={{ borderBottom: i < data.users.length - 1 ? "1px solid var(--join-divider,#e3e5e8)" : "none" }}
                >
                  <Avatar userId={u.discord_user_id} avatarHash={u.discord_avatar} username={u.discord_username} />
                  <div className="flex-grow-1 overflow-hidden">
                    <div className="fw-semibold small text-truncate">{u.discord_username || "—"}</div>
                    <div className="text-muted" style={{ fontSize: 12 }}>{u.asurite_id}</div>
                  </div>
                  <div className="text-muted small text-nowrap flex-shrink-0">
                    <i className="fas fa-sign-in-alt me-1" style={{ color: "#8c1d40" }} />
                    {u.joined_at
                      ? new Date(u.joined_at).toLocaleDateString("en-US", {
                          timeZone: "America/Phoenix", month: "short", day: "numeric", year: "numeric",
                        })
                      : "—"}
                  </div>
                </div>
              ))
            )}
          </div>

          {data?.pages > 1 && (
            <div className="d-flex align-items-center gap-3 mt-3">
              <button className="btn btn-sm btn-outline-secondary" disabled={page === 1} onClick={() => setPage((p) => p - 1)}>
                <i className="fas fa-chevron-left me-1" />Prev
              </button>
              <span className="text-muted small">Page {page} of {data.pages}</span>
              <button className="btn btn-sm btn-outline-secondary" disabled={page === data.pages} onClick={() => setPage((p) => p + 1)}>
                Next<i className="fas fa-chevron-right ms-1" />
              </button>
            </div>
          )}
        </>
      )}
    </>
  );
}
