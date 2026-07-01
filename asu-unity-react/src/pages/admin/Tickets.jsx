import { useState, useEffect } from "react";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Alert, AlertDescription } from "@/components/ui/alert";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Table,
  TableHeader,
  TableBody,
  TableRow,
  TableHead,
  TableCell,
} from "@/components/ui/table";

let nextTempId = -1;

function RoleChip({ name, color, onRemove }) {
  return (
    <span
      className="inline-flex items-center gap-1 text-xs font-medium px-2 py-0.5 rounded-[5px] leading-snug max-w-[180px] whitespace-nowrap"
      style={{ background: `${color}18`, color, border: `1px solid ${color}35` }}
      title={name}
    >
      <span className="overflow-hidden text-ellipsis whitespace-nowrap max-w-[150px]">{name}</span>
      <button
        type="button"
        className="bg-transparent border-0 p-0 pl-0.5 leading-none cursor-pointer opacity-55 flex items-center shrink-0 hover:opacity-100"
        onClick={onRemove}
      >
        <i className="fas fa-times" style={{ fontSize: 8 }} />
      </button>
    </span>
  );
}

function RolePicker({ roles, selectedIds, onChange }) {
  const selected = roles.filter((r) => selectedIds.includes(r.id));
  const available = roles.filter((r) => !selectedIds.includes(r.id));

  return (
    <div className="flex items-center gap-1 flex-wrap">
      {selected.map((r) => (
        <RoleChip
          key={r.id}
          name={r.name}
          color={r.color || "#8c1d40"}
          onRemove={() => onChange(selectedIds.filter((id) => id !== r.id))}
        />
      ))}
      {available.length > 0 && (
        <Select value="" onValueChange={(val) => val && onChange([...selectedIds, val])}>
          <SelectTrigger className="h-6 text-xs px-2 w-auto min-w-[110px] border-dashed">
            <SelectValue placeholder="+ Add role" />
          </SelectTrigger>
          <SelectContent>
            {available.map((r) => (
              <SelectItem key={r.id} value={r.id} className="text-xs">
                {r.name}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      )}
    </div>
  );
}

function EmbedPreview({ settings }) {
  return (
    <div
      className="rounded-md bg-muted/40 p-3 pl-4 max-w-md"
      style={{ borderLeft: `4px solid ${settings.embed_color || "#8c1d40"}` }}
    >
      <div className="font-semibold text-sm mb-1">{settings.embed_title || "Open a Ticket"}</div>
      <div className="text-sm text-muted-foreground whitespace-pre-wrap mb-2">
        {settings.embed_description || "Select a category below to open a ticket."}
      </div>
      {settings.embed_image_url && (
        <img src={settings.embed_image_url} alt="" className="rounded max-w-full max-h-40 object-cover mb-2" />
      )}
      <div className="rounded border border-border bg-background px-2.5 py-1.5 text-xs text-muted-foreground">
        {settings.select_placeholder || "Select a ticket category…"} <i className="fas fa-chevron-down float-right" />
      </div>
      {settings.embed_footer && (
        <div className="text-[11px] text-muted-foreground mt-2">{settings.embed_footer}</div>
      )}
    </div>
  );
}

function CategoryRow({ category, roles, onChange, onRemove, onMove, isFirst, isLast }) {
  return (
    <div className="border border-border rounded-md p-3 mb-2">
      <div className="flex gap-2 items-start flex-wrap mb-2">
        <div className="flex-1 min-w-[160px]">
          <Label className="text-xs font-semibold mb-1 block">Label</Label>
          <Input
            className="h-8 text-sm"
            value={category.label}
            onChange={(e) => onChange({ ...category, label: e.target.value })}
            placeholder="e.g. Billing"
          />
        </div>
        <div className="flex-1 min-w-[160px]">
          <Label className="text-xs font-semibold mb-1 block">Description</Label>
          <Input
            className="h-8 text-sm"
            value={category.description || ""}
            onChange={(e) => onChange({ ...category, description: e.target.value })}
            placeholder="Shown under the option"
          />
        </div>
        <div className="w-20">
          <Label className="text-xs font-semibold mb-1 block">Emoji</Label>
          <Input
            className="h-8 text-sm"
            value={category.emoji || ""}
            onChange={(e) => onChange({ ...category, emoji: e.target.value })}
            placeholder="🎫"
          />
        </div>
        <div className="flex items-end gap-1 pb-0.5">
          <Button size="icon" variant="outline" className="h-8 w-8" disabled={isFirst} onClick={() => onMove(-1)}>
            <i className="fas fa-arrow-up text-xs" />
          </Button>
          <Button size="icon" variant="outline" className="h-8 w-8" disabled={isLast} onClick={() => onMove(1)}>
            <i className="fas fa-arrow-down text-xs" />
          </Button>
          <Button size="icon" variant="destructive" className="h-8 w-8" onClick={onRemove}>
            <i className="fas fa-trash text-xs" />
          </Button>
        </div>
      </div>
      <div>
        <Label className="text-xs font-semibold mb-1 block">
          Extra roles with access to this category's tickets (in addition to global staff roles)
        </Label>
        <RolePicker
          roles={roles}
          selectedIds={category.extra_role_ids || []}
          onChange={(ids) => onChange({ ...category, extra_role_ids: ids })}
        />
      </div>
    </div>
  );
}

function StatusBadge({ status }) {
  return (
    <Badge variant={status === "open" ? "default" : "secondary"} className="capitalize">
      {status}
    </Badge>
  );
}

export default function Tickets() {
  const [settings, setSettings] = useState(null);
  const [roles, setRoles] = useState([]);
  const [channels, setChannels] = useState([]);
  const [tickets, setTickets] = useState(null);
  const [saving, setSaving] = useState(false);
  const [publishing, setPublishing] = useState(false);
  const [error, setError] = useState(null);
  const [publishStatus, setPublishStatus] = useState(null);

  useEffect(() => {
    fetch("/api/admin/tickets/settings")
      .then((r) => r.json())
      .then((data) =>
        setSettings({
          ...data,
          categories: (data.categories || []).map((c) => ({ ...c })),
        })
      )
      .catch(() => {});

    fetch("/api/admin/discord-roles")
      .then((r) => r.json())
      .then(setRoles)
      .catch(() => {});

    fetch("/api/admin/discord-channels")
      .then((r) => r.json())
      .then(setChannels)
      .catch(() => {});

    refreshTickets();
  }, []);

  const refreshTickets = () =>
    fetch("/api/admin/tickets?per_page=25")
      .then((r) => r.json())
      .then(setTickets)
      .catch(() => {});

  const updateField = (field, value) => setSettings((prev) => ({ ...prev, [field]: value }));

  const updateCategory = (id, updated) =>
    setSettings((prev) => ({
      ...prev,
      categories: prev.categories.map((c) => (c.id === id ? updated : c)),
    }));

  const addCategory = () =>
    setSettings((prev) => ({
      ...prev,
      categories: [
        ...prev.categories,
        { id: nextTempId--, label: "", description: "", emoji: "", extra_role_ids: [] },
      ],
    }));

  const removeCategory = (id) =>
    setSettings((prev) => ({ ...prev, categories: prev.categories.filter((c) => c.id !== id) }));

  const moveCategory = (id, dir) =>
    setSettings((prev) => {
      const idx = prev.categories.findIndex((c) => c.id === id);
      const swapWith = idx + dir;
      if (swapWith < 0 || swapWith >= prev.categories.length) return prev;
      const next = [...prev.categories];
      [next[idx], next[swapWith]] = [next[swapWith], next[idx]];
      return { ...prev, categories: next };
    });

  const handleSave = () => {
    setSaving(true);
    setError(null);
    fetch("/api/admin/tickets/settings", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        ...settings,
        categories: settings.categories.map((c) => ({
          id: c.id > 0 ? c.id : undefined,
          label: c.label,
          description: c.description,
          emoji: c.emoji,
          extra_role_ids: c.extra_role_ids || [],
        })),
      }),
    })
      .then((r) => r.json())
      .then((updated) => {
        if (updated.error) throw new Error(updated.error);
        setSettings(updated);
      })
      .catch((e) => setError(e.message || "Save failed"))
      .finally(() => setSaving(false));
  };

  const handlePublish = () => {
    setPublishing(true);
    setPublishStatus(null);
    setError(null);
    fetch("/api/admin/tickets/settings/publish", { method: "POST" })
      .then((r) => r.json())
      .then((result) => {
        if (result.error) throw new Error(result.error);
        setPublishStatus("published");
      })
      .catch((e) => setError(e.message || "Publish failed"))
      .finally(() => setPublishing(false));
  };

  if (!settings) {
    return (
      <div className="flex justify-center py-20">
        <div className="spinner-border" role="status" style={{ color: "#8c1d40" }}>
          <span className="visually-hidden">Loading ticket settings…</span>
        </div>
      </div>
    );
  }

  return (
    <>
      <h2 className="text-2xl font-bold mb-1">Tickets</h2>
      <p className="text-sm text-muted-foreground mb-6">
        Configure the ticket panel members use to open a private ticket channel with staff.
      </p>

      <Card className="mb-4">
        <CardContent className="p-4">
          <h5 className="text-base font-semibold mb-3">Panel</h5>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">
            <div>
              <Label className="text-xs font-semibold mb-1.5 block">Panel channel</Label>
              <Select
                value={settings.panel_channel_id || ""}
                onValueChange={(val) => updateField("panel_channel_id", val)}
              >
                <SelectTrigger className="h-8 text-sm">
                  <SelectValue placeholder="— Select a channel —" />
                </SelectTrigger>
                <SelectContent>
                  {channels.map((ch) => (
                    <SelectItem key={ch.id} value={ch.id}>
                      #{ch.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <p className="text-xs text-muted-foreground mt-1">
                Where the "Open a Ticket" embed gets posted.
              </p>
            </div>

            <div>
              <Label className="text-xs font-semibold mb-1.5 block">Global staff roles</Label>
              <RolePicker
                roles={roles}
                selectedIds={settings.staff_role_ids || []}
                onChange={(ids) => updateField("staff_role_ids", ids)}
              />
              <p className="text-xs text-muted-foreground mt-1">
                These roles get access to every ticket, regardless of category.
              </p>
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">
            <div>
              <Label className="text-xs font-semibold mb-1.5 block">Embed title</Label>
              <Input
                className="h-8 text-sm"
                value={settings.embed_title || ""}
                onChange={(e) => updateField("embed_title", e.target.value)}
              />
            </div>
            <div>
              <Label className="text-xs font-semibold mb-1.5 block">Embed color</Label>
              <div className="flex items-center gap-2">
                <input
                  type="color"
                  className="h-8 w-10 rounded border border-input cursor-pointer"
                  value={settings.embed_color || "#8c1d40"}
                  onChange={(e) => updateField("embed_color", e.target.value)}
                />
                <Input
                  className="h-8 text-sm"
                  value={settings.embed_color || "#8c1d40"}
                  onChange={(e) => updateField("embed_color", e.target.value)}
                />
              </div>
            </div>
          </div>

          <div className="mb-4">
            <Label className="text-xs font-semibold mb-1.5 block">Embed description</Label>
            <textarea
              className="flex w-full rounded-md border border-input bg-background px-3 py-2 text-sm text-foreground shadow-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring min-h-[80px]"
              value={settings.embed_description || ""}
              onChange={(e) => updateField("embed_description", e.target.value)}
            />
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">
            <div>
              <Label className="text-xs font-semibold mb-1.5 block">Embed image URL</Label>
              <Input
                className="h-8 text-sm"
                value={settings.embed_image_url || ""}
                onChange={(e) => updateField("embed_image_url", e.target.value)}
              />
            </div>
            <div>
              <Label className="text-xs font-semibold mb-1.5 block">Embed footer</Label>
              <Input
                className="h-8 text-sm"
                value={settings.embed_footer || ""}
                onChange={(e) => updateField("embed_footer", e.target.value)}
              />
            </div>
          </div>

          <div className="mb-4">
            <Label className="text-xs font-semibold mb-1.5 block">Select menu placeholder</Label>
            <Input
              className="h-8 text-sm max-w-sm"
              value={settings.select_placeholder || ""}
              onChange={(e) => updateField("select_placeholder", e.target.value)}
            />
          </div>

          <Label className="text-xs font-semibold mb-1.5 block">Preview</Label>
          <EmbedPreview settings={settings} />

          {error && (
            <Alert variant="destructive" className="mt-4 py-2">
              <AlertDescription className="text-xs">{error}</AlertDescription>
            </Alert>
          )}
          {publishStatus === "published" && (
            <Alert variant="success" className="mt-4 py-2">
              <AlertDescription className="text-xs">Panel published successfully.</AlertDescription>
            </Alert>
          )}

          <div className="flex gap-2 mt-4">
            <Button size="sm" onClick={handleSave} disabled={saving}>
              {saving ? "Saving…" : "Save Settings"}
            </Button>
            <Button size="sm" variant="outline" onClick={handlePublish} disabled={publishing || !settings.panel_channel_id}>
              {publishing ? "Publishing…" : "Publish/Update Panel"}
            </Button>
          </div>
        </CardContent>
      </Card>

      <Card className="mb-4">
        <CardContent className="p-4">
          <div className="flex justify-between items-center mb-3">
            <h5 className="text-base font-semibold mb-0">Categories</h5>
            <Button size="sm" variant="outline" onClick={addCategory}>
              <i className="fas fa-plus mr-1.5" /> Add Category
            </Button>
          </div>
          {settings.categories.length === 0 && (
            <p className="text-sm text-muted-foreground">
              No categories yet — members will see "No categories configured" until you add one.
            </p>
          )}
          {settings.categories.map((cat, i) => (
            <CategoryRow
              key={cat.id}
              category={cat}
              roles={roles}
              onChange={(updated) => updateCategory(cat.id, updated)}
              onRemove={() => removeCategory(cat.id)}
              onMove={(dir) => moveCategory(cat.id, dir)}
              isFirst={i === 0}
              isLast={i === settings.categories.length - 1}
            />
          ))}
        </CardContent>
      </Card>

      <Card>
        <CardContent className="p-4">
          <h5 className="text-base font-semibold mb-3">Recent Tickets</h5>
          {!tickets ? (
            <p className="text-sm text-muted-foreground">Loading…</p>
          ) : tickets.tickets.length === 0 ? (
            <p className="text-sm text-muted-foreground">No tickets have been opened yet.</p>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Subject</TableHead>
                  <TableHead>Category</TableHead>
                  <TableHead>Opener</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Created</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {tickets.tickets.map((t) => (
                  <TableRow key={t.id}>
                    <TableCell className="max-w-[220px] truncate">{t.subject || "(no subject)"}</TableCell>
                    <TableCell>{t.category || "—"}</TableCell>
                    <TableCell>{t.opener_username || t.opener_discord_id}</TableCell>
                    <TableCell>
                      <StatusBadge status={t.status} />
                    </TableCell>
                    <TableCell>{t.created_at ? new Date(t.created_at).toLocaleString() : "—"}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>
    </>
  );
}
