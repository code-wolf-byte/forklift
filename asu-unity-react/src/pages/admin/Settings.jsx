import { useState, useEffect, useMemo } from "react";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Alert, AlertDescription } from "@/components/ui/alert";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

const NONE = "__none__";

// Role-map rows are grouped with the same headings the Member Stats page uses.
const ROLE_MAP_GROUPS = [
  { label: "Academic Level", names: ["First Year", "Transfer Student", "Graduate Student", "Upperclassmen"] },
  {
    label: "College",
    names: [
      "Barrett The Honors College",
      "College of Health Solutions",
      "Ira A. Fulton Schools of Engineering",
      "College of Liberal Arts and Sciences",
      "College of Global Futures",
      "Edson College of Nursing and Health Innovation",
      "Herberger Institute for Design and the Arts",
      "Thunderbird School of Global Management",
      "Mary Lou Fulton Teachers College",
      "New College of Interdisciplinary Arts and Sciences",
      "College of Integrative Sciences and Arts",
      "W.P. Carey School of Business",
      "Walter Cronkite School of Journalism and Mass Communication",
      "Watts College of Public Service and Community Solutions",
      "University College",
    ],
  },
  { label: "Campus", names: ["Tempe", "Downtown Phoenix", "Polytechnic", "LA Center", "West Valley", "Online"] },
  { label: "Residency", names: ["Out of State", "Arizona Resident", "International Student"] },
  { label: "Special", names: ["First Generation Student", "Commited"] },
];

function formatAZ(isoStr) {
  if (!isoStr) return null;
  try {
    return new Date(isoStr).toLocaleString("en-US", {
      timeZone: "America/Phoenix",
      month: "short",
      day: "numeric",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return isoStr;
  }
}

function OverrideBadge({ meta, onReset }) {
  if (!meta?.is_overridden) {
    return <span className="text-xs text-muted-foreground">Default</span>;
  }
  const when = formatAZ(meta.updated_at);
  return (
    <span className="text-xs flex items-center gap-2 flex-wrap">
      <span className="font-semibold" style={{ color: "#8c1d40" }}>
        Overridden{when ? ` — ${when}` : ""}
      </span>
      <button
        type="button"
        className="underline text-muted-foreground hover:text-foreground bg-transparent border-0 p-0 cursor-pointer"
        onClick={onReset}
      >
        Reset to default
      </button>
    </span>
  );
}

function RoleSelect({ value, roles, onChange, allowEmpty = true, placeholder = "— Select a role —" }) {
  return (
    <Select value={value || NONE} onValueChange={(v) => onChange(v === NONE ? "" : v)}>
      <SelectTrigger className="max-w-sm h-8 text-sm">
        <SelectValue placeholder={placeholder} />
      </SelectTrigger>
      <SelectContent>
        {allowEmpty && <SelectItem value={NONE}>— None —</SelectItem>}
        {roles.map((r) => (
          <SelectItem key={r.id} value={r.id}>
            @{r.name}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}

export default function Settings() {
  const [settings, setSettings] = useState(null);
  const [draft, setDraft] = useState({});
  const [roles, setRoles] = useState([]);
  const [channels, setChannels] = useState([]);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);
  const [saved, setSaved] = useState(false);

  const load = (data) => {
    setSettings(data);
    setDraft(Object.fromEntries(Object.entries(data).map(([k, v]) => [k, v.value])));
  };

  useEffect(() => {
    fetch("/api/admin/settings")
      .then((r) => r.json())
      .then((data) => {
        if (data.error) throw new Error(data.error);
        load(data);
      })
      .catch((e) => setError(e.message || "Failed to load settings"));

    fetch("/api/admin/discord-roles").then((r) => r.json()).then(setRoles).catch(() => {});
    fetch("/api/admin/discord-channels?include=forum")
      .then((r) => r.json())
      .then(setChannels)
      .catch(() => {});
  }, []);

  const forumChannels = useMemo(() => channels.filter((c) => c.type === 15), [channels]);
  const roleName = (id) => roles.find((r) => r.id === String(id))?.name;

  const set = (key, value) => {
    setSaved(false);
    setDraft((prev) => ({ ...prev, [key]: value }));
  };

  const submit = (payload) => {
    setSaving(true);
    setError(null);
    setSaved(false);
    return fetch("/api/admin/settings", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    })
      .then((r) => r.json())
      .then((data) => {
        if (data.error) throw new Error(data.error);
        load(data);
        setSaved(true);
      })
      .catch((e) => setError(e.message || "Save failed"))
      .finally(() => setSaving(false));
  };

  // Values are sent as-is: "" means "explicitly unset" for optional keys and is
  // rejected for required ones. Only the Reset link sends null (back to default).
  const saveKeys = (keys) => submit(Object.fromEntries(keys.map((k) => [k, draft[k]])));

  const reset = (key) => submit({ [key]: null });

  if (!settings) {
    return (
      <>
        <h2 className="text-2xl font-bold mb-1">Settings</h2>
        {error ? (
          <Alert variant="destructive" className="mt-4">
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        ) : (
          <div className="flex justify-center py-20">
            <div className="spinner-border" role="status" style={{ color: "#8c1d40" }}>
              <span className="visually-hidden">Loading settings…</span>
            </div>
          </div>
        )}
      </>
    );
  }

  const field = (key, label, help, control) => (
    <div className="mb-4" key={key}>
      <div className="flex justify-between items-baseline gap-3 flex-wrap mb-1.5">
        <Label className="text-xs font-semibold">{label}</Label>
        <OverrideBadge meta={settings[key]} onReset={() => reset(key)} />
      </div>
      {control}
      {help && <p className="text-xs text-muted-foreground mt-1">{help}</p>}
    </div>
  );

  const SaveBar = ({ keys }) => (
    <Button size="sm" disabled={saving} onClick={() => saveKeys(keys)}>
      {saving ? "Saving…" : "Save"}
    </Button>
  );

  const restricted = draft.admin_restricted_role_ids || [];

  return (
    <>
      <h2 className="text-2xl font-bold mb-1">Settings</h2>
      <p className="text-sm text-muted-foreground mb-4">
        Channels, roles and term codes the bot reads at runtime. Changes take effect
        within 30 seconds — no restart needed. A setting left at its default follows
        the value shipped in the deployment.
      </p>

      {error && (
        <Alert variant="destructive" className="mb-4">
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}
      {saved && !error && (
        <Alert className="mb-4">
          <AlertDescription>Settings saved.</AlertDescription>
        </Alert>
      )}

      {/* ── Channels ── */}
      <Card className="mb-3">
        <CardContent className="p-4">
          <h5 className="text-base font-semibold mb-3">Channels</h5>
          {field(
            "qna_forum_channel_id",
            "Q&A Forum Channel",
            "The forum the Q&A bot answers in. Existing Q&A history stays attached to the old channel.",
            <Select
              value={draft.qna_forum_channel_id || NONE}
              onValueChange={(v) => set("qna_forum_channel_id", v === NONE ? "" : v)}
            >
              <SelectTrigger className="max-w-sm h-8 text-sm">
                <SelectValue placeholder="— Select a forum channel —" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value={NONE}>— None —</SelectItem>
                {forumChannels.map((ch) => (
                  <SelectItem key={ch.id} value={ch.id}>
                    #{ch.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          )}
          <SaveBar keys={["qna_forum_channel_id"]} />
        </CardContent>
      </Card>

      {/* ── Roles ── */}
      <Card className="mb-3">
        <CardContent className="p-4">
          <h5 className="text-base font-semibold mb-1">Roles</h5>
          <p className="text-xs text-muted-foreground mb-3">
            Changing the verified role does <strong>not</strong> re-assign members who are
            already verified — they keep the role they were given.
          </p>
          {field("verified_role_id", "Verified Role", null,
            <RoleSelect value={draft.verified_role_id} roles={roles} allowEmpty={false}
              onChange={(v) => set("verified_role_id", v)} />)}
          {field("unverified_role_id", "Unverified Role", null,
            <RoleSelect value={draft.unverified_role_id} roles={roles} allowEmpty={false}
              onChange={(v) => set("unverified_role_id", v)} />)}
          {field("gold_guide_role_id", "Gold Guide Role",
            "Pinged on Gold Guide-tagged Q&A threads, and credited for contributions.",
            <RoleSelect value={draft.gold_guide_role_id} roles={roles} allowEmpty={false}
              onChange={(v) => set("gold_guide_role_id", v)} />)}
          {field("qna_helper_role_id", "Q&A Helper Role",
            "Pinged when someone asks for human help on a Q&A thread.",
            <RoleSelect value={draft.qna_helper_role_id} roles={roles}
              onChange={(v) => set("qna_helper_role_id", v)} />)}
          <SaveBar keys={["verified_role_id", "unverified_role_id", "gold_guide_role_id", "qna_helper_role_id"]} />
        </CardContent>
      </Card>

      {/* ── Admin access ── */}
      <Card className="mb-3">
        <CardContent className="p-4">
          <h5 className="text-base font-semibold mb-1">Admin Access</h5>
          <p className="text-xs text-muted-foreground mb-3">
            Officer roles get read-limited admin access (no message logs or stats). Full
            admins come from the database, so a mistake here cannot lock you out.
          </p>
          <div className="flex justify-between items-baseline gap-3 flex-wrap mb-1.5">
            <Label className="text-xs font-semibold">Officer Roles</Label>
            <OverrideBadge
              meta={settings.admin_restricted_role_ids}
              onReset={() => reset("admin_restricted_role_ids")}
            />
          </div>
          <div className="flex flex-wrap gap-2 mb-2">
            {restricted.length === 0 && (
              <span className="text-sm text-muted-foreground">No officer roles.</span>
            )}
            {restricted.map((id) => (
              <span
                key={id}
                className="inline-flex items-center gap-1.5 text-sm rounded px-2 py-0.5"
                style={{ background: "hsl(var(--muted))" }}
              >
                @{roleName(id) || id}
                <button
                  type="button"
                  aria-label={`Remove ${roleName(id) || id}`}
                  className="bg-transparent border-0 p-0 cursor-pointer text-muted-foreground hover:text-foreground"
                  onClick={() =>
                    set("admin_restricted_role_ids", restricted.filter((r) => r !== id))
                  }
                >
                  ×
                </button>
              </span>
            ))}
          </div>
          <RoleSelect
            value=""
            roles={roles.filter((r) => !restricted.includes(r.id))}
            allowEmpty={false}
            placeholder="— Add a role —"
            onChange={(v) => v && set("admin_restricted_role_ids", [...restricted, v])}
          />
          <div className="mt-3">
            <SaveBar keys={["admin_restricted_role_ids"]} />
          </div>
        </CardContent>
      </Card>

      {/* ── Terms ── */}
      <Card className="mb-3">
        <CardContent className="p-4">
          <h5 className="text-base font-semibold mb-3">Term Codes</h5>
          {field(
            "target_term_code",
            "Target Term Code",
            "4-digit ASU term code used to classify incoming students (e.g. 2267 = Fall 2026).",
            <Input
              className="w-28 h-8 text-sm"
              value={draft.target_term_code ?? ""}
              onChange={(e) => set("target_term_code", e.target.value)}
            />
          )}
          {field(
            "active_term_codes",
            "Active Term Codes",
            "Comma-separated. A Salesforce opportunity in one of these terms is preferred when picking which one describes the student.",
            <Input
              className="max-w-sm h-8 text-sm"
              value={(draft.active_term_codes || []).join(", ")}
              onChange={(e) =>
                set(
                  "active_term_codes",
                  e.target.value.split(",").map((t) => t.trim()).filter(Boolean)
                )
              }
            />
          )}
          <SaveBar keys={["target_term_code", "active_term_codes"]} />
        </CardContent>
      </Card>

      {/* ── Role mapping ── */}
      <Card className="mb-3">
        <CardContent className="p-4">
          <h5 className="text-base font-semibold mb-1">Salesforce Role Mapping</h5>
          <p className="text-xs text-muted-foreground mb-2">
            Which Discord role each Salesforce attribute maps to. Changes apply on the next
            verification or the next Salesforce role refresh — existing members are not re-synced.
          </p>
          <div className="mb-3">
            <OverrideBadge meta={settings.role_id_map} onReset={() => reset("role_id_map")} />
          </div>
          {ROLE_MAP_GROUPS.map((group) => (
            <div key={group.label} className="mb-4">
              <div className="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-2">
                {group.label}
              </div>
              {group.names.map((name) => (
                <div key={name} className="flex items-center gap-3 flex-wrap mb-1.5">
                  <span className="text-sm w-80 shrink-0">{name}</span>
                  <RoleSelect
                    value={String((draft.role_id_map || {})[name] ?? "")}
                    roles={roles}
                    onChange={(v) =>
                      set("role_id_map", { ...(draft.role_id_map || {}), [name]: v })
                    }
                  />
                </div>
              ))}
            </div>
          ))}
          <SaveBar keys={["role_id_map"]} />
        </CardContent>
      </Card>
    </>
  );
}
