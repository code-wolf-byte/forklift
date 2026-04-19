import { useState, useEffect } from "react";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  Table,
  TableHeader,
  TableBody,
  TableRow,
  TableHead,
  TableCell,
} from "@/components/ui/table";

const STATUS_STYLES = {
  scheduled: { label: "Scheduled", className: "bg-blue-600 text-white" },
  active:    { label: "Active",    className: "bg-emerald-600 text-white" },
  completed: { label: "Completed", className: "bg-gray-500 text-white" },
  canceled:  { label: "Canceled",  className: "bg-red-700 text-white" },
};

const ENTITY_LABELS = {
  voice:          "Voice",
  stage_instance: "Stage",
};

function formatDateTime(isoStr) {
  if (!isoStr) return "—";
  return new Date(
    isoStr.endsWith("Z") || isoStr.includes("+") ? isoStr : isoStr + "Z"
  ).toLocaleString("en-US", {
    timeZone: "America/Phoenix",
    month: "short",
    day: "numeric",
    year: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

function StatusBadge({ status }) {
  const s = STATUS_STYLES[status] ?? { label: status, className: "bg-gray-400 text-white" };
  return <Badge className={s.className}>{s.label}</Badge>;
}

// ── Event detail view ─────────────────────────────────────────────────────────

function EventDetail({ eventId, onBack }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState("all"); // "all" | "joined" | "left"

  useEffect(() => {
    setLoading(true);
    fetch(`/api/admin/events/${eventId}`)
      .then((r) => r.json())
      .then((d) => { setData(d); setLoading(false); })
      .catch(() => setLoading(false));
  }, [eventId]);

  if (loading) {
    return (
      <div className="flex justify-center py-20">
        <div className="spinner-border" role="status" style={{ color: "#8c1d40" }}>
          <span className="visually-hidden">Loading…</span>
        </div>
      </div>
    );
  }

  if (!data || data.error) {
    return <p className="text-muted-foreground">Event not found.</p>;
  }

  const filtered = filter === "all"
    ? data.participants
    : data.participants.filter((p) => p.action === filter);

  const joinedCount = data.participants.filter((p) => p.action === "joined").length;
  const leftCount   = data.participants.filter((p) => p.action === "left").length;

  // Unique users currently interested: joined but not left after their last join
  const netInterested = (() => {
    const lastAction = {};
    for (const p of data.participants) {
      lastAction[p.discord_user_id] = p.action;
    }
    return Object.values(lastAction).filter((a) => a === "joined").length;
  })();

  return (
    <>
      <div className="flex items-center gap-3 mb-4">
        <Button size="sm" variant="outline" onClick={onBack}>
          <i className="fas fa-arrow-left mr-1.5" />
          All Events
        </Button>
        <StatusBadge status={data.status} />
        {data.entity_type && (
          <Badge variant="outline">{ENTITY_LABELS[data.entity_type] ?? data.entity_type}</Badge>
        )}
      </div>

      <h2 className="text-2xl font-bold mb-1">{data.name}</h2>
      {data.description && (
        <p className="text-sm text-muted-foreground mb-3 max-w-xl">{data.description}</p>
      )}

      <div className="flex flex-wrap gap-6 mb-6 text-sm text-muted-foreground">
        <span><i className="fas fa-calendar-alt mr-1.5" />Start: {formatDateTime(data.start_time)}</span>
        {data.end_time && (
          <span><i className="fas fa-calendar-check mr-1.5" />End: {formatDateTime(data.end_time)}</span>
        )}
      </div>

      {/* Stat cards */}
      <div className="grid grid-cols-3 gap-4 mb-6">
        {[
          { label: "Joined",     value: joinedCount,    icon: "fa-user-plus",  color: "text-emerald-500" },
          { label: "Left",       value: leftCount,      icon: "fa-user-minus", color: "text-red-500"     },
          { label: "Interested", value: netInterested,  icon: "fa-users",      color: "text-blue-500"    },
        ].map(({ label, value, icon, color }) => (
          <Card key={label} className="p-4">
            <div className={`text-2xl font-bold ${color}`}>{value}</div>
            <div className="text-xs text-muted-foreground mt-0.5">
              <i className={`fas ${icon} mr-1`} />{label}
            </div>
          </Card>
        ))}
      </div>

      {/* Filter tabs */}
      <div className="flex gap-2 mb-3">
        {["all", "joined", "left"].map((f) => (
          <Button
            key={f}
            size="sm"
            variant={filter === f ? "default" : "outline"}
            onClick={() => setFilter(f)}
            style={filter === f ? { background: "#8c1d40" } : {}}
          >
            {f === "all" ? "All" : f.charAt(0).toUpperCase() + f.slice(1)}
          </Button>
        ))}
      </div>

      <Card className="overflow-hidden p-0">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="pl-4">Action</TableHead>
              <TableHead>Time (AZ)</TableHead>
              <TableHead>Discord</TableHead>
              <TableHead>ASURITE</TableHead>
              <TableHead>Email</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {filtered.length === 0 ? (
              <TableRow>
                <TableCell colSpan={5} className="pl-4 text-muted-foreground italic">
                  No participants.
                </TableCell>
              </TableRow>
            ) : (
              filtered.map((p) => (
                <TableRow key={p.id}>
                  <TableCell className="pl-4">
                    {p.action === "joined" ? (
                      <Badge className="bg-emerald-600 text-white text-xs">Joined</Badge>
                    ) : (
                      <Badge className="bg-red-700 text-white text-xs">Left</Badge>
                    )}
                  </TableCell>
                  <TableCell className="text-sm text-muted-foreground">
                    {formatDateTime(p.timestamp)}
                  </TableCell>
                  <TableCell className="font-medium">
                    {p.discord_username || <span className="italic text-muted-foreground">{p.discord_user_id}</span>}
                  </TableCell>
                  <TableCell className="text-muted-foreground">{p.asurite_id || "—"}</TableCell>
                  <TableCell className="text-muted-foreground">{p.email || "—"}</TableCell>
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
      </Card>
    </>
  );
}

// ── Events list view ──────────────────────────────────────────────────────────

export default function Events() {
  const [events, setEvents] = useState(null);
  const [loading, setLoading] = useState(true);
  const [selectedId, setSelectedId] = useState(null);

  useEffect(() => {
    fetch("/api/admin/events")
      .then((r) => r.json())
      .then((d) => { setEvents(Array.isArray(d) ? d : []); setLoading(false); })
      .catch(() => setLoading(false));
  }, []);

  if (selectedId !== null) {
    return <EventDetail eventId={selectedId} onBack={() => setSelectedId(null)} />;
  }

  return (
    <>
      <h2 className="text-2xl font-bold mb-1">Server Events</h2>
      <p className="text-sm text-muted-foreground mb-6">
        {events ? `${events.length} event${events.length !== 1 ? "s" : ""} tracked` : "Loading…"}
      </p>

      {loading ? (
        <div className="flex justify-center py-20">
          <div className="spinner-border" role="status" style={{ color: "#8c1d40" }}>
            <span className="visually-hidden">Loading…</span>
          </div>
        </div>
      ) : events && events.length === 0 ? (
        <Card className="p-6 text-center text-muted-foreground">
          No server events tracked yet. Events will appear here once the bot observes a scheduled
          in-server event.
        </Card>
      ) : (
        <Card className="overflow-hidden p-0">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="pl-4">Event</TableHead>
                <TableHead>Type</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Start (AZ)</TableHead>
                <TableHead>End (AZ)</TableHead>
                <TableHead className="text-right">Joined</TableHead>
                <TableHead className="text-right pr-4">Left</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {events.map((e) => (
                <TableRow
                  key={e.id}
                  className="cursor-pointer hover:bg-muted/50"
                  onClick={() => setSelectedId(e.id)}
                >
                  <TableCell className="pl-4 font-semibold max-w-[200px] truncate">
                    {e.name}
                  </TableCell>
                  <TableCell>
                    <Badge variant="outline" className="text-xs">
                      {ENTITY_LABELS[e.entity_type] ?? e.entity_type}
                    </Badge>
                  </TableCell>
                  <TableCell><StatusBadge status={e.status} /></TableCell>
                  <TableCell className="text-sm text-muted-foreground">
                    {formatDateTime(e.start_time)}
                  </TableCell>
                  <TableCell className="text-sm text-muted-foreground">
                    {formatDateTime(e.end_time)}
                  </TableCell>
                  <TableCell className="text-right text-emerald-600 font-medium">
                    {e.joined_count}
                  </TableCell>
                  <TableCell className="text-right pr-4 text-red-600 font-medium">
                    {e.left_count}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </Card>
      )}
    </>
  );
}
