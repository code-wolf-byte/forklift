import { useState, useEffect } from "react";

function timeAgo(isoStr) {
  if (!isoStr) return "—";
  // Treat naive ISO string as UTC
  const date = new Date(
    isoStr.endsWith("Z") || isoStr.includes("+") ? isoStr : isoStr + "Z"
  );
  const diff = (Date.now() - date.getTime()) / 1000;
  if (diff < 60) return "just now";
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  if (diff < 86400 * 7) return `${Math.floor(diff / 86400)}d ago`;
  return date.toLocaleDateString("en-US", {
    timeZone: "America/Phoenix",
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}

function avatarUrl(userId, avatarHash) {
  if (!userId || !avatarHash) return null;
  return `https://cdn.discordapp.com/avatars/${userId}/${avatarHash}.png?size=64`;
}

function Avatar({ userId, avatarHash, username }) {
  const src = avatarUrl(userId, avatarHash);
  const initial = (username || "?")[0].toUpperCase();

  if (src) {
    return (
      <img
        src={src}
        alt={username}
        style={{
          width: 40,
          height: 40,
          borderRadius: "50%",
          objectFit: "cover",
          flexShrink: 0,
        }}
        onError={(e) => {
          e.target.style.display = "none";
          e.target.nextSibling.style.display = "flex";
        }}
      />
    );
  }

  return (
    <div
      style={{
        width: 40,
        height: 40,
        borderRadius: "50%",
        background: "#8c1d40",
        color: "#fff",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        fontWeight: 700,
        fontSize: 16,
        flexShrink: 0,
      }}
    >
      {initial}
    </div>
  );
}

export default function Joins() {
  const [joins, setJoins] = useState(null);

  useEffect(() => {
    fetch("/api/admin/joins?limit=50")
      .then((r) => r.json())
      .then(setJoins)
      .catch(() => setJoins([]));
  }, []);

  if (!joins) {
    return (
      <div className="text-center py-5">
        <div className="spinner-border" role="status" style={{ color: "#8c1d40" }}>
          <span className="visually-hidden">Loading…</span>
        </div>
      </div>
    );
  }

  return (
    <>
      <h2 className="mb-1">Verifications</h2>
      <p className="text-muted small mb-4">
        Most recent {joins.length} verified members.
      </p>

      {joins.length === 0 ? (
        <p className="text-muted">No verified members yet.</p>
      ) : (
        <div className="card p-0" style={{ overflow: "hidden" }}>
          {joins.map((user, i) => (
            <div
              key={user.id}
              className="d-flex align-items-center gap-3 px-3 py-2"
              style={{
                borderBottom: i < joins.length - 1 ? "1px solid var(--join-divider, #e3e5e8)" : "none",
              }}
            >
              <Avatar
                userId={user.discord_user_id}
                avatarHash={user.discord_avatar}
                username={user.discord_username}
              />
              <div className="flex-grow-1 overflow-hidden">
                <div className="d-flex align-items-center gap-2 flex-wrap">
                  <span className="fw-semibold text-truncate" style={{ maxWidth: 200 }}>
                    {user.discord_username || "Unknown"}
                  </span>
                  <span className="text-muted small text-truncate">{user.asurite_id}</span>
                </div>
              </div>
              <div
                className="text-muted small text-nowrap flex-shrink-0"
                title={user.verified_at}
              >
                <i className="fas fa-user-check me-1" style={{ color: "#8c1d40" }} />
                {timeAgo(user.verified_at)}
              </div>
            </div>
          ))}
        </div>
      )}
    </>
  );
}
