import { useState, useEffect, useRef } from "react";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import ActivityChart from "./ActivityChart.jsx";
import SeriesBuilder, { seriesLabel, seriesParams } from "./SeriesBuilder.jsx";
import { getUrlParam, replaceUrlParams } from "@/utils/adminUrl";

const COLORS = ["#8c1d40", "#3b82f6", "#10b981", "#f59e0b", "#8b5cf6", "#ef4444"];
const SCALE_PRESETS = [7, 14, 30, 90];

const todayISO = () => new Date().toISOString().slice(0, 10);
const daysAgoISO = (n) => {
  const d = new Date();
  d.setDate(d.getDate() - n);
  return d.toISOString().slice(0, 10);
};

const sum = (data, key) => data.reduce((t, d) => t + (d[key] || 0), 0);

function SeriesSummary({ label, color, data }) {
  if (!data.length) return null;
  const current = data[data.length - 1].count;
  const net = current - (data[0].count - data[0].joins + data[0].leaves);

  return (
    <div className="flex items-center gap-3 px-3 py-2">
      <span className="w-2.5 h-2.5 rounded-full shrink-0" style={{ background: color }} />
      <div className="flex-1 overflow-hidden">
        <div className="text-sm font-semibold truncate" title={label}>{label}</div>
        <div className="text-xs text-muted-foreground">
          +{sum(data, "joins").toLocaleString()} joined · −{sum(data, "leaves").toLocaleString()} left
        </div>
      </div>
      <div className="text-right shrink-0">
        <div className="text-lg font-bold leading-none tracking-tight">{current.toLocaleString()}</div>
        <div className="text-xs mt-1" style={{ color: net >= 0 ? "#10b981" : "#ef4444" }}>
          {net >= 0 ? "+" : "−"}{Math.abs(net).toLocaleString()} in range
        </div>
      </div>
    </div>
  );
}

export default function Membership({ isDark }) {
  const [filters, setFilters] = useState(() => ({
    from_date: getUrlParam("from_date", daysAgoISO(30)),
    to_date: getUrlParam("to_date", todayISO()),
  }));
  const [applied, setApplied] = useState(filters);
  const [activeScale, setActiveScale] = useState(() => {
    const s = parseInt(getUrlParam("scale", "30"), 10);
    return SCALE_PRESETS.includes(s) ? s : 30;
  });
  const [roles, setRoles] = useState([]);
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

  useEffect(() => {
    setLoading(true);
    Promise.all(
      series.map((s) => {
        const qs = seriesParams(s, applied.from_date, applied.to_date);
        return fetch(`/api/admin/membership/chart?${qs}`)
          .then((r) => r.json())
          .then((d) => ({ id: s.id, data: d }))
          .catch(() => ({ id: s.id, data: [] }));
      })
    ).then((results) => {
      const map = {};
      results.forEach((r) => { map[r.id] = r.data; });
      setChartDataMap(map);
      setLoading(false);
    });
  }, [applied, series]);

  const handleScaleClick = (days) => {
    const newFrom = daysAgoISO(days);
    const newTo = todayISO();
    setFilters((f) => ({ ...f, from_date: newFrom, to_date: newTo }));
    setApplied((prev) => ({ ...prev, from_date: newFrom, to_date: newTo }));
    setActiveScale(days);
    replaceUrlParams({ from_date: newFrom, to_date: newTo, scale: days });
  };

  const handleApply = () => {
    setApplied(filters);
    replaceUrlParams({ from_date: filters.from_date, to_date: filters.to_date, scale: "" });
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
      <h2 className="text-2xl font-bold mb-1">Membership</h2>
      <p className="text-sm text-muted-foreground mb-4">
        Members in the server on each day, from join and leave dates. Add a series to
        track a role combination — a member counts only if they have every role under
        Has and none under Excl.
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
            <Button size="sm" onClick={handleApply}>Apply</Button>
          </div>
        </CardContent>
      </Card>

      <Card className="mb-3 overflow-hidden">
        <div
          className="flex items-end justify-between gap-3 px-5 py-4"
          style={{ borderBottom: "1px solid hsl(var(--border))" }}
        >
          <div>
            <div className="text-sm font-bold tracking-tight">Members in Server</div>
            <div className="text-xs text-muted-foreground mt-0.5">
              Headcount at the end of each day
            </div>
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

      {loading ? (
        <div className="flex justify-center py-4">
          <div className="spinner-border spinner-border-sm" role="status" style={{ color: "#8c1d40" }}>
            <span className="visually-hidden">Loading…</span>
          </div>
        </div>
      ) : (
        <Card className="overflow-hidden p-0">
          {datasets.every((ds) => !ds.data.length) ? (
            <p className="text-sm text-muted-foreground p-3 mb-0">No membership data in this range.</p>
          ) : (
            datasets.map((ds, i) => (
              <div
                key={series[i].id}
                style={{ borderBottom: i < datasets.length - 1 ? "1px solid hsl(var(--border))" : "none" }}
              >
                <SeriesSummary label={ds.label} color={ds.color} data={ds.data} />
              </div>
            ))
          )}
        </Card>
      )}
    </>
  );
}
