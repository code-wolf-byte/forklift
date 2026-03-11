import { useState, useEffect, useLayoutEffect } from "react";
import Dashboard from "./admin/Dashboard.jsx";
import Automations from "./admin/Automations.jsx";
import Users from "./admin/Users.jsx";
import Joins from "./admin/Joins.jsx";
import ServerJoins from "./admin/ServerJoins.jsx";
import Leaves from "./admin/Leaves.jsx";
import MemberStats from "./admin/MemberStats.jsx";

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
      { id: "server-joins", icon: "fa-sign-in-alt",  label: "Joins"         },
      { id: "leaves",       icon: "fa-sign-out-alt", label: "Leaves"        },
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
      className={`admin-nav-item${active ? " active" : ""}`}
      onClick={() => onClick(id)}
    >
      <span className="admin-nav-icon">
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

  // Apply dark class before paint to avoid flash
  useLayoutEffect(() => {
    if (darkMode) {
      document.body.classList.add("admin-dark");
    } else {
      document.body.classList.remove("admin-dark");
    }
    return () => document.body.classList.remove("admin-dark");
  }, [darkMode]);

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
      <div className="container py-5 text-center">
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
      case "automations":   return <Automations />;
      default:              return null;
    }
  };

  return (
    <div className="admin-layout" style={{ minHeight: `calc(100vh - ${sidebarTop}px)` }}>
      {/* ── Sidebar ── */}
      <aside
        className="admin-sidebar"
        style={{ top: sidebarTop, height: `calc(100vh - ${sidebarTop}px)` }}
      >
        {/* Server header */}
        <div className="admin-sidebar-header">
          <i className="fas fa-bolt" style={{ color: "#8c1d40" }} />
          Forklift Admin
        </div>

        {/* Nav sections */}
        {NAV.map((section) => (
          <div key={section.label} className="admin-sidebar-section">
            <div className="admin-sidebar-section-label">{section.label}</div>
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
        <div className="admin-sidebar-footer">
          <div className="flex-grow-1 overflow-hidden">
            {adminUser && (
              <>
                <div className="fw-semibold small text-truncate">
                  {adminUser.asurite_id}
                </div>
                <div className="text-muted text-truncate" style={{ fontSize: 12 }}>
                  {adminUser.discord_username}
                </div>
              </>
            )}
          </div>
          <button
            className="btn btn-sm btn-outline-secondary flex-shrink-0"
            onClick={toggleDark}
            title={darkMode ? "Light mode" : "Dark mode"}
          >
            <i className={`fas ${darkMode ? "fa-sun" : "fa-moon"}`} />
          </button>
        </div>
      </aside>

      {/* ── Main content ── */}
      <div className="admin-main">
        {renderView()}
      </div>
    </div>
  );
}
