import { useState, useEffect } from "react";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { getUrlParam, replaceUrlParams } from "@/utils/adminUrl";

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
      <div className="flex justify-between text-sm mb-1">
        <span className="truncate mr-2" title={name}>{name}</span>
        <span className="text-muted-foreground shrink-0">
          {count.toLocaleString()} <span className="opacity-50">({pct}%)</span>
        </span>
      </div>
      <div className="h-[5px] rounded-[3px] bg-black/[0.07] overflow-hidden">
        <div
          className="h-full rounded-[3px] transition-[width] duration-300 ease-out"
          style={{ width: `${pct}%`, background: "#8c1d40" }}
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
    <div className="sm:col-span-1">
      <Card className="h-full relative overflow-hidden">
        <div
          className="absolute top-0 left-0 w-1 h-full rounded-l-lg"
          style={{ background: meta.color }}
        />
        <CardContent className="p-3 pl-5">
          {/* Header */}
          <div className="flex items-center gap-2 mb-3">
            <div
              className="w-11 h-11 rounded-[10px] flex items-center justify-center shrink-0"
              style={{ background: `${meta.color}18`, color: meta.color }}
            >
              <i className={`fas ${meta.icon} fa-sm`} />
            </div>
            <div className="flex-1 overflow-hidden">
              <h6 className="text-sm font-semibold mb-0 truncate">{cat.name} Roles</h6>
              <div className="text-xs text-muted-foreground">
                {cat.users_with.toLocaleString()} of {total.toLocaleString()} have this
              </div>
            </div>
            <Badge
              className="shrink-0 rounded-full text-xs"
              style={{ background: meta.color, color: "#fff" }}
            >
              {coveragePct}%
            </Badge>
          </div>

          {/* Coverage bar */}
          <div className="h-2 rounded-[6px] bg-black/[0.07] overflow-hidden mb-1">
            <div
              className="h-full rounded-[6px] transition-[width] duration-500 ease-out"
              style={{ width: `${coveragePct}%`, background: meta.color }}
            />
          </div>
          <div className="flex justify-between text-xs text-muted-foreground mb-3">
            <span>{cat.users_with.toLocaleString()} have</span>
            <span>{cat.users_missing.toLocaleString()} missing</span>
          </div>

          {/* Role breakdown */}
          {activeRoles.length > 0 ? (
            <div className="pt-3 mt-1 border-t border-black/[0.06]">
              {activeRoles.map((r) => (
                <RoleBar key={r.role} name={r.role} count={r.count} total={total} />
              ))}
            </div>
          ) : (
            <p className="text-xs text-muted-foreground italic mb-0">No role data for this period.</p>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

function SummaryCard({ value, label, icon, color }) {
  const c = color || "#8c1d40";
  return (
    <div className="sm:col-span-1">
      <Card className="relative overflow-hidden">
        <div
          className="absolute top-0 left-0 w-1 h-full rounded-l-lg"
          style={{ background: c }}
        />
        <CardContent className="p-3 pl-5 flex items-center gap-3">
          <div
            className="w-11 h-11 rounded-[10px] flex items-center justify-center shrink-0"
            style={{ background: `${c}18`, color: c }}
          >
            <i className={`fas ${icon} fa-lg`} />
          </div>
          <div>
            <div className="text-[28px] font-bold leading-none tracking-tight">{value ?? "—"}</div>
            <div className="text-sm text-muted-foreground mt-1">{label}</div>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

export default function MemberStats() {
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(true);
  const [fromDate, setFromDate] = useState(() => getUrlParam("from_date", ""));
  const [toDate, setToDate] = useState(() => getUrlParam("to_date", ""));
  const [applied, setApplied] = useState(() => ({
    from: getUrlParam("from_date", ""),
    to: getUrlParam("to_date", ""),
  }));

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

  const handleApply = () => {
    setApplied({ from: fromDate, to: toDate });
    replaceUrlParams({ from_date: fromDate, to_date: toDate });
  };

  const handlePreset = (preset) => {
    if (preset === "alltime") {
      setFromDate(""); setToDate("");
      setApplied({ from: "", to: "" });
      replaceUrlParams({ from_date: "", to_date: "" });
    } else if (preset === "month") {
      const f = monthStartISO(), t = todayISO();
      setFromDate(f); setToDate(t);
      setApplied({ from: f, to: t });
      replaceUrlParams({ from_date: f, to_date: t });
    } else if (preset === "today") {
      const t = todayISO();
      setFromDate(t); setToDate(t);
      setApplied({ from: t, to: t });
      replaceUrlParams({ from_date: t, to_date: t });
    }
  };

  if (loading && !stats) {
    return (
      <div className="flex justify-center py-20">
        <div className="spinner-border" role="status" style={{ color: "#8c1d40" }}>
          <span className="visually-hidden">Loading…</span>
        </div>
      </div>
    );
  }

  const total = stats?.total_verified ?? 0;
  const periodLabel = applied.from || applied.to
    ? `${applied.from || "start"} → ${applied.to || "today"}`
    : "All time";

  const requiredCats = ["Academic Level", "College", "Campus", "Residency"];
  const withAllRequired = stats?.categories
    ? requiredCats.reduce((min, name) => {
        const cat = stats.categories.find((c) => c.name === name);
        return cat ? Math.min(min, cat.users_with) : min;
      }, total)
    : 0;

  return (
    <>
      <h2 className="text-2xl font-bold mb-1">Member Stats</h2>
      <p className="text-sm text-muted-foreground mb-6">
        Role coverage for verified members — mirrors the{" "}
        <code>get_studet_data.py</code> report.
      </p>

      {/* Filters */}
      <Card className="mb-6">
        <CardContent className="p-3">
          <div className="flex items-end gap-2 flex-wrap">
            <div>
              <Label className="text-xs font-semibold mb-1 block">From</Label>
              <Input
                type="date"
                className="h-8 text-sm w-36"
                value={fromDate}
                onChange={(e) => setFromDate(e.target.value)}
              />
            </div>
            <div>
              <Label className="text-xs font-semibold mb-1 block">To</Label>
              <Input
                type="date"
                className="h-8 text-sm w-36"
                value={toDate}
                onChange={(e) => setToDate(e.target.value)}
              />
            </div>
            <Button size="sm" onClick={handleApply} disabled={loading}>
              Apply
            </Button>
            <div className="w-px h-6 bg-border self-center mx-1" />
            <Button size="sm" variant="outline" onClick={() => handlePreset("today")}>
              Today
            </Button>
            <Button size="sm" variant="outline" onClick={() => handlePreset("month")}>
              This Month
            </Button>
            <Button size="sm" variant="outline" onClick={() => handlePreset("alltime")}>
              All Time
            </Button>
          </div>
          {(applied.from || applied.to) && (
            <p className="text-xs text-muted-foreground mt-2 mb-0">
              Showing verified members: <strong>{periodLabel}</strong>
            </p>
          )}
        </CardContent>
      </Card>

      {/* Summary cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 mb-6">
        <SummaryCard
          value={total.toLocaleString()}
          label="Verified Members"
          icon="fa-user-check"
          color="#8c1d40"
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
        <div className="flex justify-center py-4">
          <div className="spinner-border spinner-border-sm" role="status" style={{ color: "#8c1d40" }}>
            <span className="visually-hidden">Loading…</span>
          </div>
        </div>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-3">
          {stats?.categories?.map((cat) => (
            <CategoryCard key={cat.name} cat={cat} total={total} />
          ))}
        </div>
      )}
    </>
  );
}
