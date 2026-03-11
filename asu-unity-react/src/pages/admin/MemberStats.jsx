import { useState, useEffect } from "react";

const todayISO = () => new Date().toISOString().slice(0, 10);
const monthStartISO = () => {
  const d = new Date();
  d.setDate(1);
  return d.toISOString().slice(0, 10);
};

const CAT_META = {
  "Academic Level": { icon: "fa-graduation-cap", color: "#8c1d40" },
  College:          { icon: "fa-university",      color: "#3b82f6" },
  Campus:           { icon: "fa-map-marker-alt",  color: "#10b981" },
  Residency:        { icon: "fa-home",            color: "#f59e0b" },
  Special:          { icon: "fa-star",            color: "#8b5cf6" },
};

function RoleBar({ name, count, total }) {
  const pct = total > 0 ? Math.round((count / total) * 100) : 0;
  return (
    <div className="mb-2">
      <div className="d-flex justify-content-between small mb-1">
        <span className="text-truncate me-2" title={name}>{name}</span>
        <span className="text-muted flex-shrink-0">
          {count.toLocaleString()} <span className="opacity-50">({pct}%)</span>
        </span>
      </div>
      <div className="progress member-stat-bar">
        <div
          className="progress-bar"
          style={{ width: `${pct}%`, background: "#8c1d40", transition: "width 0.4s ease" }}
        />
      </div>
    </div>
  );
}

function CategoryCard({ cat, total }) {
  const meta = CAT_META[cat.name] || { icon: "fa-tag", color: "#8c1d40" };
  const coveragePct = total > 0 ? Math.round((cat.users_with / total) * 100) : 0;
  const activeRoles = cat.roles.filter((r) => r.count > 0);

  return (
    <div className="col-sm-6 col-xl-4">
      <div className="card stat-card h-100">
        <div className="stat-card-accent" style={{ background: meta.color }} />
        <div className="p-3">
          {/* Header */}
          <div className="d-flex align-items-center gap-2 mb-3">
            <div
              className="stat-card-icon"
              style={{ background: `${meta.color}18`, color: meta.color }}
            >
              <i className={`fas ${meta.icon} fa-sm`} />
            </div>
            <div className="flex-grow-1 overflow-hidden">
              <h6 className="mb-0 text-truncate">{cat.name} Roles</h6>
              <div className="small text-muted">
                {cat.users_with.toLocaleString()} of {total.toLocaleString()} have this
              </div>
            </div>
            <span
              className="badge rounded-pill flex-shrink-0"
              style={{ background: meta.color, fontSize: 12 }}
            >
              {coveragePct}%
            </span>
          </div>

          {/* Coverage bar */}
          <div className="progress mb-1" style={{ height: 8, borderRadius: 6 }}>
            <div
              className="progress-bar"
              style={{ width: `${coveragePct}%`, background: meta.color, borderRadius: 6, transition: "width 0.5s ease" }}
            />
          </div>
          <div className="d-flex justify-content-between small text-muted mb-3">
            <span>{cat.users_with.toLocaleString()} have</span>
            <span>{cat.users_missing.toLocaleString()} missing</span>
          </div>

          {/* Role breakdown */}
          {activeRoles.length > 0 ? (
            <div className="member-stat-roles">
              {activeRoles.map((r) => (
                <RoleBar key={r.role} name={r.role} count={r.count} total={total} />
              ))}
            </div>
          ) : (
            <p className="text-muted small mb-0 fst-italic">No role data for this period.</p>
          )}
        </div>
      </div>
    </div>
  );
}

function SummaryCard({ value, label, icon, color }) {
  return (
    <div className="col-sm-4">
      <div className="card stat-card">
        <div className="stat-card-accent" style={{ background: color || "#8c1d40" }} />
        <div className="p-3 d-flex align-items-center gap-3">
          <div
            className="stat-card-icon"
            style={{ background: `${color || "#8c1d40"}18`, color: color || "#8c1d40" }}
          >
            <i className={`fas ${icon} fa-lg`} />
          </div>
          <div>
            <div className="stat-value">{value ?? "—"}</div>
            <div className="text-muted small mt-1">{label}</div>
          </div>
        </div>
      </div>
    </div>
  );
}

export default function MemberStats() {
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(true);
  const [fromDate, setFromDate] = useState("");
  const [toDate, setToDate] = useState("");
  const [applied, setApplied] = useState({ from: "", to: "" });

  useEffect(() => {
    setLoading(true);
    const params = new URLSearchParams();
    if (applied.from) params.set("from_date", applied.from);
    if (applied.to) params.set("to_date", applied.to);
    fetch(`/api/admin/member-stats?${params}`)
      .then((r) => r.json())
      .then((d) => { setStats(d); setLoading(false); })
      .catch(() => setLoading(false));
  }, [applied]);

  const handleApply = () => setApplied({ from: fromDate, to: toDate });

  const handlePreset = (preset) => {
    if (preset === "alltime") {
      setFromDate(""); setToDate("");
      setApplied({ from: "", to: "" });
    } else if (preset === "month") {
      const f = monthStartISO(), t = todayISO();
      setFromDate(f); setToDate(t);
      setApplied({ from: f, to: t });
    } else if (preset === "today") {
      const t = todayISO();
      setFromDate(t); setToDate(t);
      setApplied({ from: t, to: t });
    }
  };

  if (loading && !stats) {
    return (
      <div className="text-center py-5">
        <div className="spinner-border" role="status" style={{ color: "#8c1d40" }}>
          <span className="visually-hidden">Loading…</span>
        </div>
      </div>
    );
  }

  const total = stats?.total_verified ?? 0;
  const inServer = stats?.currently_in_server ?? 0;
  const left = stats?.left_server ?? 0;
  const periodLabel = applied.from || applied.to
    ? `${applied.from || "start"} → ${applied.to || "today"}`
    : "All time";

  // Members with all 4 required categories
  const requiredCats = ["Academic Level", "College", "Campus", "Residency"];
  const withAllRequired = stats?.categories
    ? requiredCats.reduce((min, name) => {
        const cat = stats.categories.find((c) => c.name === name);
        return cat ? Math.min(min, cat.users_with) : min;
      }, total)
    : 0;

  return (
    <>
      <h2 className="mb-1">Member Stats</h2>
      <p className="text-muted small mb-4">
        Role coverage for verified members — mirrors the{" "}
        <code>get_studet_data.py</code> report.
      </p>

      {/* Filters */}
      <div className="card p-3 mb-4">
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
          <button
            className="btn btn-sm btn-maroon text-white"
            onClick={handleApply}
            disabled={loading}
          >
            Apply
          </button>
          <div className="vr mx-1 align-self-center" style={{ height: 24 }} />
          <button className="btn btn-sm btn-outline-secondary" onClick={() => handlePreset("today")}>
            Today
          </button>
          <button className="btn btn-sm btn-outline-secondary" onClick={() => handlePreset("month")}>
            This Month
          </button>
          <button className="btn btn-sm btn-outline-secondary" onClick={() => handlePreset("alltime")}>
            All Time
          </button>
        </div>
        {(applied.from || applied.to) && (
          <div className="text-muted small mt-2">
            Showing verified members: <strong>{periodLabel}</strong>
          </div>
        )}
      </div>

      {/* Summary cards */}
      <div className="row g-3 mb-4">
        <SummaryCard
          value={total.toLocaleString()}
          label="Verified Members"
          icon="fa-user-check"
          color="#8c1d40"
        />
        <SummaryCard
          value={inServer.toLocaleString()}
          label="Currently in Server"
          icon="fa-users"
          color="#10b981"
        />
        <SummaryCard
          value={withAllRequired.toLocaleString()}
          label="Have All 4 Required Roles"
          icon="fa-shield-alt"
          color="#3b82f6"
        />
      </div>

      {/* Role category cards */}
      {loading ? (
        <div className="text-center py-4">
          <div className="spinner-border spinner-border-sm" role="status" style={{ color: "#8c1d40" }}>
            <span className="visually-hidden">Loading…</span>
          </div>
        </div>
      ) : (
        <div className="row g-3">
          {stats?.categories?.map((cat) => (
            <CategoryCard key={cat.name} cat={cat} total={total} />
          ))}
        </div>
      )}
    </>
  );
}
