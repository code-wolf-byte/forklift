import { useState, useEffect, useCallback, useRef } from "react";
import ActivityChart from "./ActivityChart.jsx";

const COLORS = ["#8c1d40", "#3b82f6", "#10b981", "#f59e0b", "#8b5cf6", "#ef4444"];
const SCALE_PRESETS = [7, 14, 30, 90];

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

export default function Leaves({ isDark }) {
  const [filters, setFilters] = useState({
    from_date: daysAgoISO(30),
    to_date: todayISO(),
    role: "",
  });
  const [applied, setApplied] = useState(filters);
  const [activeScale, setActiveScale] = useState(30);
  const [roles, setRoles] = useState([]);
  const [data, setData] = useState(null);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);

  // Chart series state
  const nextIdRef = useRef(2);
  const [series, setSeries] = useState([{ id: 1, type: "all", role: "" }]);
  const [chartDataMap, setChartDataMap] = useState({});

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

  // Fetch paginated list
  useEffect(() => {
    setLoading(true);
    fetch(`/api/admin/server-leaves?${buildQS({ per_page: 25 })}`)
      .then((r) => r.json())
      .then((d) => { setData(d); setLoading(false); })
      .catch(() => setLoading(false));
  }, [buildQS]);

  // Fetch chart data for every series in parallel
  useEffect(() => {
    const base = `from_date=${encodeURIComponent(applied.from_date)}&to_date=${encodeURIComponent(applied.to_date)}`;
    Promise.all(
      series.map((s) => {
        let qs = base;
        if (s.type === "has" && s.role) qs += `&role=${encodeURIComponent(s.role)}`;
        if (s.type === "not" && s.role) qs += `&exclude_role=${encodeURIComponent(s.role)}`;
        return fetch(`/api/admin/server-leaves/chart?${qs}`)
          .then((r) => r.json())
          .then((d) => ({ id: s.id, data: d }))
          .catch(() => ({ id: s.id, data: [] }));
      })
    ).then((results) => {
      const map = {};
      results.forEach((r) => { map[r.id] = r.data; });
      setChartDataMap(map);
    });
  }, [applied, series]);

  const handleScaleClick = (days) => {
    const newFrom = daysAgoISO(days);
    const newTo = todayISO();
    setFilters((f) => ({ ...f, from_date: newFrom, to_date: newTo }));
    setApplied((prev) => ({ ...prev, from_date: newFrom, to_date: newTo }));
    setActiveScale(days);
    setPage(1);
  };

  const handleApply = () => {
    setPage(1);
    setApplied(filters);
  };

  const addSeries = () => {
    if (series.length >= COLORS.length) return;
    setSeries((s) => [...s, { id: nextIdRef.current++, type: "all", role: "" }]);
  };

  const updateSeries = (id, patch) => {
    setSeries((s) => s.map((item) => (item.id === id ? { ...item, ...patch } : item)));
  };

  const removeSeries = (id) => {
    setSeries((s) => s.filter((item) => item.id !== id));
  };

  const datasets = series.map((s, i) => {
    let label;
    if (s.type === "all") label = "All";
    else if (s.type === "has") label = s.role ? `Has: ${s.role}` : "Has role";
    else label = s.role ? `No: ${s.role}` : "No role";
    return { data: chartDataMap[s.id] || [], label, color: COLORS[i % COLORS.length] };
  });

  return (
    <>
      <h2 className="mb-1">Server Leaves</h2>
      <p className="text-muted small mb-3">
        {data ? `${data.total.toLocaleString()} members left in this range.` : "Loading…"}
      </p>

      {/* Filters */}
      <div className="card p-3 mb-3">
        <div className="row g-2 align-items-end flex-wrap">
          <div className="col-auto">
            <label className="form-label small mb-1 fw-semibold">From</label>
            <input
              type="date"
              className="form-control form-control-sm"
              value={filters.from_date}
              onChange={(e) => {
                setFilters((f) => ({ ...f, from_date: e.target.value }));
                setActiveScale(null);
              }}
            />
          </div>
          <div className="col-auto">
            <label className="form-label small mb-1 fw-semibold">To</label>
            <input
              type="date"
              className="form-control form-control-sm"
              value={filters.to_date}
              onChange={(e) => {
                setFilters((f) => ({ ...f, to_date: e.target.value }));
                setActiveScale(null);
              }}
            />
          </div>
          <div className="col-auto">
            <label className="form-label small mb-1 fw-semibold">Scale</label>
            <div className="d-flex gap-1">
              {SCALE_PRESETS.map((d) => (
                <button
                  key={d}
                  className={`btn btn-sm ${activeScale === d ? "btn-maroon text-white" : "btn-outline-secondary"}`}
                  onClick={() => handleScaleClick(d)}
                >
                  {d}d
                </button>
              ))}
            </div>
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

      {/* Chart with series builder */}
      <div className="card p-3 mb-3">
        <p className="small fw-semibold text-muted mb-2">Daily Leaves</p>

        {/* Series builder */}
        <div className="mb-3">
          {series.map((s, i) => (
            <div key={s.id} className="d-flex align-items-center gap-2 mb-2 flex-wrap">
              <span className="chart-series-dot" style={{ background: COLORS[i % COLORS.length] }} />
              <select
                className="form-select form-select-sm w-auto"
                value={s.type}
                onChange={(e) => updateSeries(s.id, { type: e.target.value, role: "" })}
              >
                <option value="all">All members</option>
                <option value="has">Has role</option>
                <option value="not">Does not have role</option>
              </select>
              {s.type !== "all" && (
                <select
                  className="form-select form-select-sm w-auto"
                  style={{ minWidth: 140 }}
                  value={s.role}
                  onChange={(e) => updateSeries(s.id, { role: e.target.value })}
                >
                  <option value="">Select role…</option>
                  {roles.map((r) => (
                    <option key={r.role_name} value={r.role_name}>{r.role_name}</option>
                  ))}
                </select>
              )}
              {series.length > 1 && (
                <button
                  className="btn btn-sm btn-outline-secondary chart-series-remove"
                  onClick={() => removeSeries(s.id)}
                >
                  <i className="fas fa-times" />
                </button>
              )}
            </div>
          ))}
          {series.length < COLORS.length && (
            <button className="btn btn-sm btn-outline-secondary" onClick={addSeries}>
              <i className="fas fa-plus me-1" />Add series
            </button>
          )}
        </div>

        <ActivityChart datasets={datasets} isDark={isDark} />
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
              <p className="text-muted small p-3 mb-0">No leaves in this range.</p>
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
                    <i className="fas fa-sign-out-alt me-1" style={{ color: "#8c1d40" }} />
                    {u.left_at
                      ? new Date(u.left_at).toLocaleDateString("en-US", {
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
