import { useState, useEffect } from "react";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { getUrlParam, replaceUrlParams } from "@/utils/adminUrl";
import { todayISO, monthStartISO } from "@/utils/adminDates";

function StatCard({ value, label, icon, color }) {
  const c = color || "#8c1d40";
  return (
    <div className="sm:col-span-1">
      <Card className="h-full relative overflow-hidden transition-shadow hover:shadow-md">
        <div
          className="absolute top-0 left-0 w-1 h-full rounded-l-lg"
          style={{ background: c }}
        />
        <CardContent className="p-4 flex items-center gap-3 pl-5">
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

export default function Dashboard() {
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(true);
  const [fromDate, setFromDate] = useState(() => getUrlParam("from_date", monthStartISO()));
  const [toDate, setToDate] = useState(() => getUrlParam("to_date", todayISO()));
  const [applied, setApplied] = useState(() => ({
    from: getUrlParam("from_date", monthStartISO()),
    to: getUrlParam("to_date", todayISO()),
  }));
  const [purgeStatus, setPurgeStatus] = useState(null);
  const [purgeRunning, setPurgeRunning] = useState(false);

  useEffect(() => {
    setLoading(true);
    fetch(`/api/admin/stats?from_date=${encodeURIComponent(applied.from)}&to_date=${encodeURIComponent(applied.to)}`)
      .then((r) => r.json())
      .then((d) => { setStats(d); setLoading(false); })
      .catch(() => setLoading(false));
  }, [applied]);

  const handleApply = () => {
    setApplied({ from: fromDate, to: toDate });
    replaceUrlParams({ from_date: fromDate, to_date: toDate });
  };

  const pollPurgeStatus = () => {
    fetch("/api/admin/purge-unregistered-roles/status")
      .then((r) => r.json())
      .then((d) => {
        setPurgeRunning(d.running);
        setPurgeStatus(d.last);
        if (d.running) setTimeout(pollPurgeStatus, 2000);
      })
      .catch(() => setPurgeRunning(false));
  };

  const handlePurge = () => {
    if (!window.confirm(
      "This will remove the Verified role and all managed roles from every Discord member who has no record in the database.\n\nProceed?"
    )) return;
    setPurgeRunning(true);
    setPurgeStatus(null);
    fetch("/api/admin/purge-unregistered-roles", { method: "POST" })
      .then((r) => r.json())
      .then((d) => {
        if (d.status === "already_running") {
          setPurgeStatus(d.last);
        }
        pollPurgeStatus();
      })
      .catch(() => setPurgeRunning(false));
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

  const retentionDisplay =
    stats?.retention_rate != null ? `${stats.retention_rate}%` : "—";

  return (
    <>
      <h2 className="text-2xl font-bold mb-1">Overview</h2>
      <p className="text-sm text-muted-foreground mb-6">Verification stats across all members.</p>

      {/* All-time stats */}
      <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-3 mb-6">
        <StatCard value={stats?.total_users} label="Total Members" icon="fa-users" color="#8c1d40" />
        <StatCard value={stats?.verified_count} label="Verified" icon="fa-user-check" color="#10b981" />
        <StatCard value={stats?.today_verifications} label="Verified Today" icon="fa-calendar-check" color="#3b82f6" />
      </div>

      {/* Period stats */}
      <div className="flex items-center justify-between mb-4 flex-wrap gap-2">
        <h5 className="text-base font-semibold mb-0">Period Stats</h5>
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
        </div>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-3">
        <StatCard value={stats?.verified_leaves} label="Verified Leaves" icon="fa-sign-out-alt" color="#f59e0b" />
        <StatCard value={stats?.verified_at_end} label="Verified Users at End" icon="fa-users" color="#8c1d40" />
        <StatCard value={retentionDisplay} label="Retention Rate" icon="fa-chart-line" color="#10b981" />
      </div>

      {/* Maintenance */}
      <div className="mt-8">
        <h5 className="text-base font-semibold mb-3">Maintenance</h5>
        <Card>
          <CardContent className="p-4 flex flex-col gap-3">
            <div className="flex items-start justify-between gap-4 flex-wrap">
              <div>
                <div className="font-medium text-sm">Purge Roles from Non-Registered Members</div>
                <div className="text-xs text-muted-foreground mt-0.5">
                  Removes Verified and all managed roles from Discord members who have no record in the database.
                </div>
              </div>
              <Button
                size="sm"
                variant="destructive"
                onClick={handlePurge}
                disabled={purgeRunning}
              >
                {purgeRunning ? (
                  <><i className="fas fa-spinner fa-spin mr-1.5" />Running…</>
                ) : (
                  <><i className="fas fa-user-slash mr-1.5" />Purge Roles</>
                )}
              </Button>
            </div>
            {purgeStatus && !purgeRunning && (
              <div className={`text-xs rounded px-3 py-2 ${purgeStatus.error ? "bg-red-50 text-red-700" : "bg-green-50 text-green-700"}`}>
                {purgeStatus.error ? (
                  <><i className="fas fa-exclamation-circle mr-1" />Error: {purgeStatus.error}</>
                ) : (
                  <><i className="fas fa-check-circle mr-1" />Done — {purgeStatus.stripped} member{purgeStatus.stripped !== 1 ? "s" : ""} stripped{purgeStatus.errors > 0 ? `, ${purgeStatus.errors} error(s)` : ""}.</>
                )}
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    </>
  );
}
