import { useState, useEffect, useCallback, useRef } from "react";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import ActivityChart from "./ActivityChart.jsx";
import SeriesBuilder, { seriesLabel, seriesParams } from "./SeriesBuilder.jsx";
import { getUrlParam, replaceUrlParams } from "@/utils/adminUrl";
import { todayISO, daysAgoISO } from "@/utils/adminDates";

const COLORS = ["#8c1d40", "#3b82f6", "#10b981", "#f59e0b", "#8b5cf6", "#ef4444"];
const SCALE_PRESETS = [7, 14, 30, 90];

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

function DateRangeFilter({ filters, setFilters, onApply, activeScale, onScaleClick, label }) {
  return (
    <Card className="mb-3">
      <CardContent className="p-3">
        <div className="flex gap-2 items-end flex-wrap">
          <div>
            <Label className="text-xs font-semibold mb-1 block">From</Label>
            <Input
              type="date"
              className="h-8 text-sm w-36"
              value={filters.from_date}
              onChange={(e) => setFilters((f) => ({ ...f, from_date: e.target.value }))}
            />
          </div>
          <div>
            <Label className="text-xs font-semibold mb-1 block">To</Label>
            <Input
              type="date"
              className="h-8 text-sm w-36"
              value={filters.to_date}
              onChange={(e) => setFilters((f) => ({ ...f, to_date: e.target.value }))}
            />
          </div>
          {onScaleClick && (
            <div>
              <Label className="text-xs font-semibold mb-1 block">Scale</Label>
              <div className="flex gap-1">
                {SCALE_PRESETS.map((d) => (
                  <Button
                    key={d}
                    size="sm"
                    variant={activeScale === d ? "default" : "outline"}
                    onClick={() => onScaleClick(d)}
                  >
                    {d}d
                  </Button>
                ))}
              </div>
            </div>
          )}
          <Button size="sm" onClick={onApply}>Apply</Button>
        </div>
      </CardContent>
    </Card>
  );
}

export default function ServerJoins({ isDark }) {
  // ── Joins state ──────────────────────────────────────────────────────────────
  const [joinFilters, setJoinFilters] = useState(() => ({
    from_date: getUrlParam("from_date", daysAgoISO(30)),
    to_date: getUrlParam("to_date", todayISO()),
  }));
  const [joinApplied, setJoinApplied] = useState(joinFilters);
  const [joinActiveScale, setJoinActiveScale] = useState(() => {
    const s = parseInt(getUrlParam("scale", "30"), 10);
    return SCALE_PRESETS.includes(s) ? s : 30;
  });
  const [roles, setRoles] = useState([]);
  const [joinData, setJoinData] = useState(null);
  const [joinPage, setJoinPage] = useState(1);
  const [joinLoading, setJoinLoading] = useState(true);

  const nextIdRef = useRef(2);
  const [series, setSeries] = useState([{ id: 1, hasRoles: [], notRoles: [] }]);
  const [chartDataMap, setChartDataMap] = useState({});

  // ── Verifications state ───────────────────────────────────────────────────────
  const [verifFilters, setVerifFilters] = useState(() => ({
    from_date: getUrlParam("vfrom_date", daysAgoISO(30)),
    to_date: getUrlParam("vto_date", todayISO()),
  }));
  const [verifApplied, setVerifApplied] = useState(verifFilters);
  const [verifChartData, setVerifChartData] = useState([]);
  const [verifData, setVerifData] = useState(null);
  const [verifPage, setVerifPage] = useState(1);
  const [verifLoading, setVerifLoading] = useState(true);

  // ── Shared role list ─────────────────────────────────────────────────────────
  useEffect(() => {
    fetch("/api/admin/roles")
      .then((r) => r.json())
      .then(setRoles)
      .catch(() => {});
  }, []);

  // ── Joins chart & list fetches ────────────────────────────────────────────────
  const buildJoinQS = useCallback(
    (extra = {}) => {
      const p = { ...joinApplied, page: joinPage, ...extra };
      return Object.entries(p)
        .filter(([, v]) => v !== "" && v != null)
        .map(([k, v]) => `${k}=${encodeURIComponent(v)}`)
        .join("&");
    },
    [joinApplied, joinPage]
  );

  useEffect(() => {
    setJoinLoading(true);
    fetch(`/api/admin/server-joins?${buildJoinQS({ per_page: 25 })}`)
      .then((r) => r.json())
      .then((d) => { setJoinData(d); setJoinLoading(false); })
      .catch(() => setJoinLoading(false));
  }, [buildJoinQS]);

  useEffect(() => {
    Promise.all(
      series.map((s) => {
        const qs = seriesParams(s, joinApplied.from_date, joinApplied.to_date);
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
  }, [joinApplied, series]);

  // ── Verifications chart & list fetches ───────────────────────────────────────
  const buildVerifQS = useCallback(
    (extra = {}) => {
      const p = { ...verifApplied, page: verifPage, ...extra };
      return Object.entries(p)
        .filter(([, v]) => v !== "" && v != null)
        .map(([k, v]) => `${k}=${encodeURIComponent(v)}`)
        .join("&");
    },
    [verifApplied, verifPage]
  );

  useEffect(() => {
    const qs = new URLSearchParams();
    if (verifApplied.from_date) qs.set("from_date", verifApplied.from_date);
    if (verifApplied.to_date) qs.set("to_date", verifApplied.to_date);
    fetch(`/api/admin/verifications/chart?${qs}`)
      .then((r) => r.json())
      .then(setVerifChartData)
      .catch(() => {});
  }, [verifApplied]);

  useEffect(() => {
    setVerifLoading(true);
    fetch(`/api/admin/verifications?${buildVerifQS({ per_page: 25 })}`)
      .then((r) => r.json())
      .then((d) => { setVerifData(d); setVerifLoading(false); })
      .catch(() => setVerifLoading(false));
  }, [buildVerifQS]);

  // ── Joins handlers ────────────────────────────────────────────────────────────
  const handleJoinScaleClick = (days) => {
    const newFrom = daysAgoISO(days);
    const newTo = todayISO();
    setJoinFilters((f) => ({ ...f, from_date: newFrom, to_date: newTo }));
    setJoinApplied((prev) => ({ ...prev, from_date: newFrom, to_date: newTo }));
    setJoinActiveScale(days);
    setJoinPage(1);
    replaceUrlParams({ from_date: newFrom, to_date: newTo, scale: days });
  };

  const handleJoinApply = () => {
    setJoinPage(1);
    setJoinApplied(joinFilters);
    replaceUrlParams({ from_date: joinFilters.from_date, to_date: joinFilters.to_date, scale: "" });
  };

  // ── Verifications handlers ────────────────────────────────────────────────────
  const handleVerifApply = () => {
    setVerifPage(1);
    setVerifApplied(verifFilters);
    replaceUrlParams({ vfrom_date: verifFilters.from_date, vto_date: verifFilters.to_date });
  };

  // ── Series helpers ────────────────────────────────────────────────────────────
  const addSeries = () => {
    if (series.length >= COLORS.length) return;
    setSeries((s) => [...s, { id: nextIdRef.current++, hasRoles: [], notRoles: [] }]);
  };
  const updateSeries = (id, patch) => setSeries((s) => s.map((item) => (item.id === id ? { ...item, ...patch } : item)));
  const removeSeries = (id) => setSeries((s) => s.filter((item) => item.id !== id));

  const joinDatasets = series.map((s, i) => ({
    data: chartDataMap[s.id] || [],
    label: seriesLabel(s),
    color: COLORS[i % COLORS.length],
  }));

  return (
    <>
      {/* ── Joins ── */}
      <h2 className="text-2xl font-bold mb-1">Server Joins</h2>
      <p className="text-sm text-muted-foreground mb-4">
        {joinData ? `${joinData.total.toLocaleString()} members joined in this range.` : "Loading…"}
      </p>

      <DateRangeFilter
        filters={joinFilters}
        setFilters={(fn) => { setJoinFilters(fn); setJoinActiveScale(null); }}
        onApply={handleJoinApply}
        activeScale={joinActiveScale}
        onScaleClick={handleJoinScaleClick}
      />

      <Card className="mb-3 overflow-hidden">
        <div
          className="flex items-end justify-between gap-3 px-5 py-4"
          style={{ borderBottom: "1px solid hsl(var(--border))" }}
        >
          <div>
            <div className="text-sm font-bold tracking-tight">Daily Joins</div>
            {joinData && (
              <div className="text-xs text-muted-foreground mt-0.5">
                {joinData.total.toLocaleString()} member{joinData.total !== 1 ? "s" : ""} joined in range
              </div>
            )}
          </div>
        </div>

        <div className="p-5 pb-2">
          <ActivityChart datasets={joinDatasets} isDark={isDark} />
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

      {joinLoading ? (
        <div className="flex justify-center py-4">
          <div className="spinner-border spinner-border-sm" role="status" style={{ color: "#8c1d40" }}>
            <span className="visually-hidden">Loading…</span>
          </div>
        </div>
      ) : (
        <>
          <Card className="overflow-hidden p-0">
            {!joinData?.users?.length ? (
              <p className="text-sm text-muted-foreground p-3 mb-0">No joins in this range.</p>
            ) : (
              joinData.users.map((u, i) => (
                <div
                  key={u.id}
                  className="flex items-center gap-3 px-3 py-2"
                  style={{ borderBottom: i < joinData.users.length - 1 ? "1px solid hsl(var(--border))" : "none" }}
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

          {joinData?.pages > 1 && (
            <div className="flex items-center gap-3 mt-3">
              <Button size="sm" variant="outline" disabled={joinPage === 1} onClick={() => setJoinPage((p) => p - 1)}>
                <i className="fas fa-chevron-left mr-1" />Prev
              </Button>
              <span className="text-sm text-muted-foreground">Page {joinPage} of {joinData.pages}</span>
              <Button size="sm" variant="outline" disabled={joinPage === joinData.pages} onClick={() => setJoinPage((p) => p + 1)}>
                Next<i className="fas fa-chevron-right ml-1" />
              </Button>
            </div>
          )}
        </>
      )}

      {/* ── Verifications ── */}
      <h2 className="text-2xl font-bold mb-1 mt-10">Verifications</h2>
      <p className="text-sm text-muted-foreground mb-4">
        {verifData ? `${verifData.total.toLocaleString()} members verified in this range.` : "Loading…"}
      </p>

      <DateRangeFilter
        filters={verifFilters}
        setFilters={setVerifFilters}
        onApply={handleVerifApply}
      />

      <Card className="mb-3 overflow-hidden">
        <div
          className="flex items-end justify-between gap-3 px-5 py-4"
          style={{ borderBottom: "1px solid hsl(var(--border))" }}
        >
          <div>
            <div className="text-sm font-bold tracking-tight">Daily Verifications</div>
            {verifData && (
              <div className="text-xs text-muted-foreground mt-0.5">
                {verifData.total.toLocaleString()} member{verifData.total !== 1 ? "s" : ""} verified in range
              </div>
            )}
          </div>
        </div>
        <div className="p-5 pb-3">
          <ActivityChart
            datasets={[{ data: verifChartData, label: "Verifications", color: "#10b981" }]}
            isDark={isDark}
          />
        </div>
      </Card>

      {verifLoading ? (
        <div className="flex justify-center py-4">
          <div className="spinner-border spinner-border-sm" role="status" style={{ color: "#10b981" }}>
            <span className="visually-hidden">Loading…</span>
          </div>
        </div>
      ) : (
        <>
          <Card className="overflow-hidden p-0">
            {!verifData?.users?.length ? (
              <p className="text-sm text-muted-foreground p-3 mb-0">No verifications in this range.</p>
            ) : (
              verifData.users.map((u, i) => (
                <div
                  key={u.id}
                  className="flex items-center gap-3 px-3 py-2"
                  style={{ borderBottom: i < verifData.users.length - 1 ? "1px solid hsl(var(--border))" : "none" }}
                >
                  <Avatar userId={u.discord_user_id} avatarHash={u.discord_avatar} username={u.discord_username} />
                  <div className="flex-1 overflow-hidden">
                    <div className="font-semibold text-sm truncate">{u.discord_username || "—"}</div>
                    <div className="text-muted-foreground text-xs">{u.asurite_id}</div>
                  </div>
                  <div className="text-sm text-muted-foreground whitespace-nowrap shrink-0">
                    <i className="fas fa-user-check mr-1" style={{ color: "#10b981" }} />
                    {u.verified_at
                      ? new Date(u.verified_at).toLocaleDateString("en-US", {
                          timeZone: "America/Phoenix", month: "short", day: "numeric", year: "numeric",
                        })
                      : "—"}
                  </div>
                </div>
              ))
            )}
          </Card>

          {verifData?.pages > 1 && (
            <div className="flex items-center gap-3 mt-3">
              <Button size="sm" variant="outline" disabled={verifPage === 1} onClick={() => setVerifPage((p) => p - 1)}>
                <i className="fas fa-chevron-left mr-1" />Prev
              </Button>
              <span className="text-sm text-muted-foreground">Page {verifPage} of {verifData.pages}</span>
              <Button size="sm" variant="outline" disabled={verifPage === verifData.pages} onClick={() => setVerifPage((p) => p + 1)}>
                Next<i className="fas fa-chevron-right ml-1" />
              </Button>
            </div>
          )}
        </>
      )}
    </>
  );
}
