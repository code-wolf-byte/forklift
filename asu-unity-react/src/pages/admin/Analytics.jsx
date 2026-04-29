import { useState, useEffect } from "react";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

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

function StatCard({ label, value, icon, color = "#8c1d40", note, tooltip }) {
  const isNull = value === null || value === undefined;
  return (
    <Card className="relative overflow-hidden">
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

function SectionHeader({ title, icon, subtitle, tooltip }) {
  return (
    <div className="flex items-center gap-2.5 mb-3 mt-7 pb-2 border-b">
      {icon && (
        <div
          className="w-8 h-8 rounded-lg flex items-center justify-center shrink-0"
          style={{ background: "#8c1d4018", color: "#8c1d40" }}
        >
          <i className={`fas ${icon} fa-sm`} />
        </div>
      )}
      <div>
        <h3 className="text-base font-bold mb-0 flex items-center">
          {title}
          {tooltip && <Tooltip text={tooltip} />}
        </h3>
        {subtitle && <p className="text-xs text-muted-foreground mb-0">{subtitle}</p>}
      </div>
    </div>
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
  const [fromDate, setFromDate] = useState("");
  const [toDate, setToDate] = useState("");
  const [applied, setApplied] = useState({ from: "", to: "" });
  const [sfStatus, setSfStatus] = useState(null);
  const [sfRefreshing, setSfRefreshing] = useState(false);

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

  const handleApply = () => setApplied({ from: fromDate, to: toDate });

  const handlePreset = (preset) => {
    if (preset === "alltime") {
      setFromDate("");
      setToDate("");
      setApplied({ from: "", to: "" });
    } else if (preset === "month") {
      const f = monthStartISO(),
        t = todayISO();
      setFromDate(f);
      setToDate(t);
      setApplied({ from: f, to: t });
    } else if (preset === "today") {
      const t = todayISO();
      setFromDate(t);
      setToDate(t);
      setApplied({ from: t, to: t });
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

  const totalVerified = retention.total_verified || 0;
  const totalUnverified = (retention.verified_vs_unverified || {}).unverified || 0;
  const totalAllTime = totalVerified + totalUnverified;

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
      <p className="text-sm text-muted-foreground mb-5">
        Comprehensive server metrics across engagement, demographics, programs, and forums.
      </p>

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
          tooltip="Total messages logged across all channels during the period. Populated by the message backfill and real-time listener."
        />
        <StatCard
          label="Unique Talkers"
          value={ca.unique_talkers}
          icon="fa-user"
          color="#3b82f6"
          tooltip="Number of distinct members who sent at least one message during the period. A measure of how many people actively participated."
        />
        <StatCard
          label="Voice Hours"
          value={ca.voice_hours != null ? `${ca.voice_hours}h` : null}
          icon="fa-microphone"
          color="#10b981"
          tooltip="Total cumulative time members spent in voice channels during the period, summed across all sessions. Tracked per-session in voice_sessions."
        />
        <StatCard
          label="Unique Speakers"
          value={ca.unique_speakers}
          icon="fa-headphones"
          color="#f59e0b"
          tooltip="Number of distinct members who joined at least one voice channel during the period. Complements Voice Hours by showing breadth vs. depth."
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
          <SubLabel tooltip="Counts for members who joined or verified during the selected period.">
            Onboarding
          </SubLabel>
          <div className="grid grid-cols-2 gap-3">
            <StatCard
              label="Total Joins"
              value={onboarding.total_joins}
              icon="fa-sign-in-alt"
              tooltip="Members whose joined_at timestamp falls within the selected period. Recorded when the bot detects a new guild member."
            />
            <StatCard
              label="Verified Users"
              value={onboarding.verified_users}
              icon="fa-user-check"
              color="#10b981"
              tooltip="Members who completed both CAS (ASU login) and Discord linking during the period. Their verified_at timestamp is used for filtering."
            />
            <StatCard
              label="Unverified Users"
              value={onboarding.unverified_users}
              icon="fa-user-clock"
              color="#f59e0b"
              tooltip="Members who joined during the period but did not complete verification. Calculated as: joined in range AND verified = false."
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
          <SubLabel tooltip="How well the server keeps members who were already verified before the period started.">
            Retention
          </SubLabel>
          <div className="grid grid-cols-2 gap-3 mb-3">
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
              tooltip="% of verified members who were in the server at the start of the period and did not leave by the end. Formula: (verified_at_start − leaves) ÷ verified_at_start × 100. Requires a date range to calculate."
            />
            <StatCard
              label="Currently in Server"
              value={retention.currently_in_server}
              icon="fa-users"
              color="#3b82f6"
              tooltip="All-time count of verified members whose left_at is null — i.e., still present in the server right now."
            />
          </div>
          {totalAllTime > 0 && (
            <Card>
              <CardContent className="p-3">
                <SubLabel tooltip="All-time ratio of members who completed verification vs. those who joined but never verified.">
                  Verified vs Unverified Split
                </SubLabel>
                <ProgressBar
                  name="Verified"
                  count={totalVerified}
                  total={totalAllTime}
                  color="#10b981"
                />
                <ProgressBar
                  name="Unverified"
                  count={totalUnverified}
                  total={totalAllTime}
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
      />
      {channels.length > 0 ? (
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
                {channels.map((ch) => (
                  <tr
                    key={ch.channel_id}
                    className="border-b last:border-0 hover:bg-muted/30 transition-colors"
                  >
                    <td className="px-4 py-2 text-muted-foreground tabular-nums">{ch.rank}</td>
                    <td className="px-4 py-2 font-medium">
                      <i className="fas fa-hashtag text-xs mr-1.5 text-muted-foreground" />
                      {ch.channel_name}
                    </td>
                    <td className="px-4 py-2 text-right tabular-nums font-semibold">
                      {ch.messages.toLocaleString()}
                    </td>
                    <td className="px-4 py-2 text-right tabular-nums">
                      {ch.voice_seconds != null
                        ? `${(ch.voice_seconds / 3600).toFixed(1)}h`
                        : <NotTracked />}
                    </td>
                  </tr>
                ))}
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
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-6">
        <StatCard
          label="Monthly Visitors"
          value={null}
          icon="fa-user-friends"
          tooltip="Unique members who viewed any channel in the past 30 days. Requires Discord Insights — not accessible via bot API."
        />
        <StatCard
          label="Monthly Readers / Channel"
          value={null}
          icon="fa-book-open"
          color="#3b82f6"
          tooltip="Average number of unique readers per channel per month. Requires Discord Insights."
        />
        <StatCard
          label="Weekly Readers / Channel"
          value={null}
          icon="fa-calendar-week"
          color="#10b981"
          tooltip="Average number of unique readers per channel per week. Requires Discord Insights."
        />
        <StatCard
          label="Channel Followers"
          value={null}
          icon="fa-bell"
          color="#f59e0b"
          tooltip="Members who follow individual announcement channels to receive cross-server notifications. Requires Discord Insights."
        />
      </div>

      {/* ════════════════════════════════════════════════════════════════════════
          Demographics
      ════════════════════════════════════════════════════════════════════════ */}
      <SectionHeader
        title="Demographics"
        icon="fa-chart-pie"
        subtitle="Role breakdown for verified members"
        tooltip="Shows how verified members are distributed across academic level, residency, campus, college, and country of origin. Roles are assigned during Salesforce sync at verification. Date filter applies to verified_at."
      />
      <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-4 mb-4">
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
      </Card>

      {/* ════════════════════════════════════════════════════════════════════════
          Moderation
      ════════════════════════════════════════════════════════════════════════ */}
      <SectionHeader
        title="Moderation"
        icon="fa-shield-alt"
        subtitle="Bans, unbans, and safety incidents"
        tooltip="Tracks moderation actions taken in the server. Bans and unbans are recorded in the moderation_events table by the bot in real time and backfilled from the Discord audit log on startup."
      />
      <div className="grid grid-cols-2 sm:grid-cols-3 xl:grid-cols-5 gap-3 mb-6">
        <StatCard
          label="Support Tickets"
          value={moderation.support_tickets}
          icon="fa-ticket-alt"
          tooltip="Formal support tickets submitted via a moderation ticketing bot. Not currently tracked — requires integration with a ticket system."
        />
        <StatCard
          label="Banned (all-time)"
          value={moderation.banned_users}
          icon="fa-ban"
          color="#ef4444"
          tooltip="Total number of members currently flagged as banned in the database (users.banned = true). Not filtered by date — reflects current state."
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
          label="Inappropriate Speech"
          value={moderation.inappropriate_speech_incidents}
          icon="fa-exclamation-triangle"
          color="#f59e0b"
          tooltip="Messages flagged for inappropriate language by an automod or manual report. Not currently tracked."
        />
        <StatCard
          label="Harassment Incidents"
          value={moderation.harassment_incidents}
          icon="fa-user-slash"
          color="#f59e0b"
          tooltip="Reported harassment cases. Not currently tracked — would require a ticketing or report system."
        />
        <StatCard
          label="Spam / Phishing"
          value={moderation.spam_phishing_attempts}
          icon="fa-fish"
          color="#6b7280"
          tooltip="Messages flagged as spam or phishing by automod. Not currently tracked."
        />
      </div>

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
          label="Q&A Sessions"
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
              <span className="text-xs font-bold uppercase tracking-wide text-muted-foreground">
                Guide Contribution Distribution
              </span>
              <Tooltip text="Top 15 Gold Guides ranked by total messages sent in Q&A threads during the period. Shows which guides are most active." />
            </div>
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
          </CardContent>
        </Card>
      )}

      <SubLabel tooltip="Volunteer program tracking is planned but not yet implemented. These metrics will reflect a separate volunteer role cohort once configured.">
        Volunteers
      </SubLabel>
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-6">
        <StatCard
          label="Active Volunteers"
          value={vol.active_volunteers}
          icon="fa-hands-helping"
          color="#10b981"
          tooltip="Distinct volunteers who sent at least one message during the period. Not currently tracked."
        />
        <StatCard
          label="Messages Sent"
          value={vol.messages_sent}
          icon="fa-comment"
          tooltip="Total messages sent by members with the Volunteer role. Not currently tracked."
        />
        <StatCard
          label="Avg Messages / Volunteer"
          value={vol.avg_messages_per_volunteer}
          icon="fa-chart-bar"
          color="#3b82f6"
          tooltip="Average messages per active volunteer. Not currently tracked."
        />
        <StatCard
          label="Voice Hours"
          value={vol.voice_hours}
          icon="fa-microphone"
          color="#f59e0b"
          tooltip="Total voice time logged by volunteers. Not currently tracked."
        />
      </div>

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
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-3">
        <StatCard
          label="Questions Answered"
          value={askAsu.total_questions_answered}
          icon="fa-check-circle"
          color="#10b981"
          tooltip="Questions resolved by either the AI bot (status: satisfied) or a staff member (status: needs_help). Sum of bot_answered + staff_answered."
        />
        <StatCard
          label="Total Messages"
          value={askAsu.total_messages}
          icon="fa-comments"
          tooltip="Total Q&A threads opened during the period, regardless of resolution status. Each thread corresponds to one student question."
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
          <p className="text-xs text-muted-foreground mt-2">
            Activity by Major: <NotTracked />
          </p>
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
