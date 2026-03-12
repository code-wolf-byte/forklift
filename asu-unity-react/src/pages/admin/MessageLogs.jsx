import { useState, useEffect, useCallback } from "react";
import RoleFilter from "./RoleFilter.jsx";

// ── Constants ──────────────────────────────────────────────────────────────────

const DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
const HOURS = Array.from({ length: 24 }, (_, i) => i);

const todayISO = () => new Date().toISOString().slice(0, 10);
const daysAgoISO = (n) => {
  const d = new Date();
  d.setDate(d.getDate() - n);
  return d.toISOString().slice(0, 10);
};
const monthStartISO = () => {
  const d = new Date();
  d.setDate(1);
  return d.toISOString().slice(0, 10);
};

function fmtHour(h) {
  if (h === 0) return "12a";
  if (h === 12) return "12p";
  return h < 12 ? `${h}a` : `${h - 12}p`;
}

function fmtDate(isoStr) {
  if (!isoStr) return "—";
  try {
    return new Date(isoStr).toLocaleString("en-US", {
      timeZone: "America/Phoenix",
      month: "short", day: "numeric", year: "numeric",
      hour: "2-digit", minute: "2-digit",
    });
  } catch { return isoStr; }
}

// ── Heatmap ───────────────────────────────────────────────────────────────────

function Heatmap({ cells, total, loading }) {
  if (loading) {
    return (
      <div className="text-center py-5">
        <div className="spinner-border spinner-border-sm" role="status" style={{ color: "#8c1d40" }}>
          <span className="visually-hidden">Loading…</span>
        </div>
      </div>
    );
  }

  if (!cells?.length || total === 0) {
    return (
      <div className="heatmap-empty">
        No message data for the selected filters.
      </div>
    );
  }

  // Build a lookup: counts[dow][hour]
  const lookup = {};
  let maxCount = 0;
  for (const c of cells) {
    if (!lookup[c.dow]) lookup[c.dow] = {};
    lookup[c.dow][c.hour] = c.count;
    if (c.count > maxCount) maxCount = c.count;
  }

  const cellColor = (count) => {
    if (!count) return undefined;
    const intensity = Math.pow(count / maxCount, 0.5); // sqrt scale looks better
    return `rgba(140,29,64,${(0.08 + intensity * 0.88).toFixed(2)})`;
  };

  return (
    <div className="heatmap-wrapper">
      <div className="heatmap-grid">
        {/* Corner + hour labels */}
        <div className="heatmap-corner" />
        {HOURS.map((h) => (
          <div key={h} className="heatmap-hour-label">{fmtHour(h)}</div>
        ))}

        {/* Day rows */}
        {DAYS.map((day, dow) => (
          <>
            <div key={`label-${dow}`} className="heatmap-day-label">{day}</div>
            {HOURS.map((h) => {
              const count = lookup[dow]?.[h] ?? 0;
              return (
                <div
                  key={`${dow}-${h}`}
                  className="heatmap-cell"
                  style={{ background: cellColor(count) }}
                  title={`${day} ${fmtHour(h)} — ${count.toLocaleString()} message${count !== 1 ? "s" : ""}`}
                />
              );
            })}
          </>
        ))}
      </div>

      {/* Legend */}
      <div className="heatmap-legend">
        <span className="text-muted small">Less</span>
        <div className="heatmap-legend-scale">
          {[0, 0.2, 0.4, 0.65, 0.85, 1].map((v) => (
            <div
              key={v}
              className="heatmap-legend-swatch"
              style={{ background: v === 0 ? "rgba(140,29,64,0.06)" : `rgba(140,29,64,${(0.08 + v * 0.88).toFixed(2)})` }}
            />
          ))}
        </div>
        <span className="text-muted small">More</span>
        <span className="text-muted small ms-3">
          {total.toLocaleString()} total messages
        </span>
      </div>
    </div>
  );
}

// ── Export table ──────────────────────────────────────────────────────────────

function ExportTable({ data, page, setPage, loading }) {
  if (loading && !data) {
    return (
      <div className="text-center py-5">
        <div className="spinner-border spinner-border-sm" role="status" style={{ color: "#8c1d40" }}>
          <span className="visually-hidden">Loading…</span>
        </div>
      </div>
    );
  }

  const rows = data?.rows ?? [];

  return (
    <>
      <div className="card p-0" style={{ overflow: "hidden" }}>
        {!rows.length ? (
          <p className="text-muted small p-3 mb-0">No messages match the current filters.</p>
        ) : (
          <div className="table-responsive">
            <table className="table table-hover mb-0" style={{ fontSize: 13 }}>
              <thead>
                <tr>
                  <th className="ps-3">Time (AZ)</th>
                  <th>Channel</th>
                  <th>User</th>
                  <th>ASURITE</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={r.message_id}>
                    <td className="ps-3 align-middle text-muted small text-nowrap">
                      {fmtDate(r.sent_at)}
                    </td>
                    <td className="align-middle">
                      <span className="fw-semibold small">#{r.channel_name || r.channel_id}</span>
                    </td>
                    <td className="align-middle text-muted small text-truncate" style={{ maxWidth: 180 }}>
                      {r.discord_username || (
                        <span className="fst-italic opacity-50">{r.discord_user_id}</span>
                      )}
                    </td>
                    <td className="align-middle text-muted small">
                      {r.asurite_id || "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {data?.pages > 1 && (
        <div className="d-flex align-items-center gap-3 mt-3">
          <button
            className="btn btn-sm btn-outline-secondary"
            disabled={page === 1}
            onClick={() => setPage((p) => p - 1)}
          >
            <i className="fas fa-chevron-left me-1" />Prev
          </button>
          <span className="text-muted small">
            Page {page} of {data.pages}
            <span className="ms-2 opacity-50">({data.total.toLocaleString()} total)</span>
          </span>
          <button
            className="btn btn-sm btn-outline-secondary"
            disabled={page === data.pages}
            onClick={() => setPage((p) => p + 1)}
          >
            Next<i className="fas fa-chevron-right ms-1" />
          </button>
        </div>
      )}
    </>
  );
}

// ── Backfill panel ────────────────────────────────────────────────────────────

function BackfillPanel({ onClose }) {
  const [status, setStatus] = useState(null);
  const [triggering, setTriggering] = useState(false);

  const fetchStatus = useCallback(() => {
    fetch("/api/admin/message-logs/backfill/status")
      .then((r) => r.json())
      .then(setStatus)
      .catch(() => {});
  }, []);

  useEffect(() => {
    fetchStatus();
    const id = setInterval(fetchStatus, 4000);
    return () => clearInterval(id);
  }, [fetchStatus]);

  const handleStart = () => {
    setTriggering(true);
    fetch("/api/admin/message-logs/backfill", { method: "POST" })
      .then((r) => r.json())
      .then(() => fetchStatus())
      .finally(() => setTriggering(false));
  };

  const STATUS_COLORS = { done: "#10b981", running: "#3b82f6", failed: "#ef4444", pending: "#6c757d" };

  return (
    <div className="card p-3 mb-4">
      <div className="d-flex align-items-start justify-content-between mb-3">
        <div>
          <h6 className="mb-1">Historical Backfill</h6>
          <p className="text-muted small mb-0">
            Fetches up to 1 year of message metadata from all text channels.
            No message content is stored.
          </p>
        </div>
        <button className="btn btn-sm btn-outline-secondary" onClick={onClose}>
          <i className="fas fa-times" />
        </button>
      </div>

      {status && (
        <div className="d-flex align-items-center gap-3 mb-3 flex-wrap">
          <span className="small">
            <strong>{status.total_messages_logged?.toLocaleString()}</strong> messages logged
          </span>
          <span className="small text-muted">
            {status.channels_done}/{status.channels_total} channels done
          </span>
          {status.backfill_running && (
            <span className="badge" style={{ background: "#3b82f6" }}>
              <i className="fas fa-sync fa-spin me-1" style={{ fontSize: 10 }} />Running
            </span>
          )}
        </div>
      )}

      <button
        className="btn btn-sm btn-maroon text-white"
        onClick={handleStart}
        disabled={triggering || status?.backfill_running}
        style={{ alignSelf: "flex-start" }}
      >
        {status?.backfill_running ? "Backfill running…" : "Start Backfill"}
      </button>

      {status?.channels?.length > 0 && (
        <div className="mt-3" style={{ maxHeight: 220, overflowY: "auto" }}>
          <table className="table table-sm mb-0" style={{ fontSize: 12 }}>
            <thead>
              <tr>
                <th>Channel</th>
                <th>Status</th>
                <th>Messages</th>
              </tr>
            </thead>
            <tbody>
              {status.channels.map((ch) => (
                <tr key={ch.channel_id}>
                  <td>#{ch.channel_name || ch.channel_id}</td>
                  <td>
                    <span style={{ color: STATUS_COLORS[ch.status] ?? "#6c757d", fontWeight: 600 }}>
                      {ch.status}
                    </span>
                    {ch.error && (
                      <span className="text-danger ms-1" title={ch.error}>⚠</span>
                    )}
                  </td>
                  <td>{ch.messages_fetched?.toLocaleString() ?? "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

// ── Main component ────────────────────────────────────────────────────────────

const PRESETS = [
  { label: "7d",  days: 7 },
  { label: "30d", days: 30 },
  { label: "90d", days: 90 },
  { label: "1y",  days: 365 },
];

export default function MessageLogs() {
  const [tab, setTab] = useState("heatmap");
  const [showBackfill, setShowBackfill] = useState(false);

  // Shared filter state
  const [fromDate, setFromDate] = useState(daysAgoISO(30));
  const [toDate, setToDate] = useState(todayISO());
  const [hasRoles, setHasRoles] = useState([]);
  const [notRoles, setNotRoles] = useState([]);
  const [activePreset, setActivePreset] = useState(30);

  // Applied (fetched) state
  const [applied, setApplied] = useState({
    from: daysAgoISO(30), to: todayISO(), hasRoles: [], notRoles: [],
  });

  // Data
  const [roles, setRoles] = useState([]);
  const [heatmapData, setHeatmapData] = useState(null);
  const [heatmapLoading, setHeatmapLoading] = useState(true);
  const [exportData, setExportData] = useState(null);
  const [exportLoading, setExportLoading] = useState(false);
  const [exportPage, setExportPage] = useState(1);

  // Load selectors once
  useEffect(() => {
    fetch("/api/admin/roles").then((r) => r.json()).then(setRoles).catch(() => {});
  }, []);

  // Build query string from applied state
  const buildQS = useCallback((extra = {}) => {
    const p = new URLSearchParams();
    if (applied.from) p.set("from_date", applied.from);
    if (applied.to)   p.set("to_date", applied.to);
    applied.hasRoles.forEach((r) => p.append("role", r));
    applied.notRoles.forEach((r) => p.append("exclude_role", r));
    Object.entries(extra).forEach(([k, v]) => p.set(k, v));
    return p.toString();
  }, [applied]);

  // Fetch heatmap whenever applied filters change
  useEffect(() => {
    setHeatmapLoading(true);
    fetch(`/api/admin/message-logs/heatmap?${buildQS()}`)
      .then((r) => r.json())
      .then((d) => { setHeatmapData(d); setHeatmapLoading(false); })
      .catch(() => setHeatmapLoading(false));
  }, [buildQS]);

  // Fetch export page
  useEffect(() => {
    if (tab !== "export") return;
    setExportLoading(true);
    fetch(`/api/admin/message-logs/export?${buildQS({ page: exportPage, per_page: 50 })}`)
      .then((r) => r.json())
      .then((d) => { setExportData(d); setExportLoading(false); })
      .catch(() => setExportLoading(false));
  }, [tab, buildQS, exportPage]);

  // Reset page when tab switches
  useEffect(() => { setExportPage(1); }, [tab, applied]);

  const handleApply = () => {
    setApplied({ from: fromDate, to: toDate, hasRoles, notRoles });
    setActivePreset(null);
  };

  const handlePreset = (days) => {
    const f = daysAgoISO(days), t = todayISO();
    setFromDate(f); setToDate(t);
    setApplied((a) => ({ ...a, from: f, to: t }));
    setActivePreset(days);
  };

  const csvFilename = `message_logs_${applied.from || "start"}_to_${applied.to || "end"}.csv`;
  const csvHref = `/api/admin/message-logs/export/csv?${buildQS()}`;

  return (
    <>
      <div className="d-flex align-items-start justify-content-between mb-1 flex-wrap gap-2">
        <div>
          <h2 className="mb-1">Message Logs</h2>
          <p className="text-muted small mb-0">
            Activity heatmap and message export — metadata only, no content stored.
          </p>
        </div>
        <button
          className="btn btn-sm btn-outline-secondary"
          onClick={() => setShowBackfill((v) => !v)}
        >
          <i className="fas fa-history me-1" />Backfill
        </button>
      </div>

      <div className="mt-3 mb-4">
        {showBackfill && <BackfillPanel onClose={() => setShowBackfill(false)} />}

        {/* ── Filter card ── */}
        <div className="chart-card mb-3">
          <div className="chart-card-header">
            <span className="chart-card-title">Filters</span>
          </div>
          <div className="p-3">
            {/* Date row */}
            <div className="d-flex align-items-end gap-2 flex-wrap mb-3">
              <div>
                <label className="form-label small mb-1 fw-semibold">From</label>
                <input
                  type="date" className="form-control form-control-sm"
                  value={fromDate}
                  onChange={(e) => { setFromDate(e.target.value); setActivePreset(null); }}
                />
              </div>
              <div>
                <label className="form-label small mb-1 fw-semibold">To</label>
                <input
                  type="date" className="form-control form-control-sm"
                  value={toDate}
                  onChange={(e) => { setToDate(e.target.value); setActivePreset(null); }}
                />
              </div>
              <div className="d-flex gap-1">
                {PRESETS.map(({ label, days }) => (
                  <button
                    key={days}
                    className={`btn btn-sm ${activePreset === days ? "btn-maroon text-white" : "btn-outline-secondary"}`}
                    onClick={() => handlePreset(days)}
                  >
                    {label}
                  </button>
                ))}
              </div>
              <button className="btn btn-sm btn-maroon text-white" onClick={handleApply}>
                Apply
              </button>
            </div>

            {/* Role filter */}
            <div>
              <div className="form-label small fw-semibold mb-2">Roles</div>
              <RoleFilter
                hasRoles={hasRoles}
                notRoles={notRoles}
                roles={roles}
                onHasChange={setHasRoles}
                onNotChange={setNotRoles}
              />
            </div>
          </div>
        </div>

        {/* ── Tabs ── */}
        <div className="d-flex gap-2 mb-3">
          {[
            { id: "heatmap", icon: "fa-th", label: "Activity Heatmap" },
            { id: "export",  icon: "fa-table", label: "Export" },
          ].map(({ id, icon, label }) => (
            <button
              key={id}
              className={`btn btn-sm ${tab === id ? "btn-maroon text-white" : "btn-outline-secondary"}`}
              onClick={() => setTab(id)}
            >
              <i className={`fas ${icon} me-1`} />{label}
            </button>
          ))}
        </div>

        {/* ── Heatmap tab ── */}
        {tab === "heatmap" && (
          <div className="chart-card">
            <div className="chart-card-header">
              <div>
                <div className="chart-card-title">Message Activity</div>
                <div className="chart-card-subtitle">
                  By hour of day &amp; day of week · Arizona Time
                </div>
              </div>
            </div>
            <div className="p-3">
              <Heatmap
                cells={heatmapData?.cells}
                total={heatmapData?.total ?? 0}
                loading={heatmapLoading}
              />
            </div>
          </div>
        )}

        {/* ── Export tab ── */}
        {tab === "export" && (
          <div>
            <div className="d-flex align-items-center justify-content-between mb-3">
              <span className="text-muted small">
                {exportData
                  ? `${exportData.total.toLocaleString()} messages match`
                  : "Loading…"}
              </span>
              <a
                href={csvHref}
                download={csvFilename}
                className="btn btn-sm btn-outline-secondary"
              >
                <i className="fas fa-download me-1" />Download CSV
              </a>
            </div>
            <ExportTable
              data={exportData}
              page={exportPage}
              setPage={setExportPage}
              loading={exportLoading}
            />
          </div>
        )}
      </div>
    </>
  );
}
