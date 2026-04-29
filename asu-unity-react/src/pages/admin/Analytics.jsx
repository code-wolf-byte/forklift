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

function StatCard({ label, value, icon, color = "#8c1d40", note }) {
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
        <div className="text-xs text-muted-foreground">{label}</div>
        {note && <div className="text-[11px] text-muted-foreground/60 mt-0.5">{note}</div>}
      </CardContent>
    </Card>
  );
}

function SectionHeader({ title, icon, subtitle }) {
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
        <h3 className="text-base font-bold mb-0">{title}</h3>
        {subtitle && <p className="text-xs text-muted-foreground mb-0">{subtitle}</p>}
      </div>
    </div>
  );
}

function SubLabel({ children }) {
  return (
    <div className="text-[11px] font-bold uppercase tracking-[0.06em] text-muted-foreground mb-2">
      {children}
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
      <SectionHeader title="Core Activity" icon="fa-bolt" subtitle="Engagement" />
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-6">
        <StatCard label="Messages Sent" value={ca.messages_sent} icon="fa-comment" />
        <StatCard
          label="Unique Talkers"
          value={ca.unique_talkers}
          icon="fa-user"
          color="#3b82f6"
        />
        <StatCard
          label="Voice Hours"
          value={ca.voice_hours != null ? `${ca.voice_hours}h` : null}
          icon="fa-microphone"
          color="#10b981"
        />
        <StatCard
          label="Unique Speakers"
          value={ca.unique_speakers}
          icon="fa-headphones"
          color="#f59e0b"
        />
      </div>

      {/* ════════════════════════════════════════════════════════════════════════
          Growth & Funnel
      ════════════════════════════════════════════════════════════════════════ */}
      <SectionHeader title="Growth & Funnel" icon="fa-filter" subtitle="Onboarding and retention" />
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-5 mb-6">
        {/* Onboarding */}
        <div>
          <SubLabel>Onboarding</SubLabel>
          <div className="grid grid-cols-2 gap-3">
            <StatCard label="Total Joins" value={onboarding.total_joins} icon="fa-sign-in-alt" />
            <StatCard
              label="Verified Users"
              value={onboarding.verified_users}
              icon="fa-user-check"
              color="#10b981"
            />
            <StatCard
              label="Unverified Users"
              value={onboarding.unverified_users}
              icon="fa-user-clock"
              color="#f59e0b"
            />
            <StatCard
              label="Venue Users"
              value={onboarding.venue_users}
              icon="fa-map-marker-alt"
              color="#6b7280"
            />
          </div>
        </div>

        {/* Retention */}
        <div>
          <SubLabel>Retention</SubLabel>
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
            />
            <StatCard
              label="Currently in Server"
              value={retention.currently_in_server}
              icon="fa-users"
              color="#3b82f6"
            />
          </div>
          {totalAllTime > 0 && (
            <Card>
              <CardContent className="p-3">
                <SubLabel>Verified vs Unverified Split</SubLabel>
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
      <SectionHeader title="Channel Engagement" icon="fa-hashtag" subtitle="Channels" />
      {channels.length > 0 ? (
        <Card className="mb-6">
          <CardContent className="p-0">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-xs text-muted-foreground uppercase tracking-wide border-b">
                  <th className="text-left px-4 py-2.5 font-semibold w-10">#</th>
                  <th className="text-left px-4 py-2.5 font-semibold">Channel Name</th>
                  <th className="text-right px-4 py-2.5 font-semibold w-32">Messages</th>
                  <th className="text-right px-4 py-2.5 font-semibold w-32">Voice Activity</th>
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
        subtitle="Passive Engagement — requires Discord Insights access"
      />
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-6">
        <StatCard label="Monthly Visitors" value={null} icon="fa-user-friends" />
        <StatCard
          label="Monthly Readers / Channel"
          value={null}
          icon="fa-book-open"
          color="#3b82f6"
        />
        <StatCard
          label="Weekly Readers / Channel"
          value={null}
          icon="fa-calendar-week"
          color="#10b981"
        />
        <StatCard label="Channel Followers" value={null} icon="fa-bell" color="#f59e0b" />
      </div>

      {/* ════════════════════════════════════════════════════════════════════════
          Demographics
      ════════════════════════════════════════════════════════════════════════ */}
      <SectionHeader
        title="Demographics"
        icon="fa-chart-pie"
        subtitle="Role breakdown for verified members (filtered by verified_at)"
      />
      <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-4 mb-4">
        {/* Student Role */}
        <Card>
          <CardContent className="p-4">
            <SubLabel>
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
            <SubLabel>
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
            <SubLabel>
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
            <SubLabel>
              <i className="fas fa-globe mr-1.5" />
              International
            </SubLabel>
            <p className="text-sm text-muted-foreground mb-0">
              Country of Origin: <NotTracked />
            </p>
            <p className="text-xs text-muted-foreground/70 mt-1">
              Requires Salesforce API integration.
            </p>
          </CardContent>
        </Card>
      </div>

      {/* College */}
      <SubLabel>College</SubLabel>
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
      <SectionHeader title="Moderation" icon="fa-shield-alt" subtitle="Safety" />
      <div className="grid grid-cols-2 sm:grid-cols-3 xl:grid-cols-5 gap-3 mb-6">
        <StatCard
          label="Support Tickets"
          value={moderation.support_tickets}
          icon="fa-ticket-alt"
        />
        <StatCard
          label="Banned (all-time)"
          value={moderation.banned_users}
          icon="fa-ban"
          color="#ef4444"
        />
        <StatCard
          label="Bans (period)"
          value={moderation.period_bans ?? 0}
          icon="fa-gavel"
          color="#ef4444"
          note="From moderation_events"
        />
        <StatCard
          label="Unbans (period)"
          value={moderation.period_unbans ?? 0}
          icon="fa-user-check"
          color="#10b981"
          note="From moderation_events"
        />
        <StatCard
          label="Inappropriate Speech"
          value={moderation.inappropriate_speech_incidents}
          icon="fa-exclamation-triangle"
          color="#f59e0b"
        />
        <StatCard
          label="Harassment Incidents"
          value={moderation.harassment_incidents}
          icon="fa-user-slash"
          color="#f59e0b"
        />
        <StatCard
          label="Spam / Phishing"
          value={moderation.spam_phishing_attempts}
          icon="fa-fish"
          color="#6b7280"
        />
      </div>

      {/* ════════════════════════════════════════════════════════════════════════
          Programs
      ════════════════════════════════════════════════════════════════════════ */}
      <SectionHeader title="Programs" icon="fa-star" subtitle="Gold Guides and Volunteers" />

      <SubLabel>Gold Guides</SubLabel>
      <div className="grid grid-cols-2 sm:grid-cols-3 gap-3 mb-3">
        <StatCard
          label="Active Guides"
          value={gg.active_guides}
          icon="fa-user-tie"
          color="#f59e0b"
        />
        <StatCard
          label="Q&A Sessions"
          value={gg.qna_sessions}
          icon="fa-comments"
          color="#8c1d40"
        />
        <StatCard
          label="Messages Sent"
          value={gg.messages_sent}
          icon="fa-comment"
          color="#3b82f6"
        />
      </div>
      {gg.contribution_distribution?.length > 0 && (
        <Card className="mb-5">
          <CardContent className="p-0">
            <div className="px-4 py-2.5 border-b">
              <span className="text-xs font-bold uppercase tracking-wide text-muted-foreground">
                Guide Contribution Distribution
              </span>
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

      <SubLabel>Volunteers</SubLabel>
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-6">
        <StatCard
          label="Active Volunteers"
          value={vol.active_volunteers}
          icon="fa-hands-helping"
          color="#10b981"
        />
        <StatCard label="Messages Sent" value={vol.messages_sent} icon="fa-comment" />
        <StatCard
          label="Avg Messages / Volunteer"
          value={vol.avg_messages_per_volunteer}
          icon="fa-chart-bar"
          color="#3b82f6"
        />
        <StatCard
          label="Voice Hours"
          value={vol.voice_hours}
          icon="fa-microphone"
          color="#f59e0b"
        />
      </div>

      {/* ════════════════════════════════════════════════════════════════════════
          Forums
      ════════════════════════════════════════════════════════════════════════ */}
      <SectionHeader
        title="Forums"
        icon="fa-comments"
        subtitle="Ask ASU Staff · Connect by Major · Roommate Finder"
      />

      <SubLabel>Ask ASU Staff</SubLabel>
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-3">
        <StatCard
          label="Questions Answered"
          value={askAsu.total_questions_answered}
          icon="fa-check-circle"
          color="#10b981"
        />
        <StatCard
          label="Total Messages"
          value={askAsu.total_messages}
          icon="fa-comments"
        />
        <StatCard
          label="Bot Answered"
          value={askAsu.bot_answered}
          icon="fa-robot"
          color="#3b82f6"
        />
        <StatCard
          label="Staff Answered"
          value={askAsu.staff_answered}
          icon="fa-user-tie"
          color="#f59e0b"
        />
      </div>
      {askAsu.by_tag?.length > 0 && (
        <Card className="mb-5">
          <CardContent className="p-0">
            <div className="px-4 py-2.5 border-b">
              <span className="text-xs font-bold uppercase tracking-wide text-muted-foreground">
                Posts by Tag
              </span>
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
          <SubLabel>Connect by Major</SubLabel>
          <div className="grid grid-cols-2 gap-3">
            <StatCard
              label="Posts Created"
              value={forums.connect_by_major?.posts_created}
              icon="fa-edit"
            />
            <StatCard
              label="Messages Sent"
              value={forums.connect_by_major?.messages_sent}
              icon="fa-comment"
              color="#3b82f6"
            />
          </div>
          <p className="text-xs text-muted-foreground mt-2">
            Activity by Major: <NotTracked />
          </p>
        </div>
        <div>
          <SubLabel>Roommate Finder</SubLabel>
          <StatCard
            label="Posts by Campus"
            value={forums.roommate_finder?.posts_by_campus}
            icon="fa-home"
            color="#10b981"
          />
        </div>
      </div>

      {/* ════════════════════════════════════════════════════════════════════════
          Acquisition
      ════════════════════════════════════════════════════════════════════════ */}
      <SectionHeader
        title="Acquisition"
        icon="fa-search"
        subtitle="Traffic Source — requires Google Analytics integration"
      />
      <div className="grid grid-cols-2 sm:grid-cols-3 xl:grid-cols-6 gap-3 mb-6">
        <StatCard label="Source / Medium" value={null} icon="fa-link" />
        <StatCard label="Users" value={null} icon="fa-users" color="#3b82f6" />
        <StatCard label="Sessions" value={null} icon="fa-layer-group" color="#10b981" />
        <StatCard label="Pageviews" value={null} icon="fa-eye" color="#f59e0b" />
        <StatCard label="Bounce Rate" value={null} icon="fa-percentage" color="#ef4444" />
        <StatCard label="Session Duration" value={null} icon="fa-clock" color="#8b5cf6" />
      </div>

      {/* ════════════════════════════════════════════════════════════════════════
          Suggested Additions
      ════════════════════════════════════════════════════════════════════════ */}
      <SectionHeader
        title="Suggested Additions"
        icon="fa-lightbulb"
        subtitle="Metrics recommended for future tracking"
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
