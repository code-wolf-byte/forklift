import { useState, useEffect, useCallback, useRef } from "react";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import ActivityChart from "./ActivityChart.jsx";
import SeriesBuilder, { seriesLabel, seriesParams } from "./SeriesBuilder.jsx";

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

export default function ServerJoins({ isDark }) {
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

  const nextIdRef = useRef(2);
  const [series, setSeries] = useState([{ id: 1, hasRoles: [], notRoles: [] }]);
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

  useEffect(() => {
    setLoading(true);
    fetch(`/api/admin/server-joins?${buildQS({ per_page: 25 })}`)
      .then((r) => r.json())
      .then((d) => { setData(d); setLoading(false); })
      .catch(() => setLoading(false));
  }, [buildQS]);

  useEffect(() => {
    Promise.all(
      series.map((s) => {
        const qs = seriesParams(s, applied.from_date, applied.to_date);
        return fetch(`/api/admin/server-joins/chart?${qs}`)
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
    setSeries((s) => [...s, { id: nextIdRef.current++, hasRoles: [], notRoles: [] }]);
  };

  const updateSeries = (id, patch) => {
    setSeries((s) => s.map((item) => (item.id === id ? { ...item, ...patch } : item)));
  };

  const removeSeries = (id) => {
    setSeries((s) => s.filter((item) => item.id !== id));
  };

  const datasets = series.map((s, i) => ({
    data: chartDataMap[s.id] || [],
    label: seriesLabel(s),
    color: COLORS[i % COLORS.length],
  }));

  return (
    <>
      <h2 className="text-2xl font-bold mb-1">Server Joins</h2>
      <p className="text-sm text-muted-foreground mb-4">
        {data ? `${data.total.toLocaleString()} members joined in this range.` : "Loading…"}
      </p>

      {/* Filters */}
      <Card className="mb-3">
        <CardContent className="p-3">
          <div className="flex gap-2 items-end flex-wrap">
            <div>
              <Label className="text-xs font-semibold mb-1 block">From</Label>
              <Input
                type="date"
                className="h-8 text-sm w-36"
                value={filters.from_date}
                onChange={(e) => {
                  setFilters((f) => ({ ...f, from_date: e.target.value }));
                  setActiveScale(null);
                }}
              />
            </div>
            <div>
              <Label className="text-xs font-semibold mb-1 block">To</Label>
              <Input
                type="date"
                className="h-8 text-sm w-36"
                value={filters.to_date}
                onChange={(e) => {
                  setFilters((f) => ({ ...f, to_date: e.target.value }));
                  setActiveScale(null);
                }}
              />
            </div>
            <div>
              <Label className="text-xs font-semibold mb-1 block">Scale</Label>
              <div className="flex gap-1">
                {SCALE_PRESETS.map((d) => (
                  <Button
                    key={d}
                    size="sm"
                    variant={activeScale === d ? "default" : "outline"}
                    onClick={() => handleScaleClick(d)}
                  >
                    {d}d
                  </Button>
                ))}
              </div>
            </div>
            <div>
              <Label className="text-xs font-semibold mb-1 block">Role</Label>
              <select
                className="series-add-select h-8 rounded-md border border-input bg-background px-2 text-sm"
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
            <Button size="sm" onClick={handleApply}>Apply</Button>
          </div>
        </CardContent>
      </Card>

      {/* Chart card */}
      <Card className="mb-3 overflow-hidden">
        <div
          className="flex items-end justify-between gap-3 px-5 py-4"
          style={{ borderBottom: "1px solid hsl(var(--border))" }}
        >
          <div>
            <div className="text-sm font-bold tracking-tight">Daily Joins</div>
            {data && (
              <div className="text-xs text-muted-foreground mt-0.5">
                {data.total.toLocaleString()} member{data.total !== 1 ? "s" : ""} joined in range
              </div>
            )}
          </div>
        </div>

        <div className="p-5 pb-2">
          <ActivityChart datasets={datasets} isDark={isDark} />
        </div>

        <div className="px-4 py-3" style={{ borderTop: "1px solid hsl(var(--border))" }}>
          <div className="flex items-center justify-between mb-2.5">
            <span className="text-[11px] font-bold uppercase tracking-[0.07em] text-muted-foreground">Series</span>
            {series.length < COLORS.length && (
              <Button size="sm" variant="outline" onClick={addSeries}>
                <i className="fas fa-plus mr-1" style={{ fontSize: 10 }} />Add series
              </Button>
            )}
          </div>
          <SeriesBuilder
            series={series}
            roles={roles}
            colors={COLORS}
            onUpdate={updateSeries}
            onRemove={removeSeries}
          />
        </div>
      </Card>

      {/* List */}
      {loading ? (
        <div className="flex justify-center py-4">
          <div className="spinner-border spinner-border-sm" role="status" style={{ color: "#8c1d40" }}>
            <span className="visually-hidden">Loading…</span>
          </div>
        </div>
      ) : (
        <>
          <Card className="overflow-hidden p-0">
            {!data?.users?.length ? (
              <p className="text-sm text-muted-foreground p-3 mb-0">No joins in this range.</p>
            ) : (
              data.users.map((u, i) => (
                <div
                  key={u.id}
                  className="flex items-center gap-3 px-3 py-2"
                  style={{ borderBottom: i < data.users.length - 1 ? "1px solid hsl(var(--border))" : "none" }}
                >
                  <Avatar userId={u.discord_user_id} avatarHash={u.discord_avatar} username={u.discord_username} />
                  <div className="flex-1 overflow-hidden">
                    <div className="font-semibold text-sm truncate">{u.discord_username || "—"}</div>
                    <div className="text-muted-foreground text-xs">{u.asurite_id}</div>
                  </div>
                  <div className="text-sm text-muted-foreground whitespace-nowrap shrink-0">
                    <i className="fas fa-sign-in-alt mr-1" style={{ color: "#8c1d40" }} />
                    {u.joined_at
                      ? new Date(u.joined_at).toLocaleDateString("en-US", {
                          timeZone: "America/Phoenix", month: "short", day: "numeric", year: "numeric",
                        })
                      : "—"}
                  </div>
                </div>
              ))
            )}
          </Card>

          {data?.pages > 1 && (
            <div className="flex items-center gap-3 mt-3">
              <Button size="sm" variant="outline" disabled={page === 1} onClick={() => setPage((p) => p - 1)}>
                <i className="fas fa-chevron-left mr-1" />Prev
              </Button>
              <span className="text-sm text-muted-foreground">Page {page} of {data.pages}</span>
              <Button size="sm" variant="outline" disabled={page === data.pages} onClick={() => setPage((p) => p + 1)}>
                Next<i className="fas fa-chevron-right ml-1" />
              </Button>
            </div>
          )}
        </>
      )}
    </>
  );
}
