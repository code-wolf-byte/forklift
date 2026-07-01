import React, { useState, useEffect } from "react";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { getUrlParam, replaceUrlParams } from "@/utils/adminUrl";

const todayISO = () => new Date().toISOString().slice(0, 10);
const monthStartISO = () => {
  const d = new Date();
  d.setDate(1);
  return d.toISOString().slice(0, 10);
};

function NotTracked() {
  return <span className="text-xs text-muted-foreground italic">not tracked</span>;
}

function Tooltip({ text }) {
  return (
    <span className="relative group inline-flex items-center ml-1 cursor-help">
      <i className="fas fa-info-circle text-[10px] text-muted-foreground/40 group-hover:text-muted-foreground/70 transition-colors" />
      <span className="pointer-events-none absolute bottom-full left-1/2 -translate-x-1/2 mb-2 w-56 rounded-md bg-gray-900 px-2.5 py-2 text-[11px] leading-snug text-white opacity-0 shadow-xl transition-opacity group-hover:opacity-100 z-50 text-left whitespace-normal">
        {text}
        <span className="absolute top-full left-1/2 -translate-x-1/2 border-4 border-transparent border-t-gray-900" />
      </span>
    </span>
  );
}

function StatCard({ label, value, icon, color = "#8c1d40", note, tooltip, onClick }) {
  const isNull = value === null || value === undefined;
  return (
    <Card
      className={`relative overflow-hidden ${onClick ? "cursor-pointer hover:shadow-md transition-shadow" : ""}`}
      onClick={onClick}
    >
      <div className="absolute top-0 left-0 w-1 h-full rounded-l-lg" style={{ background: color }} />
      <CardContent className="p-3 pl-5">
        <div className="flex items-center gap-2 mb-1">
          {icon && (
            <div
              className="w-8 h-8 rounded-lg flex items-center justify-center shrink-0"
              style={{ background: `${color}18`, color }}
            >
              <i className={`fas ${icon} fa-sm`} />
            </div>
          )}
          <div className="text-[22px] font-bold leading-none tracking-tight">
            {isNull ? (
              <NotTracked />
            ) : typeof value === "number" ? (
              value.toLocaleString()
            ) : (
              value
            )}
          </div>
        </div>
        <div className="text-xs text-muted-foreground flex items-center">
          {label}
          {tooltip && <Tooltip text={tooltip} />}
        </div>
        {note && <div className="text-[11px] text-muted-foreground/60 mt-0.5">{note}</div>}
      </CardContent>
    </Card>
  );
}

function SectionHeader({ title, icon, subtitle, tooltip, collapsible, collapsed, onToggle }) {
  const content = (
    <>
      {icon && (
        <div
          className="w-8 h-8 rounded-lg flex items-center justify-center shrink-0"
          style={{ background: "#8c1d4018", color: "#8c1d40" }}
        >
          <i className={`fas ${icon} fa-sm`} />
        </div>
      )}
      <div className="min-w-0">
        <h3 className="text-base font-bold mb-0 flex items-center">
          {title}
          {tooltip && <Tooltip text={tooltip} />}
        </h3>
        {subtitle && <p className="text-xs text-muted-foreground mb-0">{subtitle}</p>}
      </div>
      {collapsible && (
        <i
          className={`fas fa-chevron-down fa-sm text-muted-foreground ml-auto shrink-0 transition-transform ${
            collapsed ? "-rotate-90" : ""
          }`}
        />
      )}
    </>
  );

  if (collapsible) {
    return (
      <button
        type="button"
        onClick={onToggle}
        className="w-full flex items-center gap-2.5 mb-3 mt-7 pb-2 border-b text-left cursor-pointer bg-transparent border-x-0 border-t-0 text-inherit"
      >
        {content}
      </button>
    );
  }

  return (
    <div className="flex items-center gap-2.5 mb-3 mt-7 pb-2 border-b">{content}</div>
  );
}

function SubLabel({ children, tooltip }) {
  return (
    <div className="text-[11px] font-bold uppercase tracking-[0.06em] text-muted-foreground mb-2 flex items-center">
      {children}
      {tooltip && <Tooltip text={tooltip} />}
    </div>
  );
}

function ProgressBar({ name, count, total, color = "#8c1d40" }) {
  const pct = total > 0 ? Math.round((count / total) * 100) : 0;
  return (
    <div className="mb-2">
      <div className="flex justify-between text-sm mb-1">
        <span className="truncate mr-2" title={name}>
          {name}
        </span>
        <span className="text-muted-foreground shrink-0 tabular-nums">
          {count.toLocaleString()} <span className="opacity-50">({pct}%)</span>
        </span>
      </div>
      <div className="h-[4px] rounded-full bg-black/[0.07] overflow-hidden">
        <div
          className="h-full rounded-full transition-[width] duration-300"
          style={{ width: `${pct}%`, background: color }}
        />
      </div>
    </div>
  );
}

export default function Analytics() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [fromDate, setFromDate] = useState(() => getUrlParam("from_date", ""));
  const [toDate, setToDate] = useState(() => getUrlParam("to_date", ""));
  const [applied, setApplied] = useState(() => ({
    from: getUrlParam("from_date", ""),
    to: getUrlParam("to_date", ""),
  }));
  const [liveStats, setLiveStats] = useState(null);
  const [sfStatus, setSfStatus] = useState(null);
  const [sfRefreshing, setSfRefreshing] = useState(false);
  const [channelsCollapsed, setChannelsCollapsed] = useState(true);
  const [demographicsCollapsed, setDemographicsCollapsed] = useState(true);
  const [expandedChannels, setExpandedChannels] = useState(new Set());
  const [goldGuideListCollapsed, setGoldGuideListCollapsed] = useState(true);
  const [volunteerListCollapsed, setVolunteerListCollapsed] = useState(true);
  const [deleteModalOpen, setDeleteModalOpen] = useState(false);
  const [deleteRows, setDeleteRows] = useState(null);
  const [deleteLoading, setDeleteLoading] = useState(false);

  useEffect(() => {
    setLoading(true);
    const params = new URLSearchParams();
    if (applied.from) params.set("from_date", applied.from);
    if (applied.to) params.set("to_date", applied.to);
    fetch(`/api/admin/analytics?${params}`)
      .then((r) => r.json())
      .then((d) => {
        setData(d);
        setLoading(false);
      })
      .catch(() => setLoading(false));
  }, [applied]);

  useEffect(() => {
    fetch("/api/admin/live-member-counts")
      .then((r) => r.json())
      .then((d) => setLiveStats(d))
      .catch(() => {});
  }, []);

  useEffect(() => {
    fetch("/api/admin/salesforce/status")
      .then((r) => r.json())
      .then((d) => setSfStatus(d))
      .catch(() => {});
  }, []);

  const handleSfRefresh = () => {
    setSfRefreshing(true);
    fetch("/api/admin/salesforce/refresh", { method: "POST" })
      .then((r) => r.json())
      .then(() => {
        setSfStatus((prev) => ({ ...prev, refresh_running: true }));
        const poll = setInterval(() => {
          fetch("/api/admin/salesforce/status")
            .then((r) => r.json())
            .then((s) => {
              setSfStatus(s);
              if (!s.refresh_running) {
                clearInterval(poll);
                setSfRefreshing(false);
                setApplied((prev) => ({ ...prev }));
              }
            })
            .catch(() => {});
        }, 3000);
      })
      .catch(() => setSfRefreshing(false));
  };

  const toggleChannel = (channelId) => {
    setExpandedChannels((prev) => {
      const next = new Set(prev);
      if (next.has(channelId)) next.delete(channelId);
      else next.add(channelId);
      return next;
    });
  };

  const openDeleteModal = () => {
    setDeleteModalOpen(true);
    setDeleteLoading(true);
    const params = new URLSearchParams();
    if (applied.from) params.set("from_date", applied.from);
    if (applied.to) params.set("to_date", applied.to);
    fetch(`/api/admin/analytics/moderation/message-deletes?${params}`)
      .then((r) => r.json())
      .then((d) => {
        setDeleteRows(d.rows || []);
        setDeleteLoading(false);
      })
      .catch(() => setDeleteLoading(false));
  };

  const handleApply = () => {
    setApplied({ from: fromDate, to: toDate });
    replaceUrlParams({ from_date: fromDate, to_date: toDate });
  };

  const handlePreset = (preset) => {
    if (preset === "alltime") {
      setFromDate("");
      setToDate("");
      setApplied({ from: "", to: "" });
      replaceUrlParams({ from_date: "", to_date: "" });
    } else if (preset === "month") {
      const f = monthStartISO(), t = todayISO();
      setFromDate(f);
      setToDate(t);
      setApplied({ from: f, to: t });
      replaceUrlParams({ from_date: f, to_date: t });
    } else if (preset === "today") {
      const t = todayISO();
      setFromDate(t);
      setToDate(t);
      setApplied({ from: t, to: t });
      replaceUrlParams({ from_date: t, to_date: t });
    }
  };

  if (loading && !data) {
    return (
      <div className="flex justify-center py-20">
        <div className="spinner-border" role="status" style={{ color: "#8c1d40" }}>
          <span className="visually-hidden">Loading…</span>
        </div>
      </div>
    );
  }

  const d = data || {};
  const ca = d.core_activity || {};
  const gf = d.growth_funnel || {};
  const onboarding = gf.onboarding || {};
  const retention = gf.retention || {};
  const demo = d.demographics || {};
  const channels = d.channel_engagement || [];
  const programs = d.programs || {};
  const gg = programs.gold_guides || {};
  const vol = programs.volunteers || {};
  const forums = d.forums || {};
  const askAsu = forums.ask_asu_staff || {};
  const moderation = d.moderation || {};

  const splitVerified = onboarding.verified_users || 0;
  const splitUnverified = onboarding.unverified_users || 0;
  const splitTotal = onboarding.total_joins || 0;

  const collegeEntries = Object.entries(demo.college || {}).sort(([, a], [, b]) => b - a);
  const collegeTotal = collegeEntries.reduce((s, [, c]) => s + c, 0);

  const studentEntries = Object.entries(demo.student_role || {});
  const studentTotal = studentEntries.reduce((s, [, c]) => s + c, 0);

  const residencyEntries = Object.entries(demo.residency || {});
  const residencyTotal = residencyEntries.reduce((s, [, c]) => s + c, 0);

  const campusEntries = Object.entries(demo.campus || {});
  const campusTotal = campusEntries.reduce((s, [, c]) => s + c, 0);

  const periodLabel =
    applied.from || applied.to
      ? `${applied.from || "start"} → ${applied.to || "today"}`
      : "All time";

  return (
    <>
      <h2 className="text-2xl font-bold mb-1">Analytics</h2>
      <p className="text-sm text-muted-foreground mb-4">
        Comprehensive server metrics across engagement, demographics, programs, and forums.
      </p>

      {/* ── Live server membership ── */}
      <div className="grid grid-cols-2 gap-3 mb-5">
        <StatCard
          label="Verified Members"
          value={liveStats ? liveStats.verified : undefined}
          icon="fa-user-check"
          color="#10b981"
          tooltip="Current number of verified members in the Discord server. Live from the bot cache — not affected by the date filter."
        />
        <StatCard
          label="Unverified Members"
          value={liveStats ? liveStats.unverified : undefined}
          icon="fa-user-clock"
          color="#f59e0b"
          tooltip="Current number of members who have joined but not yet completed verification. Live — not affected by the date filter."
        />
      </div>

      {/* ── Date filter ── */}
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
              Showing: <strong>{periodLabel}</strong>
            </p>
          )}
        </CardContent>
      </Card>

      {/* ── Salesforce Data Status ── */}
      {sfStatus && (
        <Card className="mb-4">
          <CardContent className="p-3">
            <div className="flex items-center justify-between flex-wrap gap-2">
              <div className="flex items-center gap-3 text-sm">
                <i className="fas fa-cloud text-muted-foreground" />
                <span className="font-medium">Salesforce Profile Cache</span>
                <span className="text-muted-foreground">
                  {sfStatus.profiles_cached.toLocaleString()} profiles
                  {sfStatus.international_count > 0 &&
                    ` · ${sfStatus.international_count.toLocaleString()} international`}
                  {sfStatus.last_fetched && ` · Last refreshed ${sfStatus.last_fetched.slice(0, 10)}`}
                  {sfStatus.error_count > 0 && (
                    <span className="text-amber-500 ml-1">· {sfStatus.error_count} errors</span>
                  )}
                </span>
              </div>
              <Button
                size="sm"
                variant="outline"
                onClick={handleSfRefresh}
                disabled={sfRefreshing || sfStatus.refresh_running}
              >
                {sfRefreshing || sfStatus.refresh_running ? (
                  <>
                    <i className="fas fa-spinner fa-spin mr-1.5" />
                    Refreshing…
                  </>
                ) : (
                  <>
                    <i className="fas fa-sync-alt mr-1.5" />
                    Refresh Salesforce
                  </>
                )}
              </Button>
            </div>
          </CardContent>
        </Card>
      )}

      {loading && (
        <div className="flex justify-center py-4 mb-2">
          <div
            className="spinner-border spinner-border-sm"
            role="status"
            style={{ color: "#8c1d40" }}
          >
            <span className="visually-hidden">Loading…</span>
          </div>
        </div>
      )}

      {/* ════════════════════════════════════════════════════════════════════════
          Core Activity
      ════════════════════════════════════════════════════════════════════════ */}
      <SectionHeader
        title="Core Activity"
        icon="fa-bolt"
        subtitle="High-level engagement signals for the selected period"
        tooltip="Top-line metrics showing how active the server is. All counts are filtered by the selected date range."
      />
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-6">
        <StatCard
          label="Messages Sent"
          value={ca.messages_sent}
          icon="fa-comment"
          tooltip="Total messages logged across all tracked channels during the period. Accuracy depends on the backfill being complete — gaps exist for channels or time ranges not yet backfilled."
        />
        <StatCard
          label="Unique Talkers"
          value={ca.unique_talkers}
          icon="fa-user"
          color="#3b82f6"
          tooltip="Distinct members who sent at least one message in any tracked channel during the period. Subject to the same backfill coverage as Messages Sent — under-counts if backfill is incomplete."
        />
        <StatCard
          label="Voice Hours"
          value={ca.voice_hours != null ? `${ca.voice_hours}h` : null}
          icon="fa-microphone"
          color="#10b981"
          tooltip="Total time members spent in voice channels, summed across all completed sessions (left_at is set). Sessions clipped to the selected period boundaries. Ongoing sessions with no left_at are excluded."
        />
        <StatCard
          label="Unique Speakers"
          value={ca.unique_speakers}
          icon="fa-headphones"
          color="#f59e0b"
          tooltip="Distinct members who joined at least one voice channel during the period. Only counts members with at least one completed session — members currently in voice with no left_at are excluded."
        />
      </div>

      {/* ════════════════════════════════════════════════════════════════════════
          Growth & Funnel
      ════════════════════════════════════════════════════════════════════════ */}
      <SectionHeader
        title="Growth & Funnel"
        icon="fa-filter"
        subtitle="Onboarding conversion and member retention"
        tooltip="Tracks how new members move through the join → verify pipeline and how well the server retains verified members over time."
      />
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-5 mb-6">
        {/* Onboarding */}
        <div>
          <SubLabel tooltip="All counts are based on joined_at from the discord_members table — the date the member joined the server, not when they verified.">
            Onboarding
          </SubLabel>
          <p className="text-[11px] text-amber-600 dark:text-amber-400 mb-2">
            <i className="fas fa-exclamation-triangle mr-1" />
            Join data is only recorded since May 2026 and is not historically accurate for earlier dates.
          </p>
          <div className="grid grid-cols-2 gap-3">
            <StatCard
              label="Total Joins"
              value={onboarding.total_joins}
              icon="fa-sign-in-alt"
              tooltip="Members whose joined_at falls within the period. Recorded by the on_member_join bot event. May under-count if the bot was offline during joins."
            />
            <StatCard
              label="Verified Users"
              value={onboarding.verified_users}
              icon="fa-user-check"
              color="#10b981"
              tooltip="Of members who joined in the period, how many are currently verified. Filtered by joined_at — not verified_at — so a member who joined now but verified later would still count here once verified."
            />
            <StatCard
              label="Unverified Users"
              value={onboarding.unverified_users}
              icon="fa-user-clock"
              color="#f59e0b"
              tooltip="Of members who joined in the period, how many have not completed verification. Calculated as total joins minus verified users."
            />
            <StatCard
              label="Venue Users"
              value={onboarding.venue_users}
              icon="fa-map-marker-alt"
              color="#6b7280"
              tooltip="Members acquired through in-person venue QR codes (e.g., orientation events). Not currently tracked — requires a separate acquisition source flag."
            />
          </div>
        </div>

        {/* Retention */}
        <div>
          <SubLabel tooltip="Retention measures how well the server keeps verified members who were already present before the selected period.">
            Retention
          </SubLabel>
          <StatCard
            label="Retention Rate"
            value={
              retention.verified_retention_rate !== null &&
              retention.verified_retention_rate !== undefined
                ? `${retention.verified_retention_rate}%`
                : null
            }
            icon="fa-chart-line"
            color="#10b981"
            note={applied.from ? periodLabel : "Select a date range"}
            tooltip="% of verified members who were present at the start of the period and had not left by the end. Formula: (verified_at_start − leaves in period) ÷ verified_at_start × 100. A member counts as 'left' when the bot records an on_member_remove event. Requires a date range to calculate."
            className="mb-3"
          />
          {splitTotal > 0 && (
            <Card>
              <CardContent className="p-3">
                <SubLabel tooltip="Of all members who joined during the selected period, what share completed verification. Both numbers come from the same joined_at-filtered query so they always sum to total joins.">
                  Verified vs Unverified Split
                </SubLabel>
                <ProgressBar
                  name="Verified"
                  count={splitVerified}
                  total={splitTotal}
                  color="#10b981"
                />
                <ProgressBar
                  name="Unverified"
                  count={splitUnverified}
                  total={splitTotal}
                  color="#f59e0b"
                />
              </CardContent>
            </Card>
          )}
        </div>
      </div>

      {/* ════════════════════════════════════════════════════════════════════════
          Channel Engagement
      ════════════════════════════════════════════════════════════════════════ */}
      <SectionHeader
        title="Channel Engagement"
        icon="fa-hashtag"
        subtitle="Top 25 channels by message volume for the period"
        tooltip="Ranks channels by message count. Voice Activity shows accumulated voice time in the same channel during the period — only applicable to voice channels."
        collapsible
        collapsed={channelsCollapsed}
        onToggle={() => setChannelsCollapsed((c) => !c)}
      />
      {channelsCollapsed ? null : channels.length > 0 ? (
        <Card className="mb-6">
          <CardContent className="p-0">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-xs text-muted-foreground uppercase tracking-wide border-b">
                  <th className="text-left px-4 py-2.5 font-semibold w-10">#</th>
                  <th className="text-left px-4 py-2.5 font-semibold">Channel Name</th>
                  <th className="text-right px-4 py-2.5 font-semibold w-32">Messages</th>
                  <th className="text-right px-4 py-2.5 font-semibold w-32">
                    Voice Activity
                    <Tooltip text="Total hours members spent in this voice channel during the period. Text channels show 'not tracked'." />
                  </th>
                </tr>
              </thead>
              <tbody>
                {channels.map((ch) => {
                  const hasThreads = ch.threads && ch.threads.length > 0;
                  const isExpanded = expandedChannels.has(ch.channel_id);
                  return (
                    <React.Fragment key={ch.channel_id}>
                      <tr
                        className={`border-b transition-colors ${hasThreads ? "cursor-pointer hover:bg-muted/40" : "hover:bg-muted/30"}`}
                        onClick={hasThreads ? () => toggleChannel(ch.channel_id) : undefined}
                      >
                        <td className="px-4 py-2 text-muted-foreground tabular-nums">{ch.rank}</td>
                        <td className="px-4 py-2 font-medium">
                          {hasThreads ? (
                            <span className="flex items-center gap-1.5">
                              <i
                                className={`fas fa-chevron-right text-[10px] text-muted-foreground transition-transform duration-200 ${isExpanded ? "rotate-90" : ""}`}
                              />
                              <i className="fas fa-hashtag text-xs text-muted-foreground" />
                              {ch.channel_name}
                              <span className="ml-1.5 text-[10px] font-normal text-muted-foreground/60 bg-muted px-1.5 py-0.5 rounded-full">
                                {ch.threads.length} thread{ch.threads.length !== 1 ? "s" : ""}
                              </span>
                            </span>
                          ) : (
                            <span className="flex items-center gap-1.5">
                              <i className="fas fa-hashtag text-xs text-muted-foreground" />
                              {ch.channel_name}
                            </span>
                          )}
                        </td>
                        <td className="px-4 py-2 text-right tabular-nums font-semibold">
                          {ch.messages.toLocaleString()}
                        </td>
                        <td className="px-4 py-2 text-right tabular-nums">
                          {ch.voice_seconds != null ? (
                            `${(ch.voice_seconds / 3600).toFixed(1)}h`
                          ) : (
                            <NotTracked />
                          )}
                        </td>
                      </tr>
                      {hasThreads && isExpanded &&
                        ch.threads.map((t) => (
                          <tr
                            key={t.channel_id}
                            className="border-b last:border-0 bg-muted/20 hover:bg-muted/40 transition-colors"
                          >
                            <td className="px-4 py-1.5 text-muted-foreground/50 tabular-nums text-xs" />
                            <td className="py-1.5 pr-4 font-normal text-muted-foreground">
                              <span className="flex items-center gap-1.5 pl-8">
                                <i className="fas fa-level-right text-[10px] text-muted-foreground/40" />
                                <i className="fas fa-comment-alt text-[10px] text-muted-foreground/60" />
                                <span className="text-xs">{t.channel_name}</span>
                              </span>
                            </td>
                            <td className="px-4 py-1.5 text-right tabular-nums text-xs font-medium text-muted-foreground">
                              {t.messages.toLocaleString()}
                            </td>
                            <td className="px-4 py-1.5 text-right tabular-nums text-xs text-muted-foreground">
                              {t.voice_seconds != null ? (
                                `${(t.voice_seconds / 3600).toFixed(1)}h`
                              ) : (
                                <NotTracked />
                              )}
                            </td>
                          </tr>
                        ))}
                    </React.Fragment>
                  );
                })}
              </tbody>
            </table>
          </CardContent>
        </Card>
      ) : (
        <Card className="mb-6">
          <CardContent className="py-8 text-center text-muted-foreground text-sm">
            No message data for this period.
          </CardContent>
        </Card>
      )}

      {/* ════════════════════════════════════════════════════════════════════════
          Readership
      ════════════════════════════════════════════════════════════════════════ */}
      <SectionHeader
        title="Readership"
        icon="fa-eye"
        subtitle="Passive engagement — requires Discord Insights access"
        tooltip="Readership tracks members who read channels without posting. Discord does not expose this data via bot API — it requires access to the server's Discord Insights dashboard."
      />
      <Card className="mb-6">
        <CardContent className="py-5 px-5">
          <p className="text-sm text-muted-foreground mb-3">
            Readership data is not accessible via the bot API. View it directly in the Discord Insights dashboard.
            {" "}
            <strong>Note:</strong> Discord Insights only retains the last 120 days of data.
          </p>
          <a
            href={`https://discord.com/developers/servers/1187144343400751234/analytics/engagement?interval=2${applied.from ? `&start=${applied.from}` : ""}&end=${applied.to || new Date().toISOString().slice(0, 10)}`}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-2 text-sm font-medium text-blue-500 hover:text-blue-400 hover:underline"
          >
            <i className="fab fa-discord" />
            Open Discord Insights — Engagement
            <i className="fas fa-external-link-alt text-xs" />
          </a>
        </CardContent>
      </Card>

      {/* ════════════════════════════════════════════════════════════════════════
          Demographics
      ════════════════════════════════════════════════════════════════════════ */}
      <SectionHeader
        title="Demographics"
        icon="fa-chart-pie"
        subtitle="Role breakdown for verified members"
        tooltip="Shows how verified members are distributed across academic level, residency, campus, college, and country of origin. Roles are assigned during Salesforce sync at verification. Date filter applies to verified_at."
        collapsible
        collapsed={demographicsCollapsed}
        onToggle={() => setDemographicsCollapsed((c) => !c)}
      />
      {demographicsCollapsed ? null : <><div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-4 mb-4">
        {/* Student Role */}
        <Card>
          <CardContent className="p-4">
            <SubLabel tooltip="Academic level as determined by the student's active Salesforce opportunity (type field). First Year = First Time Freshman, Transfer = Transfer admit.">
              <i className="fas fa-graduation-cap mr-1.5" />
              Student Role
            </SubLabel>
            {studentEntries.map(([name, count]) => (
              <ProgressBar key={name} name={name} count={count} total={studentTotal} />
            ))}
          </CardContent>
        </Card>

        {/* Residency */}
        <Card>
          <CardContent className="p-4">
            <SubLabel tooltip="Based on the internationalStudent flag and state field from Salesforce. Arizona Resident = in-state, Out of State = not AZ and not international, International = Salesforce internationalStudent = true.">
              <i className="fas fa-home mr-1.5" />
              Residency
            </SubLabel>
            {residencyEntries.map(([name, count]) => (
              <ProgressBar
                key={name}
                name={name}
                count={count}
                total={residencyTotal}
                color="#f59e0b"
              />
            ))}
          </CardContent>
        </Card>

        {/* Campus */}
        <Card>
          <CardContent className="p-4">
            <SubLabel tooltip="Primary campus from the currentLocation field on the student's Salesforce opportunity. Members may only appear in one campus.">
              <i className="fas fa-map-marker-alt mr-1.5" />
              Campus
            </SubLabel>
            {campusEntries.map(([name, count]) => (
              <ProgressBar
                key={name}
                name={name}
                count={count}
                total={campusTotal}
                color="#10b981"
              />
            ))}
          </CardContent>
        </Card>

        {/* International */}
        <Card>
          <CardContent className="p-4">
            <SubLabel tooltip="Country breakdown for verified international students. Sourced from the Salesforce ESB API (contact country + opportunity country fields). Click 'Refresh Salesforce' above to populate or update.">
              <i className="fas fa-globe mr-1.5" />
              International — Country of Origin
            </SubLabel>
            {demo.international_country ? (
              (() => {
                const total = demo.international_country.reduce((s, r) => s + r.count, 0);
                return demo.international_country.slice(0, 12).map((row) => (
                  <ProgressBar
                    key={row.country}
                    name={row.country}
                    count={row.count}
                    total={total}
                    color="#8b5cf6"
                  />
                ));
              })()
            ) : (
              <>
                <p className="text-sm text-muted-foreground mb-1">
                  Country of Origin: <NotTracked />
                </p>
                <p className="text-xs text-muted-foreground/70">
                  Run Salesforce refresh to populate.
                </p>
              </>
            )}
          </CardContent>
        </Card>
      </div>

      {/* College */}
      <SubLabel tooltip="College is derived from the student's program code (collegeProgramCode) via Salesforce and mapped to the corresponding Discord role. Members may belong to one college.">
        College
      </SubLabel>
      <Card className="mb-6">
        <CardContent className="p-4">
          {collegeEntries.length > 0 ? (
            collegeEntries.map(([name, count]) => (
              <ProgressBar
                key={name}
                name={name}
                count={count}
                total={collegeTotal}
                color="#3b82f6"
              />
            ))
          ) : (
            <p className="text-sm text-muted-foreground text-center py-4">
              No role data available.
            </p>
          )}
        </CardContent>
      </Card></>}

      {/* ════════════════════════════════════════════════════════════════════════
          Moderation
      ════════════════════════════════════════════════════════════════════════ */}
      <SectionHeader
        title="Moderation"
        icon="fa-shield-alt"
        subtitle="Bans, unbans, kicks, timeouts, and message deletions"
        tooltip="Tracks moderation actions taken in the server. All events are recorded in the moderation_events table by the bot in real time and backfilled from the Discord audit log on startup."
      />
      <div className="grid grid-cols-2 sm:grid-cols-3 xl:grid-cols-6 gap-3 mb-6">
        <StatCard
          label="Banned (from verifying)"
          value={moderation.banned_users}
          icon="fa-ban"
          color="#ef4444"
          tooltip="Members currently flagged as banned in the database (users.banned = true). These users are blocked from completing the verification flow. Not filtered by date — reflects current state."
        />
        <StatCard
          label="Bans (period)"
          value={moderation.period_bans ?? 0}
          icon="fa-gavel"
          color="#ef4444"
          tooltip="Members banned via the /blacklist command during the selected period. Recorded in moderation_events with event_type = 'ban', including the moderator who issued it."
        />
        <StatCard
          label="Unbans (period)"
          value={moderation.period_unbans ?? 0}
          icon="fa-user-check"
          color="#10b981"
          tooltip="Members unbanned via the /whitelist command during the selected period. Recorded in moderation_events with event_type = 'unban'."
        />
        <StatCard
          label="Kicks (period)"
          value={moderation.period_kicks ?? 0}
          icon="fa-boot"
          color="#f59e0b"
          tooltip="Members kicked from the server during the selected period. Detected via the Discord audit log when a member is removed by a moderator."
        />
        <StatCard
          label="Timeouts (period)"
          value={moderation.period_timeouts ?? 0}
          icon="fa-clock"
          color="#f59e0b"
          tooltip="Members timed out by a moderator during the selected period. Detected when a member's timeout expiry is set via Discord."
        />
        <StatCard
          label="Deleted Messages (period)"
          value={moderation.period_message_deletes ?? 0}
          icon="fa-trash-alt"
          color="#6b7280"
          tooltip="Messages deleted by a moderator during the selected period. Detected via the Discord audit log when a message is removed by someone other than the author. Click to view details."
          onClick={openDeleteModal}
        />
      </div>

      <Dialog open={deleteModalOpen} onOpenChange={setDeleteModalOpen}>
        <DialogContent className="max-w-4xl max-h-[80vh] flex flex-col">
          <DialogHeader>
            <DialogTitle>Deleted Messages — {periodLabel}</DialogTitle>
          </DialogHeader>
          <div className="overflow-y-auto flex-1">
            {deleteLoading ? (
              <div className="flex justify-center py-10">
                <div className="spinner-border spinner-border-sm" role="status" style={{ color: "#8c1d40" }}>
                  <span className="visually-hidden">Loading…</span>
                </div>
              </div>
            ) : deleteRows && deleteRows.length > 0 ? (
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-xs text-muted-foreground uppercase tracking-wide border-b sticky top-0 bg-card">
                    <th className="text-left px-3 py-2 font-semibold">Author</th>
                    <th className="text-left px-3 py-2 font-semibold">Channel</th>
                    <th className="text-left px-3 py-2 font-semibold">Moderator</th>
                    <th className="text-left px-3 py-2 font-semibold">Deleted At</th>
                    <th className="text-left px-3 py-2 font-semibold">Content</th>
                  </tr>
                </thead>
                <tbody>
                  {deleteRows.map((row) => (
                    <tr key={row.message_id} className="border-b last:border-0 align-top">
                      <td className="px-3 py-2 whitespace-nowrap">{row.discord_username || "—"}</td>
                      <td className="px-3 py-2 whitespace-nowrap">
                        {row.channel_name || <NotTracked />}
                      </td>
                      <td className="px-3 py-2 whitespace-nowrap">{row.moderator_username || "—"}</td>
                      <td className="px-3 py-2 whitespace-nowrap">
                        {new Date(row.occurred_at).toLocaleString()}
                      </td>
                      <td className="px-3 py-2 max-w-xs break-words">
                        {row.content || <span className="text-muted-foreground italic">no content</span>}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : (
              <p className="text-sm text-muted-foreground text-center py-8">
                No deleted messages for this period.
              </p>
            )}
          </div>
        </DialogContent>
      </Dialog>

      {/* ════════════════════════════════════════════════════════════════════════
          Programs
      ════════════════════════════════════════════════════════════════════════ */}
      <SectionHeader
        title="Programs"
        icon="fa-star"
        subtitle="Gold Guides and Volunteers"
        tooltip="Tracks activity from organized member programs. Gold Guides are trained peer advisors who answer questions in the Q&A forum. Volunteer tracking is not yet implemented."
      />

      <SubLabel tooltip="Gold Guides are members with the Gold Guide role who respond to questions in Q&A forum threads. Contributions are tracked per-message in gold_guide_contributions.">
        Gold Guides
      </SubLabel>
      <div className="grid grid-cols-2 sm:grid-cols-3 gap-3 mb-3">
        <StatCard
          label="Active Guides"
          value={gg.active_guides}
          icon="fa-user-tie"
          color="#f59e0b"
          tooltip="Distinct Gold Guide members who sent at least one message in a Q&A thread during the period. A guide counts as 'active' if they contributed at least once."
        />
        <StatCard
          label="Questions answered in Ask ASU Staff"
          value={gg.qna_sessions}
          icon="fa-comments"
          color="#8c1d40"
          tooltip="Total Q&A forum threads created during the period. Each thread is one question from a student. Tracked in qna_posts."
        />
        <StatCard
          label="Messages Sent"
          value={gg.messages_sent}
          icon="fa-comment"
          color="#3b82f6"
          tooltip="Total messages sent by Gold Guide members inside Q&A threads during the period. Tracked per-message in gold_guide_contributions."
        />
      </div>
      {gg.contribution_distribution?.length > 0 && (
        <Card className="mb-5">
          <CardContent className="p-0">
            <div className="px-4 py-2.5 border-b flex items-center gap-1">
              <button
                type="button"
                onClick={() => setGoldGuideListCollapsed((c) => !c)}
                className="flex items-center gap-1 cursor-pointer bg-transparent border-0 p-0 text-inherit"
              >
                <i
                  className={`fas fa-chevron-down fa-sm text-muted-foreground transition-transform ${
                    goldGuideListCollapsed ? "-rotate-90" : ""
                  }`}
                />
                <span className="text-xs font-bold uppercase tracking-wide text-muted-foreground">
                  Guide Contribution Distribution
                </span>
              </button>
              <Tooltip text="Top 15 Gold Guides ranked by total messages sent in Q&A threads during the period. Shows which guides are most active." />
              <Button
                size="sm"
                variant="outline"
                asChild
                className="ml-auto h-7 px-2 text-xs"
              >
                <a
                  href={`/api/admin/analytics/gold-guides/export/csv?${new URLSearchParams({
                    ...(applied.from ? { from_date: applied.from } : {}),
                    ...(applied.to ? { to_date: applied.to } : {}),
                  })}`}
                  download={`gold_guide_contributions_${applied.from || "start"}_to_${applied.to || "end"}.csv`}
                >
                  <i className="fas fa-download mr-1" />
                  Download CSV
                </a>
              </Button>
            </div>
            {!goldGuideListCollapsed && (
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-xs text-muted-foreground uppercase tracking-wide border-b">
                    <th className="text-left px-4 py-2 font-semibold">Guide</th>
                    <th className="text-right px-4 py-2 font-semibold w-28">Messages</th>
                  </tr>
                </thead>
                <tbody>
                  {gg.contribution_distribution.map((g) => (
                    <tr key={g.discord_id} className="border-b last:border-0 hover:bg-muted/30">
                      <td className="px-4 py-2 font-medium">{g.username}</td>
                      <td className="px-4 py-2 text-right tabular-nums font-semibold">
                        {g.messages.toLocaleString()}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </CardContent>
        </Card>
      )}

      <SubLabel tooltip="Volunteers are members with the Volunteer role who send messages anywhere in the server (not restricted to a specific forum, unlike Gold Guides). Contributions are tracked per-message in volunteer_contributions.">
        Volunteers
      </SubLabel>
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-3">
        <StatCard
          label="Active Volunteers"
          value={vol.active_volunteers}
          icon="fa-hands-helping"
          color="#10b981"
          tooltip="Distinct Volunteer-role members who sent at least one message anywhere in the server during the period."
        />
        <StatCard
          label="Messages Sent"
          value={vol.messages_sent}
          icon="fa-comment"
          tooltip="Total messages sent by members with the Volunteer role during the period, across all channels. Tracked per-message in volunteer_contributions."
        />
        <StatCard
          label="Avg Messages / Volunteer"
          value={vol.avg_messages_per_volunteer}
          icon="fa-chart-bar"
          color="#3b82f6"
          tooltip="Average messages per active volunteer during the period (messages sent ÷ active volunteers)."
        />
        <StatCard
          label="Voice Hours"
          value={vol.voice_hours != null ? `${vol.voice_hours}h` : null}
          icon="fa-microphone"
          color="#f59e0b"
          tooltip="Total voice time logged by members currently holding the Volunteer role, clipped to the selected period. Reflects current role membership, not historical — a member who left the role won't be counted even if they volunteered during the period."
        />
      </div>
      {vol.contribution_distribution?.length > 0 && (
        <Card className="mb-6">
          <CardContent className="p-0">
            <div className="px-4 py-2.5 border-b flex items-center gap-1">
              <button
                type="button"
                onClick={() => setVolunteerListCollapsed((c) => !c)}
                className="flex items-center gap-1 cursor-pointer bg-transparent border-0 p-0 text-inherit"
              >
                <i
                  className={`fas fa-chevron-down fa-sm text-muted-foreground transition-transform ${
                    volunteerListCollapsed ? "-rotate-90" : ""
                  }`}
                />
                <span className="text-xs font-bold uppercase tracking-wide text-muted-foreground">
                  Volunteer Contribution Distribution
                </span>
              </button>
              <Tooltip text="Top 15 Volunteers ranked by total messages sent anywhere in the server during the period." />
            </div>
            {!volunteerListCollapsed && (
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-xs text-muted-foreground uppercase tracking-wide border-b">
                    <th className="text-left px-4 py-2 font-semibold">Volunteer</th>
                    <th className="text-right px-4 py-2 font-semibold w-28">Messages</th>
                  </tr>
                </thead>
                <tbody>
                  {vol.contribution_distribution.map((v) => (
                    <tr key={v.discord_id} className="border-b last:border-0 hover:bg-muted/30">
                      <td className="px-4 py-2 font-medium">{v.username}</td>
                      <td className="px-4 py-2 text-right tabular-nums font-semibold">
                        {v.messages.toLocaleString()}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </CardContent>
        </Card>
      )}

      {/* ════════════════════════════════════════════════════════════════════════
          Forums
      ════════════════════════════════════════════════════════════════════════ */}
      <SectionHeader
        title="Forums"
        icon="fa-comments"
        subtitle="Ask ASU Staff · Connect by Major · Roommate Finder"
        tooltip="Tracks activity across Discord forum channels. Ask ASU Staff is the AI-assisted Q&A channel. Connect by Major and Roommate Finder are peer connection forums. All forum threads are tracked in forum_posts."
      />

      <SubLabel tooltip="Ask ASU Staff is a forum where students ask questions. The bot attempts to answer via AI; unresolved questions are flagged for staff. Tracked in qna_posts.">
        Ask ASU Staff
      </SubLabel>
      <div className="grid grid-cols-2 sm:grid-cols-3 xl:grid-cols-5 gap-3 mb-3">
        <StatCard
          label="Questions Answered"
          value={askAsu.total_questions_answered}
          icon="fa-check-circle"
          color="#10b981"
          tooltip="Questions resolved by either the AI bot (status: satisfied) or a staff member (status: needs_help). Sum of bot_answered + staff_answered."
        />
        <StatCard
          label="Posts Created"
          value={askAsu.posts_created}
          icon="fa-edit"
          tooltip="Total Q&A threads opened during the period, regardless of resolution status. Each thread corresponds to one student question."
        />
        <StatCard
          label="Total Messages"
          value={askAsu.total_messages}
          icon="fa-comments"
          color="#8c1d40"
          tooltip="Total messages sent within Ask ASU Staff threads during the period (student questions, bot replies, and staff replies combined), regardless of when the thread itself was created."
        />
        <StatCard
          label="Bot Answered"
          value={askAsu.bot_answered}
          icon="fa-robot"
          color="#3b82f6"
          tooltip="Threads where the AI assistant's answer was marked as satisfactory by the student (status: satisfied)."
        />
        <StatCard
          label="Staff Answered"
          value={askAsu.staff_answered}
          icon="fa-user-tie"
          color="#f59e0b"
          tooltip="Threads escalated to staff because the bot could not resolve them (status: needs_help). Lower is better if bot resolution rate is high."
        />
      </div>
      {askAsu.by_tag?.length > 0 && (
        <Card className="mb-5">
          <CardContent className="p-0">
            <div className="px-4 py-2.5 border-b flex items-center gap-1">
              <span className="text-xs font-bold uppercase tracking-wide text-muted-foreground">
                Posts by Tag
              </span>
              <Tooltip text="Questions grouped by the tag selected when the thread was opened. Reveals which topic areas generate the most student questions." />
            </div>
            <table className="w-full text-sm">
              <thead>
                <tr className="text-xs text-muted-foreground uppercase tracking-wide border-b">
                  <th className="text-left px-4 py-2 font-semibold">Tag</th>
                  <th className="text-right px-4 py-2 font-semibold w-24">Posts</th>
                </tr>
              </thead>
              <tbody>
                {askAsu.by_tag.map((row) => (
                  <tr key={row.tag} className="border-b last:border-0 hover:bg-muted/30">
                    <td className="px-4 py-2">{row.tag}</td>
                    <td className="px-4 py-2 text-right tabular-nums font-semibold">
                      {row.count}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </CardContent>
        </Card>
      )}

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-5 mb-6">
        <div>
          <SubLabel tooltip="Forum channel for students to connect with others in the same major. Each post is a thread where students introduce themselves or seek connections.">
            Connect by Major
          </SubLabel>
          <div className="grid grid-cols-2 gap-3">
            <StatCard
              label="Posts Created"
              value={forums.connect_by_major?.posts_created}
              icon="fa-edit"
              tooltip="Threads started in channels whose name contains 'major'. Tracked in forum_posts by parent channel name."
            />
            <StatCard
              label="Messages Sent"
              value={forums.connect_by_major?.messages_sent}
              icon="fa-comment"
              color="#3b82f6"
              tooltip="Total replies within Connect by Major threads. Not currently tracked — would require message-level forum tracking."
            />
          </div>
          {forums.connect_by_major?.activity_by_major?.length > 0 && (
            <Card className="mt-3">
              <CardContent className="p-0">
                <div className="px-3 py-2 border-b flex items-center gap-1">
                  <span className="text-[11px] font-bold uppercase tracking-wide text-muted-foreground">
                    Forums by College
                  </span>
                  <Tooltip text="Number of Connect by Major posts during the period, bucketed by the author's college role. Authors with no matching college role are grouped as 'Unknown'." />
                </div>
                <table className="w-full text-sm">
                  <tbody>
                    {forums.connect_by_major.activity_by_major.map((row) => (
                      <tr key={row.college} className="border-b last:border-0 hover:bg-muted/30">
                        <td className="px-3 py-1.5">{row.college}</td>
                        <td className="px-3 py-1.5 text-right tabular-nums font-semibold w-16">
                          {row.count.toLocaleString()}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </CardContent>
            </Card>
          )}
          {forums.connect_by_major?.top_threads?.length > 0 && (
            <Card className="mt-3">
              <CardContent className="p-0">
                <div className="px-3 py-2 border-b flex items-center gap-1">
                  <span className="text-[11px] font-bold uppercase tracking-wide text-muted-foreground">
                    Top 5 Threads
                  </span>
                  <Tooltip text="The 5 Connect by Major threads with the most messages during the selected period." />
                </div>
                <table className="w-full text-sm">
                  <tbody>
                    {forums.connect_by_major.top_threads.map((t) => (
                      <tr key={t.channel_id} className="border-b last:border-0 hover:bg-muted/30">
                        <td className="px-3 py-1.5 truncate max-w-[10rem]" title={t.channel_name}>
                          {t.channel_name}
                        </td>
                        <td className="px-3 py-1.5 text-right tabular-nums font-semibold w-16">
                          {t.messages.toLocaleString()}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </CardContent>
            </Card>
          )}
        </div>
        <div>
          <SubLabel tooltip="Forum channel where students looking for roommates post listings. Posts are tracked in forum_posts by parent channel name.">
            Roommate Finder
          </SubLabel>
          <StatCard
            label="Posts by Campus"
            value={forums.roommate_finder?.posts_by_campus}
            icon="fa-home"
            color="#10b981"
            tooltip="Threads started in channels whose name contains 'roommate'. A proxy for demand for roommate matching at each campus."
          />
        </div>
      </div>

      {/* ════════════════════════════════════════════════════════════════════════
          Acquisition
      ════════════════════════════════════════════════════════════════════════ */}
      <SectionHeader
        title="Acquisition"
        icon="fa-search"
        subtitle="Traffic source — requires Google Analytics integration"
        tooltip="Shows how people find and arrive at the verification page. All metrics require Google Analytics (or similar) to be integrated with the web app. Currently not connected."
      />
      <div className="grid grid-cols-2 sm:grid-cols-3 xl:grid-cols-6 gap-3 mb-6">
        <StatCard
          label="Source / Medium"
          value={null}
          icon="fa-link"
          tooltip="The traffic source and medium (e.g., email / campaign, organic / google). Requires Google Analytics UTM tracking."
        />
        <StatCard
          label="Users"
          value={null}
          icon="fa-users"
          color="#3b82f6"
          tooltip="Unique visitors to the verification page from this source. Requires Google Analytics."
        />
        <StatCard
          label="Sessions"
          value={null}
          icon="fa-layer-group"
          color="#10b981"
          tooltip="Total sessions initiated from this source. One user can have multiple sessions. Requires Google Analytics."
        />
        <StatCard
          label="Pageviews"
          value={null}
          icon="fa-eye"
          color="#f59e0b"
          tooltip="Total page views from this source, including repeat views within a session. Requires Google Analytics."
        />
        <StatCard
          label="Bounce Rate"
          value={null}
          icon="fa-percentage"
          color="#ef4444"
          tooltip="% of sessions where the user left without interacting (single-page visit). Lower bounce rate = more engaged visitors. Requires Google Analytics."
        />
        <StatCard
          label="Session Duration"
          value={null}
          icon="fa-clock"
          color="#8b5cf6"
          tooltip="Average time users spend on the verification page per session. Longer duration may indicate friction in the flow. Requires Google Analytics."
        />
      </div>

      {/* ════════════════════════════════════════════════════════════════════════
          Suggested Additions
      ════════════════════════════════════════════════════════════════════════ */}
      <SectionHeader
        title="Suggested Additions"
        icon="fa-lightbulb"
        subtitle="Metrics recommended for future tracking"
        tooltip="These metrics are not currently tracked but would provide valuable insight if implemented. Each would require additional data collection, instrumentation, or external integrations."
      />
      <Card className="mb-6">
        <CardContent className="p-4">
          <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-x-8 gap-y-1.5">
            {[
              "Join to Verify Conversion Rate",
              "Time to First Message",
              "7-Day Retention",
              "30-Day Retention",
              "Messages per Active User",
              "Lurker vs Contributor Rate",
              "Replies per Thread",
              "New vs Returning Users per Channel",
              "Channel Retention",
              "Event Attendance",
              "Event Impact on Activity",
              "Event Impact on Retention",
              "Reports per 1k Users",
              "Moderation Response Time",
              "Repeat Offenders",
              "DM Connections After Join",
              "Group Formation Success Rate",
              "Retention by Source",
              "Engagement by Source",
              "Response Time to Questions",
              "Answer Rate",
              "User Satisfaction Score",
            ].map((label) => (
              <div key={label} className="flex items-center gap-2 text-sm text-muted-foreground">
                <i className="fas fa-circle text-[5px] shrink-0 opacity-40" />
                {label}
              </div>
            ))}
          </div>
        </CardContent>
      </Card>
    </>
  );
}
