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

export default function Dashboard({ stats }) {
  if (!stats) {
    return (
      <div className="text-center py-5">
        <div className="spinner-border" role="status" style={{ color: "#8c1d40" }}>
          <span className="visually-hidden">Loading…</span>
        </div>
      </div>
    );
  }

  return (
    <>
      <h2 className="mb-1">Overview</h2>
      <p className="text-muted small mb-4">Verification stats across all members.</p>
      <div className="row g-3">
        <StatCard value={stats.total_users} label="Total Members" icon="fa-users" />
        <StatCard value={stats.verified_count} label="Verified" icon="fa-user-check" />
        <StatCard value={stats.today_verifications} label="Verified Today" icon="fa-calendar-check" />
      </div>
    </>
  );
}
