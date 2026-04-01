import { useState, useEffect, useRef } from "react";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";

const ROLE_NAMES = [
  // Academic Level
  "First Year",
  "Transfer Student",
  "Graduate Student",
  "Upperclassmen",
  // Special
  "First Generation Student",
  "Commited",
  // College
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
  // Campus
  "Tempe",
  "Downtown Phoenix",
  "Polytechnic",
  "LA Center",
  "West Valley",
  "Online",
  // Residency
  "Out of State",
  "Arizona Resident",
  "International Student",
];

function Avatar({ src, name, size = 32 }) {
  const initials = (name || "?")[0].toUpperCase();
  if (src) {
    return (
      <img
        src={src}
        alt={name}
        width={size}
        height={size}
        style={{ borderRadius: "50%", objectFit: "cover", flexShrink: 0 }}
      />
    );
  }
  return (
    <div
      style={{
        width: size,
        height: size,
        borderRadius: "50%",
        background: "#8c1d40",
        color: "#fff",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        fontWeight: 700,
        fontSize: size * 0.45,
        flexShrink: 0,
      }}
    >
      {initials}
    </div>
  );
}

function ExceptionBadge({ type }) {
  const styles =
    type === "paused"
      ? { background: "#f59e0b", color: "#fff" }
      : { background: "#10b981", color: "#fff" };
  return (
    <span
      style={{
        ...styles,
        borderRadius: 4,
        padding: "1px 7px",
        fontSize: 11,
        fontWeight: 700,
        textTransform: "uppercase",
        letterSpacing: "0.04em",
      }}
    >
      {type === "paused" ? "Paused" : "Added"}
    </span>
  );
}

export default function Exceptions() {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState([]);
  const [searching, setSearching] = useState(false);
  const [selected, setSelected] = useState(null); // discord_user_id
  const [userData, setUserData] = useState(null);
  const [userLoading, setUserLoading] = useState(false);

  // Add-exception form state
  const [formRole, setFormRole] = useState(ROLE_NAMES[0]);
  const [formType, setFormType] = useState("paused");
  const [formNote, setFormNote] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState(null);

  const searchTimer = useRef(null);

  // Debounced search
  useEffect(() => {
    if (searchTimer.current) clearTimeout(searchTimer.current);
    if (!query.trim()) {
      setResults([]);
      setSearching(false);
      return;
    }
    setSearching(true);
    searchTimer.current = setTimeout(() => {
      fetch(`/api/admin/exceptions/search?q=${encodeURIComponent(query)}`)
        .then((r) => r.json())
        .then((d) => {
          setResults(Array.isArray(d) ? d : []);
          setSearching(false);
        })
        .catch(() => setSearching(false));
    }, 300);
  }, [query]);

  // Load user detail when selected changes
  useEffect(() => {
    if (!selected) {
      setUserData(null);
      return;
    }
    setUserLoading(true);
    setUserData(null);
    fetch(`/api/admin/exceptions/user/${selected}`)
      .then((r) => r.json())
      .then((d) => {
        setUserData(d);
        setUserLoading(false);
      })
      .catch(() => setUserLoading(false));
  }, [selected]);

  const refreshUser = () => {
    if (!selected) return;
    fetch(`/api/admin/exceptions/user/${selected}`)
      .then((r) => r.json())
      .then(setUserData)
      .catch(() => {});
  };

  const handleSelect = (member) => {
    setSelected(member.discord_user_id);
    setFormError(null);
  };

  const handleDelete = (exceptionId) => {
    fetch(`/api/admin/exceptions/${exceptionId}`, { method: "DELETE" })
      .then(() => refreshUser())
      .catch(() => {});
  };

  const handleSubmit = (e) => {
    e.preventDefault();
    setFormError(null);
    setSubmitting(true);
    const endpoint =
      formType === "paused"
        ? `/api/admin/exceptions/user/${selected}/pause`
        : `/api/admin/exceptions/user/${selected}/add`;
    fetch(endpoint, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ role_name: formRole, note: formNote || null }),
    })
      .then((r) => {
        if (!r.ok) return r.json().then((d) => { throw new Error(d.error || "Failed"); });
        return r.json();
      })
      .then(() => {
        setFormNote("");
        setSubmitting(false);
        refreshUser();
      })
      .catch((err) => {
        setFormError(err.message);
        setSubmitting(false);
      });
  };

  const borderColor = "hsl(var(--border))";
  const mutedColor = "hsl(var(--muted-foreground))";

  return (
    <>
      <h2 className="text-2xl font-bold mb-1">Role Exceptions</h2>
      <p className="text-sm mb-6" style={{ color: mutedColor }}>
        Pause automatic Salesforce role management for a user, or permanently add a role that
        survives syncs.
      </p>

      <div className="flex gap-4" style={{ alignItems: "flex-start" }}>
        {/* ── Left panel: search ── */}
        <div style={{ width: 280, flexShrink: 0 }}>
          <input
            className="w-full px-3 py-2 rounded border text-sm mb-2"
            style={{ borderColor, background: "hsl(var(--background))", color: "hsl(var(--foreground))" }}
            placeholder="Search members by name…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
          {searching && (
            <p className="text-xs px-1" style={{ color: mutedColor }}>Searching…</p>
          )}
          {results.length > 0 && (
            <Card className="overflow-hidden p-0">
              {results.map((m) => (
                <button
                  key={m.discord_user_id}
                  onClick={() => handleSelect(m)}
                  className="flex items-center gap-2.5 w-full px-3 py-2 text-left border-b last:border-b-0 text-sm"
                  style={{
                    borderColor,
                    background:
                      selected === m.discord_user_id
                        ? "hsl(var(--sidebar-accent))"
                        : "hsl(var(--background))",
                    color: "hsl(var(--foreground))",
                    cursor: "pointer",
                  }}
                >
                  <Avatar src={m.avatar} name={m.display_name || m.username} size={28} />
                  <div style={{ overflow: "hidden" }}>
                    <div className="font-medium truncate">{m.display_name || m.username}</div>
                    <div className="text-xs truncate" style={{ color: mutedColor }}>
                      @{m.username}
                    </div>
                  </div>
                </button>
              ))}
            </Card>
          )}
          {!searching && query.trim() && results.length === 0 && (
            <p className="text-xs px-1" style={{ color: mutedColor }}>No members found.</p>
          )}
        </div>

        {/* ── Right panel: user detail ── */}
        <div style={{ flex: 1, minWidth: 0 }}>
          {!selected && (
            <p className="text-sm" style={{ color: mutedColor }}>
              Search and select a member to manage their role exceptions.
            </p>
          )}

          {selected && userLoading && (
            <div className="flex justify-center py-10">
              <div className="spinner-border" role="status" style={{ color: "#8c1d40" }}>
                <span className="visually-hidden">Loading…</span>
              </div>
            </div>
          )}

          {selected && userData && !userLoading && (
            <div className="flex flex-col gap-4">
              {/* Member header */}
              <Card className="p-4">
                <div className="flex items-center gap-3">
                  <Avatar
                    src={userData.member_info?.avatar}
                    name={userData.member_info?.display_name || userData.db_user?.discord_username}
                    size={44}
                  />
                  <div>
                    <div className="font-bold text-base">
                      {userData.member_info?.display_name ||
                        userData.db_user?.discord_username ||
                        userData.discord_user_id}
                    </div>
                    <div className="text-sm" style={{ color: mutedColor }}>
                      {userData.db_user
                        ? `@${userData.db_user.discord_username} · ${userData.db_user.asurite_id}`
                        : `Discord ID: ${userData.discord_user_id}`}
                    </div>
                  </div>
                  {userData.db_user?.verified && (
                    <Badge className="ml-auto" style={{ background: "#8c1d40" }}>
                      Verified
                    </Badge>
                  )}
                </div>

                {userData.db_roles.length > 0 && (
                  <div className="mt-3">
                    <div className="text-xs font-semibold uppercase tracking-wide mb-1.5" style={{ color: mutedColor }}>
                      Current Salesforce Roles
                    </div>
                    <div className="flex flex-wrap gap-1.5">
                      {userData.db_roles.map((r) => (
                        <span
                          key={r}
                          className="text-xs px-2 py-0.5 rounded"
                          style={{ background: "hsl(var(--muted))", color: "hsl(var(--foreground))" }}
                        >
                          {r}
                        </span>
                      ))}
                    </div>
                  </div>
                )}
              </Card>

              {/* Active exceptions */}
              <Card className="p-4">
                <div className="text-sm font-bold mb-3">Active Exceptions</div>
                {userData.exceptions.length === 0 ? (
                  <p className="text-sm" style={{ color: mutedColor }}>
                    No exceptions. Salesforce sync runs normally for this member.
                  </p>
                ) : (
                  <div className="flex flex-col gap-2">
                    {userData.exceptions.map((exc) => (
                      <div
                        key={exc.id}
                        className="flex items-center gap-3 px-3 py-2 rounded"
                        style={{ background: "hsl(var(--muted))" }}
                      >
                        <ExceptionBadge type={exc.exception_type} />
                        <span className="text-sm font-medium flex-1">{exc.role_name}</span>
                        {exc.note && (
                          <span className="text-xs" style={{ color: mutedColor }}>
                            {exc.note}
                          </span>
                        )}
                        <button
                          onClick={() => handleDelete(exc.id)}
                          title="Remove exception"
                          style={{
                            background: "none",
                            border: "none",
                            cursor: "pointer",
                            color: mutedColor,
                            fontSize: 14,
                            lineHeight: 1,
                            padding: "0 2px",
                          }}
                        >
                          <i className="fas fa-times" />
                        </button>
                      </div>
                    ))}
                  </div>
                )}
              </Card>

              {/* Add exception form */}
              <Card className="p-4">
                <div className="text-sm font-bold mb-3">Add Exception</div>
                <form onSubmit={handleSubmit} className="flex flex-col gap-3">
                  <div className="flex gap-3 flex-wrap">
                    {/* Role selector */}
                    <div style={{ flex: "1 1 220px", minWidth: 0 }}>
                      <label className="block text-xs font-semibold mb-1" style={{ color: mutedColor }}>
                        Role
                      </label>
                      <select
                        className="w-full px-2 py-1.5 rounded border text-sm"
                        style={{ borderColor, background: "hsl(var(--background))", color: "hsl(var(--foreground))" }}
                        value={formRole}
                        onChange={(e) => setFormRole(e.target.value)}
                      >
                        {ROLE_NAMES.map((r) => (
                          <option key={r} value={r}>{r}</option>
                        ))}
                      </select>
                    </div>

                    {/* Type selector */}
                    <div style={{ flex: "0 0 140px" }}>
                      <label className="block text-xs font-semibold mb-1" style={{ color: mutedColor }}>
                        Type
                      </label>
                      <select
                        className="w-full px-2 py-1.5 rounded border text-sm"
                        style={{ borderColor, background: "hsl(var(--background))", color: "hsl(var(--foreground))" }}
                        value={formType}
                        onChange={(e) => setFormType(e.target.value)}
                      >
                        <option value="paused">Paused — skip this role in syncs</option>
                        <option value="added">Added — always keep this role</option>
                      </select>
                    </div>
                  </div>

                  {/* Note */}
                  <div>
                    <label className="block text-xs font-semibold mb-1" style={{ color: mutedColor }}>
                      Note (optional)
                    </label>
                    <input
                      className="w-full px-2 py-1.5 rounded border text-sm"
                      style={{ borderColor, background: "hsl(var(--background))", color: "hsl(var(--foreground))" }}
                      placeholder="Reason for this exception…"
                      value={formNote}
                      onChange={(e) => setFormNote(e.target.value)}
                    />
                  </div>

                  {formError && (
                    <p className="text-xs text-red-500">{formError}</p>
                  )}

                  <div>
                    <Button
                      type="submit"
                      disabled={submitting}
                      style={{ background: "#8c1d40", color: "#fff", border: "none" }}
                    >
                      {submitting ? "Saving…" : "Add Exception"}
                    </Button>
                  </div>
                </form>

                <div className="mt-3 text-xs" style={{ color: mutedColor }}>
                  <strong>Paused:</strong> Salesforce sync will not add or remove this role for this
                  member — their current Discord role state is preserved.
                  <br />
                  <strong>Added:</strong> This role is immediately granted and will never be removed
                  by automated syncs.
                </div>
              </Card>
            </div>
          )}
        </div>
      </div>
    </>
  );
}
