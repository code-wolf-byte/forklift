import "@/admin.css";
import { useState, useEffect, useLayoutEffect } from "react";
import { Button } from "@/components/ui/button";
import Dashboard from "./admin/Dashboard.jsx";
import Automations from "./admin/Automations.jsx";
import Users from "./admin/Users.jsx";
import Joins from "./admin/Joins.jsx";
import ServerJoins from "./admin/ServerJoins.jsx";
import Leaves from "./admin/Leaves.jsx";
import MemberStats from "./admin/MemberStats.jsx";
import MessageLogs from "./admin/MessageLogs.jsx";
import QnA from "./admin/QnA.jsx";

// ─── Sidebar navigation config ────────────────────────────────────────────────

const NAV = [
  {
    label: "General",
    items: [
      { id: "dashboard", icon: "fa-chart-bar", label: "Overview" },
    ],
  },
  {
    label: "Management",
    items: [
      { id: "members",      icon: "fa-users",        label: "Members"       },
      { id: "joins",        icon: "fa-user-check",   label: "Verifications" },
      { id: "member-stats", icon: "fa-chart-pie",    label: "Member Stats"  },
    ],
  },
  {
    label: "Activity",
    items: [
      { id: "server-joins",  icon: "fa-sign-in-alt",  label: "Joins"         },
      { id: "leaves",        icon: "fa-sign-out-alt", label: "Leaves"        },
      { id: "message-logs",  icon: "fa-comments",     label: "Message Logs"  },
    ],
  },
  {
    label: "Q&A",
    items: [
      { id: "qna", icon: "fa-question-circle", label: "Q&A Analytics" },
    ],
  },
  {
    label: "System",
    items: [
      { id: "automations",  icon: "fa-robot",        label: "Automations"   },
    ],
  },
];

function NavItem({ id, icon, label, active, onClick }) {
  return (
    <button
      className={[
        "flex items-center gap-2.5 w-full px-2.5 py-1.5 rounded text-left cursor-pointer text-[15px] font-medium transition-colors mb-px border-0",
        active
          ? "bg-sidebar-accent text-sidebar-accent-foreground font-semibold"
          : "bg-transparent text-sidebar-foreground/70 hover:bg-sidebar-accent/50 hover:text-sidebar-foreground",
      ].join(" ")}
      onClick={() => onClick(id)}
    >
      <span className="w-[18px] text-center text-[15px] shrink-0">
        <i className={`fas ${icon}`} />
      </span>
      {label}
    </button>
  );
}

// ─── Admin shell ──────────────────────────────────────────────────────────────

export default function Admin() {
  const [activeView, setActiveView] = useState("dashboard");
  const [adminUser, setAdminUser] = useState(null);
  const [loading, setLoading] = useState(true);
  const [sidebarTop, setSidebarTop] = useState(0);
  const [darkMode, setDarkMode] = useState(
    () => localStorage.getItem("admin_theme") === "dark"
  );

  // Measure fixed ASU header so sidebar sticks just below it
  useEffect(() => {
    const el = document.querySelector(".asuHeader") || document.querySelector("header");
    if (el) setSidebarTop(el.offsetHeight);
  }, []);

  const toggleDark = () =>
    setDarkMode((prev) => {
      const next = !prev;
      localStorage.setItem("admin_theme", next ? "dark" : "light");
      return next;
    });

  // Auth check + initial stats fetch
  useEffect(() => {
    fetch("/api/admin/me")
      .then((r) => {
        if (r.status === 403) { window.location.href = "/"; return null; }
        return r.json();
      })
      .then((data) => {
        if (!data) return;
        setAdminUser(data);
        setLoading(false);
      })
      .catch(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20">
        <div className="spinner-border" role="status" style={{ color: "#8c1d40" }}>
          <span className="visually-hidden">Loading...</span>
        </div>
      </div>
    );
  }

  const renderView = () => {
    switch (activeView) {
      case "dashboard":     return <Dashboard />;
      case "members":       return <Users />;
      case "joins":         return <Joins />;
      case "member-stats":  return <MemberStats />;
      case "server-joins":  return <ServerJoins isDark={darkMode} />;
      case "leaves":        return <Leaves isDark={darkMode} />;
      case "message-logs":  return <MessageLogs />;
      case "automations":   return <Automations />;
      case "qna":           return <QnA />;
      default:              return null;
    }
  };

  return (
    <div
      className={["admin-layout flex", darkMode ? "admin-dark" : ""].join(" ")}
      style={{ minHeight: `calc(100vh - ${sidebarTop}px)`, background: "hsl(var(--background))", color: "hsl(var(--foreground))" }}
    >
      {/* ── Sidebar ── */}
      <aside
        className="w-60 shrink-0 flex flex-col sticky overflow-y-auto"
        style={{
          top: sidebarTop,
          height: `calc(100vh - ${sidebarTop}px)`,
          background: "hsl(var(--sidebar-background))",
          borderRight: "1px solid hsl(var(--sidebar-border))",
        }}
      >
        {/* Server header */}
        <div
          className="flex items-center gap-2.5 px-4 py-3.5 font-bold text-sm uppercase tracking-wider shrink-0"
          style={{ borderBottom: "1px solid hsl(var(--sidebar-border))", color: "hsl(var(--sidebar-foreground))" }}
        >
          <i className="fas fa-bolt" style={{ color: "#8c1d40" }} />
          Forklift Admin
        </div>

        {/* Nav sections */}
        {NAV.map((section) => (
          <div key={section.label} className="px-2 pt-4 pb-1">
            <div
              className="px-2 pb-1 text-[11px] font-bold uppercase tracking-[0.06em]"
              style={{ color: "hsl(var(--muted-foreground))" }}
            >
              {section.label}
            </div>
            {section.items.map((item) => (
              <NavItem
                key={item.id}
                {...item}
                active={activeView === item.id}
                onClick={setActiveView}
              />
            ))}
          </div>
        ))}

        {/* Footer: user info + dark mode toggle */}
        <div
          className="mt-auto flex items-center gap-2 px-3 py-2.5 shrink-0"
          style={{ borderTop: "1px solid hsl(var(--sidebar-border))", color: "hsl(var(--sidebar-foreground))" }}
        >
          <div className="flex-1 overflow-hidden">
            {adminUser && (
              <>
                <div className="font-semibold text-sm truncate">
                  {adminUser.asurite_id}
                </div>
                <div className="text-[12px] truncate" style={{ color: "hsl(var(--muted-foreground))" }}>
                  {adminUser.discord_username}
                </div>
              </>
            )}
          </div>
          <Button
            size="icon"
            variant="outline"
            className="shrink-0 h-8 w-8"
            onClick={toggleDark}
            title={darkMode ? "Light mode" : "Dark mode"}
          >
            <i className={`fas ${darkMode ? "fa-sun" : "fa-moon"}`} />
          </Button>
        </div>
      </aside>

      {/* ── Main content ── */}
      <div className="flex-1 p-8 min-w-0">
        {renderView()}
      </div>
    </div>
  );
}
