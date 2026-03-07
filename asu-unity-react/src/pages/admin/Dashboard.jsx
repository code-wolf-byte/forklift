import { useState, useEffect } from "react";

const todayISO = () => new Date().toISOString().slice(0, 10);
const monthStartISO = () => {
  const d = new Date();
  d.setDate(1);
  return d.toISOString().slice(0, 10);
};

function StatCard({ value, label, icon }) {
  return (
    <div className="col-sm-6 col-xl-4">
      <div className="card p-4 h-100">
        <div className="d-flex align-items-center gap-3">
          <div
            style={{
              width: 48,
              height: 48,
              borderRadius: 12,
              background: "rgba(140,29,64,0.12)",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              flexShrink: 0,
            }}
          >
            <i className={`fas ${icon} fa-lg`} style={{ color: "#8c1d40" }} />
          </div>
          <div>
            <div style={{ fontSize: 28, fontWeight: 700, lineHeight: 1, color: "#8c1d40" }}>
              {value ?? "—"}
            </div>
            <div className="text-muted small mt-1">{label}</div>
          </div>
        </div>
      </div>
    </div>
  );
}

export default function Dashboard() {
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(true);
  const [fromDate, setFromDate] = useState(monthStartISO());
  const [toDate, setToDate] = useState(todayISO());
  const [applied, setApplied] = useState({ from: monthStartISO(), to: todayISO() });

  useEffect(() => {
    setLoading(true);
    fetch(`/api/admin/stats?from_date=${encodeURIComponent(applied.from)}&to_date=${encodeURIComponent(applied.to)}`)
      .then((r) => r.json())
      .then((d) => { setStats(d); setLoading(false); })
      .catch(() => setLoading(false));
  }, [applied]);

  const handleApply = () => setApplied({ from: fromDate, to: toDate });

  if (loading && !stats) {
    return (
      <div className="text-center py-5">
        <div className="spinner-border" role="status" style={{ color: "#8c1d40" }}>
          <span className="visually-hidden">Loading…</span>
        </div>
      </div>
    );
  }

  const retentionDisplay =
    stats?.retention_rate != null ? `${stats.retention_rate}%` : "—";

  return (
    <>
      <h2 className="mb-1">Overview</h2>
      <p className="text-muted small mb-4">Verification stats across all members.</p>

      {/* All-time stats */}
      <div className="row g-3 mb-4">
        <StatCard value={stats?.total_users} label="Total Members" icon="fa-users" />
        <StatCard value={stats?.verified_count} label="Verified" icon="fa-user-check" />
        <StatCard value={stats?.today_verifications} label="Verified Today" icon="fa-calendar-check" />
      </div>

      {/* Period stats */}
      <div className="d-flex align-items-center justify-content-between mb-3 flex-wrap gap-2">
        <h5 className="mb-0">Period Stats</h5>
        <div className="d-flex align-items-end gap-2 flex-wrap">
          <div>
            <label className="form-label small mb-1 fw-semibold">From</label>
            <input
              type="date"
              className="form-control form-control-sm"
              value={fromDate}
              onChange={(e) => setFromDate(e.target.value)}
            />
          </div>
          <div>
            <label className="form-label small mb-1 fw-semibold">To</label>
            <input
              type="date"
              className="form-control form-control-sm"
              value={toDate}
              onChange={(e) => setToDate(e.target.value)}
            />
          </div>
          <button className="btn btn-sm btn-maroon text-white" onClick={handleApply} disabled={loading}>
            Apply
          </button>
        </div>
      </div>

      <div className="row g-3">
        <StatCard value={stats?.verified_leaves} label="Verified Leaves" icon="fa-sign-out-alt" />
        <StatCard value={stats?.verified_at_end} label="Verified Users" icon="fa-users" />
        <StatCard value={retentionDisplay} label="Retention Rate" icon="fa-chart-line" />
      </div>
    </>
  );
}
