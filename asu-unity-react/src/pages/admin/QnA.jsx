import { useState, useEffect } from "react";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";

const todayISO = () => new Date().toISOString().slice(0, 10);
const yearStartISO = () => {
  const d = new Date();
  d.setMonth(0, 1);
  return d.toISOString().slice(0, 10);
};

const STATUS_META = {
  satisfied:  { label: "Bot answered",       color: "#10b981" },
  needs_help: { label: "Needed staff help",   color: "#f59e0b" },
  pending:    { label: "Pending feedback",    color: "#3b82f6" },
  no_bot_msg: { label: "No bot message",      color: "#6b7280" },
};

function StatCard({ value, label, icon, color }) {
  const c = color || "#8c1d40";
  return (
    <Card className="relative overflow-hidden transition-shadow hover:shadow-md">
      <div className="absolute top-0 left-0 w-1 h-full rounded-l-lg" style={{ background: c }} />
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
  );
}

function BackfillStatus({ status, onTrigger }) {
  if (!status) return null;
  const isRunning = status.backfill_running;
  const s = status.status;

  return (
    <div
      className="flex items-center gap-3 text-sm px-4 py-2.5 rounded-lg mb-6"
      style={{
        background: isRunning ? "#3b82f618" : s === "done" ? "#10b98118" : "#6b728018",
        border: `1px solid ${isRunning ? "#3b82f6" : s === "done" ? "#10b981" : "#6b7280"}44`,
      }}
    >
      {isRunning
        ? <><i className="fas fa-spinner fa-spin" style={{ color: "#3b82f6" }} /> Backfill running — {status.threads_processed} / {status.threads_total} threads</>
        : s === "done"
          ? <><i className="fas fa-check-circle" style={{ color: "#10b981" }} /> Backfill complete — {status.posts_upserted} posts, {status.contributions_inserted} contributions</>
          : s === "failed"
            ? <><i className="fas fa-exclamation-circle" style={{ color: "#ef4444" }} /> Backfill failed: {status.error}</>
            : <><i className="fas fa-info-circle" style={{ color: "#6b7280" }} /> No backfill run yet</>
      }
      <Button
        size="sm"
        variant="outline"
        className="ml-auto h-7 text-xs"
        onClick={onTrigger}
        disabled={isRunning}
      >
        {isRunning ? "Running…" : "Run Backfill"}
      </Button>
    </div>
  );
}

export default function QnA() {
  const [qnaStats, setQnaStats] = useState(null);
  const [ggStats, setGgStats] = useState(null);
  const [backfillStatus, setBackfillStatus] = useState(null);
  const [loading, setLoading] = useState(true);
  const [fromDate, setFromDate] = useState(yearStartISO());
  const [toDate, setToDate] = useState(todayISO());
  const [applied, setApplied] = useState({ from: yearStartISO(), to: todayISO() });
  const [expandedGuide, setExpandedGuide] = useState(null);

  // Poll backfill status while running
  useEffect(() => {
    let interval;
    const fetchStatus = () =>
      fetch("/api/admin/qna/backfill/status")
        .then((r) => r.json())
        .then((d) => {
          setBackfillStatus(d);
          if (!d.backfill_running) clearInterval(interval);
        })
        .catch(() => {});
    fetchStatus();
    interval = setInterval(fetchStatus, 3000);
    return () => clearInterval(interval);
  }, []);

  // Fetch QnA stats (no date filter — all-time counts)
  useEffect(() => {
    fetch("/api/admin/qna/stats")
      .then((r) => r.json())
      .then(setQnaStats)
      .catch(() => {});
  }, []);

  // Fetch Gold Guide stats with date filter
  useEffect(() => {
    setLoading(true);
    fetch(
      `/api/admin/qna/gold-guide-stats?from_date=${encodeURIComponent(applied.from)}&to_date=${encodeURIComponent(applied.to)}`
    )
      .then((r) => r.json())
      .then((d) => { setGgStats(d); setLoading(false); })
      .catch(() => setLoading(false));
  }, [applied]);

  const handleApply = () => setApplied({ from: fromDate, to: toDate });

  const triggerBackfill = () =>
    fetch("/api/admin/qna/backfill", { method: "POST" })
      .then((r) => r.json())
      .then(() => {
        // Start polling
        setBackfillStatus((prev) => ({ ...prev, backfill_running: true }));
      })
      .catch(() => {});

  const total = qnaStats?.total ?? 0;
  const byStatus = qnaStats?.by_status ?? {};

  return (
    <>
      <h2 className="text-2xl font-bold mb-1">Q&amp;A Analytics</h2>
      <p className="text-sm text-muted-foreground mb-6">
        Forum post stats and Gold Guide contribution tracking.
      </p>

      <BackfillStatus status={backfillStatus} onTrigger={triggerBackfill} />

      {/* ── Top stat cards ── */}
      <div className="grid grid-cols-2 xl:grid-cols-4 gap-3 mb-8">
        <StatCard value={total}                            label="Total Posts"         icon="fa-comments"     color="#8c1d40" />
        <StatCard value={byStatus.satisfied}              label="Bot Answered"         icon="fa-robot"        color="#10b981" />
        <StatCard value={byStatus.needs_help}             label="Needed Staff Help"    icon="fa-hand-paper"   color="#f59e0b" />
        <StatCard value={byStatus.pending}                label="Pending Feedback"     icon="fa-hourglass"    color="#3b82f6" />
      </div>

      {/* ── Posts by tag ── */}
      {qnaStats?.by_tag?.length > 0 && (
        <Card className="mb-8">
          <CardContent className="p-5">
            <h3 className="font-semibold text-base mb-3">Posts by Tag</h3>
            <table className="w-full text-sm">
              <thead>
                <tr className="text-xs text-muted-foreground uppercase tracking-wide border-b">
                  <th className="text-left py-2 font-semibold">Tag</th>
                  <th className="text-right py-2 font-semibold w-20">Posts</th>
                  <th className="text-right py-2 font-semibold w-24">Bot ans.</th>
                  <th className="text-right py-2 font-semibold w-24">Needs help</th>
                  <th className="text-right py-2 font-semibold w-24">Pending</th>
                </tr>
              </thead>
              <tbody>
                {qnaStats.by_tag.map((row) => (
                  <tr key={row.tag} className="border-b last:border-0 hover:bg-muted/30 transition-colors">
                    <td className="py-2 font-medium">{row.tag}</td>
                    <td className="text-right py-2 tabular-nums">{row.total}</td>
                    <td className="text-right py-2 tabular-nums text-emerald-600">{row.by_status?.satisfied ?? 0}</td>
                    <td className="text-right py-2 tabular-nums text-amber-500">{row.by_status?.needs_help ?? 0}</td>
                    <td className="text-right py-2 tabular-nums text-blue-500">{row.by_status?.pending ?? 0}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </CardContent>
        </Card>
      )}

      {/* ── Gold Guide contributions ── */}
      <div className="flex items-center justify-between mb-4 flex-wrap gap-2">
        <div>
          <h3 className="font-semibold text-base mb-0">Gold Guide Contributions</h3>
          <p className="text-xs text-muted-foreground">
            Messages posted by Gold Guides in Q&amp;A threads.
          </p>
        </div>
        <div className="flex items-end gap-2 flex-wrap">
          <div>
            <Label className="text-xs font-semibold mb-1 block">From</Label>
            <Input type="date" className="h-8 text-sm w-36" value={fromDate} onChange={(e) => setFromDate(e.target.value)} />
          </div>
          <div>
            <Label className="text-xs font-semibold mb-1 block">To</Label>
            <Input type="date" className="h-8 text-sm w-36" value={toDate} onChange={(e) => setToDate(e.target.value)} />
          </div>
          <Button size="sm" onClick={handleApply} disabled={loading}>Apply</Button>
        </div>
      </div>

      {loading && !ggStats ? (
        <div className="flex justify-center py-10">
          <div className="spinner-border" role="status" style={{ color: "#8c1d40" }}>
            <span className="visually-hidden">Loading…</span>
          </div>
        </div>
      ) : ggStats?.gold_guides?.length === 0 ? (
        <Card><CardContent className="py-10 text-center text-muted-foreground text-sm">No Gold Guide contributions in this period.</CardContent></Card>
      ) : (
        <Card>
          <CardContent className="p-0">
            <div className="px-5 py-3 border-b flex items-center justify-between">
              <span className="text-xs text-muted-foreground">
                {ggStats?.total_contributions ?? 0} total contributions · {ggStats?.gold_guides?.length ?? 0} guides active
              </span>
            </div>
            <table className="w-full text-sm">
              <thead>
                <tr className="text-xs text-muted-foreground uppercase tracking-wide border-b">
                  <th className="text-left px-5 py-2.5 font-semibold">Gold Guide</th>
                  <th className="text-right px-5 py-2.5 font-semibold w-32">Contributions</th>
                  <th className="text-right px-5 py-2.5 font-semibold w-28">Channels</th>
                  <th className="w-10" />
                </tr>
              </thead>
              <tbody>
                {ggStats?.gold_guides?.map((guide) => (
                  <>
                    <tr
                      key={guide.discord_id}
                      className="border-b last:border-0 hover:bg-muted/30 transition-colors cursor-pointer"
                      onClick={() => setExpandedGuide(expandedGuide === guide.discord_id ? null : guide.discord_id)}
                    >
                      <td className="px-5 py-2.5 font-medium flex items-center gap-2">
                        <span
                          className="w-7 h-7 rounded-full flex items-center justify-center text-xs font-bold shrink-0"
                          style={{ background: "#8c1d4020", color: "#8c1d40" }}
                        >
                          {(guide.username || "?")[0].toUpperCase()}
                        </span>
                        {guide.username ?? guide.discord_id}
                      </td>
                      <td className="px-5 py-2.5 text-right tabular-nums font-semibold">
                        {guide.total_contributions}
                      </td>
                      <td className="px-5 py-2.5 text-right">
                        <Badge variant="secondary">{guide.by_channel?.length ?? 0}</Badge>
                      </td>
                      <td className="pr-4 text-muted-foreground text-xs text-right">
                        <i className={`fas fa-chevron-${expandedGuide === guide.discord_id ? "up" : "down"}`} />
                      </td>
                    </tr>
                    {expandedGuide === guide.discord_id && (
                      <tr key={`${guide.discord_id}-detail`} className="bg-muted/20 border-b">
                        <td colSpan={4} className="px-10 py-3">
                          <div className="text-xs text-muted-foreground font-semibold uppercase tracking-wide mb-2">
                            Breakdown by channel
                          </div>
                          <div className="flex flex-col gap-1.5">
                            {guide.by_channel?.map((ch) => (
                              <div key={ch.channel_id} className="flex items-center justify-between">
                                <span className="text-sm">
                                  <i className="fas fa-hashtag text-xs mr-1.5 text-muted-foreground" />
                                  {ch.channel_name ?? ch.channel_id}
                                </span>
                                <span className="tabular-nums font-semibold text-sm">{ch.count}</span>
                              </div>
                            ))}
                          </div>
                        </td>
                      </tr>
                    )}
                  </>
                ))}
              </tbody>
            </table>
          </CardContent>
        </Card>
      )}
    </>
  );
}
