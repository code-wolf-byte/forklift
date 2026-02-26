import { useState, useEffect, useLayoutEffect } from "react";
import Header from "./components/Header.jsx";
import Footer from "./components/Footer.jsx";
import Home from "./pages/Home.jsx";

const DEFAULT_STATUS = {
  cas_complete: false,
  discord_complete: false,
  cas_user: {},
  discord_user: {},
  cas_login_url: "/auth/cas/login",
  discord_login_url: "/auth/discord/login",
  verification_error: null,
  discord_configured: false,
  logout_url: "/auth/logout",
  cas_enabled: true,
  student_profile: null,
  verification_state: {},
};

export default function App() {
  const [status, setStatus] = useState(DEFAULT_STATUS);
  const [loading, setLoading] = useState(true);
  const [headerOffset, setHeaderOffset] = useState(0);

  useEffect(() => {
    fetch("/api/status")
      .then((r) => r.json())
      .then((data) => {
        setStatus(data);
        setLoading(false);
      })
      .catch(() => setLoading(false));
  }, []);

  // Offset main content below the sticky ASU header
  useLayoutEffect(() => {
    const el = document.querySelector(".asuHeader");
    if (!el) return;
    const observer = new ResizeObserver(() => {
      setHeaderOffset(el.offsetHeight);
    });
    observer.observe(el);
    return () => observer.disconnect();
  }, [loading]);

  return (
    <>
      <Header
        casComplete={status.cas_complete}
        asurite={status.verification_state?.asurite}
      />
      <main style={{ paddingTop: headerOffset }}>
        {loading ? (
          <div className="container py-5 text-center">
            <div
              className="spinner-border"
              role="status"
              style={{ color: "#8c1d40" }}
            >
              <span className="visually-hidden">Loading...</span>
            </div>
          </div>
        ) : (
          <Home status={status} />
        )}
      </main>
      <Footer />
    </>
  );
}
