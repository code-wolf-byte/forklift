import { useState, useEffect } from "react";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
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
  const [filter, setFilter] = useState("all");

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

      <div className="grid grid-cols-3 gap-4 mb-6">
        {[
          { label: "Joined",     value: joinedCount,   icon: "fa-user-plus",  color: "text-emerald-500" },
          { label: "Left",       value: leftCount,     icon: "fa-user-minus", color: "text-red-500"     },
          { label: "Interested", value: netInterested, icon: "fa-users",      color: "text-blue-500"    },
        ].map(({ label, value, icon, color }) => (
          <Card key={label} className="p-4">
            <div className={`text-2xl font-bold ${color}`}>{value}</div>
            <div className="text-xs text-muted-foreground mt-0.5">
              <i className={`fas ${icon} mr-1`} />{label}
            </div>
          </Card>
        ))}
      </div>

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

// ── Voice search view ─────────────────────────────────────────────────────────

function VoiceSearchView({ onBack, onSaved }) {
  const [channels, setChannels] = useState([]);
  const [startTime, setStartTime] = useState("");
  const [endTime, setEndTime] = useState("");
  const [channel, setChannel] = useState("");
  const [searching, setSearching] = useState(false);
  const [results, setResults] = useState(null);
  const [error, setError] = useState(null);
  const [eventName, setEventName] = useState("");
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState(null);

  useEffect(() => {
    fetch("/api/admin/events/voice-channels")
      .then((r) => r.json())
      .then(setChannels)
      .catch(() => {});
  }, []);

  function handleSearch(e) {
    e.preventDefault();
    if (!startTime || !endTime) return;
    setSearching(true);
    setResults(null);
    setError(null);
    setEventName("");
    setSaveError(null);

    fetch("/api/admin/events/voice-search", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ start_time: startTime, end_time: endTime, channel_name: channel || null }),
    })
      .then((r) => r.json())
      .then((d) => {
        if (d.error) { setError(d.error); } else { setResults(d); }
        setSearching(false);
      })
      .catch(() => { setError("Search failed."); setSearching(false); });
  }

  function handleSave(e) {
    e.preventDefault();
    if (!eventName.trim()) return;
    setSaving(true);
    setSaveError(null);

    fetch("/api/admin/events/voice-save", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name: eventName.trim(), start_time: startTime, end_time: endTime, channel_name: channel || null }),
    })
      .then((r) => r.json())
      .then((d) => {
        setSaving(false);
        if (d.error) { setSaveError(d.error); } else { onSaved(d.id); }
      })
      .catch(() => { setSaveError("Save failed."); setSaving(false); });
  }

  return (
    <>
      <div className="flex items-center gap-3 mb-6">
        <Button size="sm" variant="outline" onClick={onBack}>
          <i className="fas fa-arrow-left mr-1.5" />
          All Events
        </Button>
        <h2 className="text-2xl font-bold">Search Voice Sessions</h2>
      </div>

      <Card className="p-5 mb-6">
        <form onSubmit={handleSearch} className="flex flex-wrap gap-4 items-end">
          <div className="flex flex-col gap-1.5 min-w-[180px]">
            <Label htmlFor="vs-start">Start Time (AZ)</Label>
            <input
              id="vs-start"
              type="datetime-local"
              value={startTime}
              onChange={(e) => setStartTime(e.target.value)}
              required
              className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-sm transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
            />
          </div>
          <div className="flex flex-col gap-1.5 min-w-[180px]">
            <Label htmlFor="vs-end">End Time (AZ)</Label>
            <input
              id="vs-end"
              type="datetime-local"
              value={endTime}
              onChange={(e) => setEndTime(e.target.value)}
              required
              className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-sm transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
            />
          </div>
          <div className="flex flex-col gap-1.5 min-w-[180px]">
            <Label htmlFor="vs-channel">Voice Channel (optional)</Label>
            <select
              id="vs-channel"
              value={channel}
              onChange={(e) => setChannel(e.target.value)}
              className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
            >
              <option value="">All channels</option>
              {channels.map((c) => (
                <option key={c} value={c}>{c}</option>
              ))}
            </select>
          </div>
          <Button type="submit" disabled={searching} style={{ background: "#8c1d40" }}>
            {searching ? (
              <><span className="spinner-border spinner-border-sm mr-2" />Searching…</>
            ) : (
              <><i className="fas fa-search mr-1.5" />Search</>
            )}
          </Button>
        </form>
      </Card>

      {error && (
        <p className="text-red-600 text-sm mb-4">{error}</p>
      )}

      {results !== null && (
        <>
          <div className="flex items-center justify-between mb-3">
            <p className="text-sm text-muted-foreground">
              {results.length} unique user{results.length !== 1 ? "s" : ""} found
            </p>
          </div>

          <Card className="overflow-hidden p-0 mb-6">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="pl-4">Email</TableHead>
                  <TableHead>Discord</TableHead>
                  <TableHead>Channel</TableHead>
                  <TableHead>Joined (AZ)</TableHead>
                  <TableHead>Left (AZ)</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {results.length === 0 ? (
                  <TableRow>
                    <TableCell colSpan={5} className="pl-4 text-muted-foreground italic">
                      No users found in the specified window.
                    </TableCell>
                  </TableRow>
                ) : (
                  results.map((r) => (
                    <TableRow key={r.discord_user_id}>
                      <TableCell className="pl-4 text-muted-foreground">
                        {r.email || <span className="italic">—</span>}
                      </TableCell>
                      <TableCell className="font-medium">
                        {r.discord_username || <span className="italic text-muted-foreground">{r.discord_user_id}</span>}
                      </TableCell>
                      <TableCell className="text-sm text-muted-foreground">{r.channel_name || "—"}</TableCell>
                      <TableCell className="text-sm text-muted-foreground">{formatDateTime(r.joined_at)}</TableCell>
                      <TableCell className="text-sm text-muted-foreground">
                        {r.left_at ? formatDateTime(r.left_at) : <span className="italic">Still active</span>}
                      </TableCell>
                    </TableRow>
                  ))
                )}
              </TableBody>
            </Table>
          </Card>

          {results.length > 0 && (
            <Card className="p-5">
              <p className="text-sm font-medium mb-3">Save as event</p>
              <form onSubmit={handleSave} className="flex gap-3 items-end">
                <div className="flex flex-col gap-1.5 flex-1 max-w-sm">
                  <Label htmlFor="vs-name">Event Name</Label>
                  <Input
                    id="vs-name"
                    placeholder="e.g. Game Night – May 1"
                    value={eventName}
                    onChange={(e) => setEventName(e.target.value)}
                    required
                  />
                </div>
                <Button type="submit" disabled={saving || !eventName.trim()} style={{ background: "#8c1d40" }}>
                  {saving ? (
                    <><span className="spinner-border spinner-border-sm mr-2" />Saving…</>
                  ) : (
                    <><i className="fas fa-save mr-1.5" />Save Event</>
                  )}
                </Button>
              </form>
              {saveError && <p className="text-red-600 text-sm mt-2">{saveError}</p>}
            </Card>
          )}
        </>
      )}
    </>
  );
}

// ── Events list view ──────────────────────────────────────────────────────────

export default function Events() {
  const [events, setEvents] = useState(null);
  const [loading, setLoading] = useState(true);
  const [selectedId, setSelectedId] = useState(null);
  const [showVoiceSearch, setShowVoiceSearch] = useState(false);

  function loadEvents() {
    setLoading(true);
    fetch("/api/admin/events")
      .then((r) => r.json())
      .then((d) => { setEvents(Array.isArray(d) ? d : []); setLoading(false); })
      .catch(() => setLoading(false));
  }

  useEffect(() => { loadEvents(); }, []);

  if (selectedId !== null) {
    return <EventDetail eventId={selectedId} onBack={() => setSelectedId(null)} />;
  }

  if (showVoiceSearch) {
    return (
      <VoiceSearchView
        onBack={() => setShowVoiceSearch(false)}
        onSaved={(id) => {
          loadEvents();
          setShowVoiceSearch(false);
          setSelectedId(id);
        }}
      />
    );
  }

  return (
    <>
      <div className="flex items-center justify-between mb-1">
        <h2 className="text-2xl font-bold">Server Events</h2>
        <Button
          size="sm"
          onClick={() => setShowVoiceSearch(true)}
          style={{ background: "#8c1d40" }}
        >
          <i className="fas fa-microphone mr-1.5" />
          Search Voice Sessions
        </Button>
      </div>
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
