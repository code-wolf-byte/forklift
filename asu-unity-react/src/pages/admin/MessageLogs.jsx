import { useState, useEffect, useCallback } from "react";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import {
  Table,
  TableHeader,
  TableBody,
  TableRow,
  TableHead,
  TableCell,
} from "@/components/ui/table";
import RoleFilter from "./RoleFilter.jsx";

// ── Constants ──────────────────────────────────────────────────────────────────

const DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
const HOURS = Array.from({ length: 24 }, (_, i) => i);

const DOW_ABBR = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

const todayISO = () => new Date().toISOString().slice(0, 10);
const daysAgoISO = (n) => {
  const d = new Date();
  d.setDate(d.getDate() - n);
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
      <div className="flex justify-center py-20">
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

  const lookup = {};
  let maxCount = 0;
  for (const c of cells) {
    if (!lookup[c.dow]) lookup[c.dow] = {};
    lookup[c.dow][c.hour] = c.count;
    if (c.count > maxCount) maxCount = c.count;
  }

  const cellColor = (count) => {
    if (!count) return undefined;
    const intensity = Math.pow(count / maxCount, 0.5);
    return `rgba(140,29,64,${(0.08 + intensity * 0.88).toFixed(2)})`;
  };

  return (
    <div className="heatmap-wrapper">
      <div className="heatmap-grid">
        <div className="heatmap-corner" />
        {HOURS.map((h) => (
          <div key={h} className="heatmap-hour-label">{fmtHour(h)}</div>
        ))}

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

      <div className="heatmap-legend">
        <span className="text-muted-foreground text-xs">Less</span>
        <div className="heatmap-legend-scale">
          {[0, 0.2, 0.4, 0.65, 0.85, 1].map((v) => (
            <div
              key={v}
              className="heatmap-legend-swatch"
              style={{ background: v === 0 ? "rgba(140,29,64,0.06)" : `rgba(140,29,64,${(0.08 + v * 0.88).toFixed(2)})` }}
            />
          ))}
        </div>
        <span className="text-muted-foreground text-xs">More</span>
        <span className="text-muted-foreground text-xs ml-3">
          {total.toLocaleString()} total messages
        </span>
      </div>
    </div>
  );
}

// ── Date heatmap (date × hour) ────────────────────────────────────────────────

function fmtDateLabel(isoDate) {
  const [y, m, d] = isoDate.split("-").map(Number);
  return new Date(y, m - 1, d).toLocaleDateString("en-US", {
    month: "short", day: "numeric",
  });
}

function DateHeatmap({ cells, dates, total, loading }) {
  if (loading) {
    return (
      <div className="flex justify-center py-20">
        <div className="spinner-border spinner-border-sm" role="status" style={{ color: "#8c1d40" }}>
          <span className="visually-hidden">Loading…</span>
        </div>
      </div>
    );
  }

  if (!cells?.length || total === 0) {
    return <div className="heatmap-empty">No message data for the selected filters.</div>;
  }

  const lookup = {};
  let maxCount = 0;
  for (const c of cells) {
    if (!lookup[c.date]) lookup[c.date] = {};
    lookup[c.date][c.hour] = c.count;
    if (c.count > maxCount) maxCount = c.count;
  }

  const cellColor = (count) => {
    if (!count) return undefined;
    const intensity = Math.pow(count / maxCount, 0.5);
    return `rgba(140,29,64,${(0.08 + intensity * 0.88).toFixed(2)})`;
  };

  return (
    <div className="heatmap-wrapper" style={{ maxHeight: 480, overflowY: "auto" }}>
      <div className="heatmap-grid" style={{ gridTemplateColumns: "64px repeat(24, 1fr)" }}>
        {/* Header row */}
        <div className="heatmap-corner" />
        {HOURS.map((h) => (
          <div key={h} className="heatmap-hour-label">{fmtHour(h)}</div>
        ))}

        {/* One row per date */}
        {dates.map((date) => {
          const [y, m, d] = date.split("-").map(Number);
          const dow = new Date(y, m - 1, d).getDay(); // 0=Sun
          const dowLabel = DOW_ABBR[(dow + 6) % 7]; // convert to Mon=0
          return (
            <>
              <div key={`label-${date}`} className="heatmap-day-label" style={{ fontSize: 10 }}>
                <span style={{ fontWeight: 700, marginRight: 3 }}>{fmtDateLabel(date)}</span>
                <span style={{ opacity: 0.5, fontWeight: 400 }}>{dowLabel}</span>
              </div>
              {HOURS.map((h) => {
                const count = lookup[date]?.[h] ?? 0;
                return (
                  <div
                    key={`${date}-${h}`}
                    className="heatmap-cell"
                    style={{ background: cellColor(count) }}
                    title={`${date} ${fmtHour(h)} — ${count.toLocaleString()} message${count !== 1 ? "s" : ""}`}
                  />
                );
              })}
            </>
          );
        })}
      </div>

      <div className="heatmap-legend">
        <span className="text-muted-foreground text-xs">Less</span>
        <div className="heatmap-legend-scale">
          {[0, 0.2, 0.4, 0.65, 0.85, 1].map((v) => (
            <div
              key={v}
              className="heatmap-legend-swatch"
              style={{ background: v === 0 ? "rgba(140,29,64,0.06)" : `rgba(140,29,64,${(0.08 + v * 0.88).toFixed(2)})` }}
            />
          ))}
        </div>
        <span className="text-muted-foreground text-xs">More</span>
        <span className="text-muted-foreground text-xs ml-3">
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
      <div className="flex justify-center py-20">
        <div className="spinner-border spinner-border-sm" role="status" style={{ color: "#8c1d40" }}>
          <span className="visually-hidden">Loading…</span>
        </div>
      </div>
    );
  }

  const rows = data?.rows ?? [];

  return (
    <>
      <Card className="overflow-hidden p-0">
        {!rows.length ? (
          <p className="text-sm text-muted-foreground p-3 mb-0">No messages match the current filters.</p>
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="pl-4">Time (AZ)</TableHead>
                <TableHead>Channel</TableHead>
                <TableHead>User</TableHead>
                <TableHead>ASURITE</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows.map((r) => (
                <TableRow key={r.message_id}>
                  <TableCell className="pl-4 text-muted-foreground text-xs whitespace-nowrap">
                    {fmtDate(r.sent_at)}
                  </TableCell>
                  <TableCell>
                    <span className="font-semibold text-xs">#{r.channel_name || r.channel_id}</span>
                  </TableCell>
                  <TableCell className="text-muted-foreground text-xs truncate max-w-[180px]">
                    {r.discord_username || (
                      <span className="italic opacity-50">{r.discord_user_id}</span>
                    )}
                  </TableCell>
                  <TableCell className="text-muted-foreground text-xs">
                    {r.asurite_id || "—"}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </Card>

      {data?.pages > 1 && (
        <div className="flex items-center gap-3 mt-3">
          <Button
            size="sm"
            variant="outline"
            disabled={page === 1}
            onClick={() => setPage((p) => p - 1)}
          >
            <i className="fas fa-chevron-left mr-1" />Prev
          </Button>
          <span className="text-sm text-muted-foreground">
            Page {page} of {data.pages}
            <span className="ml-2 opacity-50">({data.total.toLocaleString()} total)</span>
          </span>
          <Button
            size="sm"
            variant="outline"
            disabled={page === data.pages}
            onClick={() => setPage((p) => p + 1)}
          >
            Next<i className="fas fa-chevron-right ml-1" />
          </Button>
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
    <Card className="mb-6">
      <CardContent className="p-4">
        <div className="flex items-start justify-between mb-3">
          <div>
            <h6 className="text-sm font-semibold mb-1">Historical Backfill</h6>
            <p className="text-xs text-muted-foreground mb-0">
              Fetches up to 1 year of message metadata from all text channels.
              No message content is stored.
            </p>
          </div>
          <Button size="sm" variant="outline" onClick={onClose}>
            <i className="fas fa-times" />
          </Button>
        </div>

        {status && (
          <div className="flex items-center gap-3 mb-3 flex-wrap">
            <span className="text-sm">
              <strong>{status.total_messages_logged?.toLocaleString()}</strong> messages logged
            </span>
            <span className="text-xs text-muted-foreground">
              {status.channels_done}/{status.channels_total} channels done
            </span>
            {status.backfill_running && (
              <Badge style={{ background: "#3b82f6", color: "#fff" }}>
                <i className="fas fa-sync fa-spin mr-1" style={{ fontSize: 10 }} />Running
              </Badge>
            )}
          </div>
        )}

        <Button
          size="sm"
          onClick={handleStart}
          disabled={triggering || status?.backfill_running}
          className="self-start"
        >
          {status?.backfill_running ? "Backfill running…" : "Start Backfill"}
        </Button>

        {status?.channels?.length > 0 && (
          <div className="mt-3" style={{ maxHeight: 220, overflowY: "auto" }}>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Channel</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Messages</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {status.channels.map((ch) => (
                  <TableRow key={ch.channel_id}>
                    <TableCell className="text-xs">#{ch.channel_name || ch.channel_id}</TableCell>
                    <TableCell className="text-xs">
                      <span style={{ color: STATUS_COLORS[ch.status] ?? "#6c757d", fontWeight: 600 }}>
                        {ch.status}
                      </span>
                      {ch.error && (
                        <span className="text-destructive ml-1" title={ch.error}>⚠</span>
                      )}
                    </TableCell>
                    <TableCell className="text-xs">{ch.messages_fetched?.toLocaleString() ?? "—"}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        )}
      </CardContent>
    </Card>
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

  const [fromDate, setFromDate] = useState(daysAgoISO(30));
  const [toDate, setToDate] = useState(todayISO());
  const [hasRoles, setHasRoles] = useState([]);
  const [notRoles, setNotRoles] = useState([]);
  const [activePreset, setActivePreset] = useState(30);

  const [applied, setApplied] = useState({
    from: daysAgoISO(30), to: todayISO(), hasRoles: [], notRoles: [],
  });

  const [heatmapGroupby, setHeatmapGroupby] = useState("dow");

  const [roles, setRoles] = useState([]);
  const [heatmapData, setHeatmapData] = useState(null);
  const [heatmapLoading, setHeatmapLoading] = useState(true);
  const [exportData, setExportData] = useState(null);
  const [exportLoading, setExportLoading] = useState(false);
  const [exportPage, setExportPage] = useState(1);

  useEffect(() => {
    fetch("/api/admin/roles").then((r) => r.json()).then(setRoles).catch(() => {});
  }, []);

  const buildQS = useCallback((extra = {}) => {
    const p = new URLSearchParams();
    if (applied.from) p.set("from_date", applied.from);
    if (applied.to)   p.set("to_date", applied.to);
    applied.hasRoles.forEach((r) => p.append("role", r));
    applied.notRoles.forEach((r) => p.append("exclude_role", r));
    Object.entries(extra).forEach(([k, v]) => p.set(k, v));
    return p.toString();
  }, [applied]);

  useEffect(() => {
    setHeatmapLoading(true);
    fetch(`/api/admin/message-logs/heatmap?${buildQS()}&groupby=${heatmapGroupby}`)
      .then((r) => r.json())
      .then((d) => { setHeatmapData(d); setHeatmapLoading(false); })
      .catch(() => setHeatmapLoading(false));
  }, [buildQS, heatmapGroupby]);

  useEffect(() => {
    if (tab !== "export") return;
    setExportLoading(true);
    fetch(`/api/admin/message-logs/export?${buildQS({ page: exportPage, per_page: 50 })}`)
      .then((r) => r.json())
      .then((d) => { setExportData(d); setExportLoading(false); })
      .catch(() => setExportLoading(false));
  }, [tab, buildQS, exportPage]);

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
      <div className="flex items-start justify-between mb-1 flex-wrap gap-2">
        <div>
          <h2 className="text-2xl font-bold mb-1">Message Logs</h2>
          <p className="text-sm text-muted-foreground mb-0">
            Activity heatmap and message export — metadata only, no content stored.
          </p>
        </div>
        <Button
          size="sm"
          variant="outline"
          onClick={() => setShowBackfill((v) => !v)}
        >
          <i className="fas fa-history mr-1" />Backfill
        </Button>
      </div>

      <div className="mt-4 mb-6">
        {showBackfill && <BackfillPanel onClose={() => setShowBackfill(false)} />}

        {/* ── Filter card ── */}
        <Card className="mb-3 overflow-hidden">
          <div
            className="flex items-end justify-between gap-3 px-5 py-4"
            style={{ borderBottom: "1px solid hsl(var(--border))" }}
          >
            <span className="text-sm font-bold tracking-tight">Filters</span>
          </div>
          <CardContent className="p-4">
            {/* Date row */}
            <div className="flex items-end gap-2 flex-wrap mb-4">
              <div>
                <Label className="text-xs font-semibold mb-1 block">From</Label>
                <Input
                  type="date"
                  className="h-8 text-sm w-36"
                  value={fromDate}
                  onChange={(e) => { setFromDate(e.target.value); setActivePreset(null); }}
                />
              </div>
              <div>
                <Label className="text-xs font-semibold mb-1 block">To</Label>
                <Input
                  type="date"
                  className="h-8 text-sm w-36"
                  value={toDate}
                  onChange={(e) => { setToDate(e.target.value); setActivePreset(null); }}
                />
              </div>
              <div className="flex gap-1">
                {PRESETS.map(({ label, days }) => (
                  <Button
                    key={days}
                    size="sm"
                    variant={activePreset === days ? "default" : "outline"}
                    onClick={() => handlePreset(days)}
                  >
                    {label}
                  </Button>
                ))}
              </div>
              <Button size="sm" onClick={handleApply}>Apply</Button>
            </div>

            {/* Role filter */}
            <div>
              <Label className="text-xs font-semibold mb-2 block">Roles</Label>
              <RoleFilter
                hasRoles={hasRoles}
                notRoles={notRoles}
                roles={roles}
                onHasChange={setHasRoles}
                onNotChange={setNotRoles}
              />
            </div>
          </CardContent>
        </Card>

        {/* ── Tabs ── */}
        <div className="flex gap-2 mb-3">
          {[
            { id: "heatmap", icon: "fa-th", label: "Activity Heatmap" },
            { id: "export",  icon: "fa-table", label: "Export" },
          ].map(({ id, icon, label }) => (
            <Button
              key={id}
              size="sm"
              variant={tab === id ? "default" : "outline"}
              onClick={() => setTab(id)}
            >
              <i className={`fas ${icon} mr-1`} />{label}
            </Button>
          ))}
        </div>

        {/* ── Heatmap tab ── */}
        {tab === "heatmap" && (
          <Card className="overflow-hidden">
            <div
              className="flex items-center justify-between gap-3 px-5 py-4"
              style={{ borderBottom: "1px solid hsl(var(--border))" }}
            >
              <div>
                <div className="text-sm font-bold tracking-tight">Message Activity</div>
                <div className="text-xs text-muted-foreground mt-0.5">
                  {heatmapGroupby === "dow"
                    ? "By hour of day & day of week · Arizona Time"
                    : "By date & hour of day · Arizona Time"}
                </div>
              </div>
              <div className="flex gap-1">
                <Button
                  size="sm"
                  variant={heatmapGroupby === "dow" ? "default" : "outline"}
                  onClick={() => setHeatmapGroupby("dow")}
                >
                  By Day
                </Button>
                <Button
                  size="sm"
                  variant={heatmapGroupby === "date" ? "default" : "outline"}
                  onClick={() => setHeatmapGroupby("date")}
                >
                  By Date
                </Button>
              </div>
            </div>
            <CardContent className="p-4">
              {heatmapGroupby === "dow" ? (
                <Heatmap
                  cells={heatmapData?.cells}
                  total={heatmapData?.total ?? 0}
                  loading={heatmapLoading}
                />
              ) : (
                <DateHeatmap
                  cells={heatmapData?.cells}
                  dates={heatmapData?.dates ?? []}
                  total={heatmapData?.total ?? 0}
                  loading={heatmapLoading}
                />
              )}
            </CardContent>
          </Card>
        )}

        {/* ── Export tab ── */}
        {tab === "export" && (
          <div>
            <div className="flex items-center justify-between mb-3">
              <span className="text-sm text-muted-foreground">
                {exportData
                  ? `${exportData.total.toLocaleString()} messages match`
                  : "Loading…"}
              </span>
              <Button size="sm" variant="outline" asChild>
                <a href={csvHref} download={csvFilename}>
                  <i className="fas fa-download mr-1" />Download CSV
                </a>
              </Button>
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
