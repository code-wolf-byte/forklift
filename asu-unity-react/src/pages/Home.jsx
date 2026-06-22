import { useState } from "react";
import profileGif from "../assets/devil2devil-profile.gif";

const isAndroid = /android/i.test(navigator.userAgent);
const isIOS = /iphone|ipad|ipod/i.test(navigator.userAgent);

function toAndroidIntentUrl(url) {
  const parsed = new URL(url);
  const fallback = encodeURIComponent(url);
  return `intent://${parsed.host}${parsed.pathname}${parsed.search}#Intent;scheme=https;package=com.discord;S.browser_fallback_url=${fallback};end`;
}

function navigateWithIOSFallback(appUrl, webUrl) {
  const start = Date.now();
  window.location.href = appUrl;
  setTimeout(() => {
    if (Date.now() - start < 1800) {
      window.location.href = webUrl;
    }
  }, 1500);
}

function useDiscordRedirect() {
  const [loading, setLoading] = useState(false);

  const handleClick = async (e) => {
    e.preventDefault();
    if (loading) return;
    setLoading(true);
    try {
      const res = await fetch("/auth/discord/prepare", { method: "POST" });
      const data = await res.json();
      if (data.authorize_url) {
        if (isAndroid) {
          window.location.href = toAndroidIntentUrl(data.authorize_url);
        } else if (isIOS) {
          const parsed = new URL(data.authorize_url);
          const appUrl = `discord://${parsed.host}${parsed.pathname}${parsed.search}`;
          navigateWithIOSFallback(appUrl, data.authorize_url);
        } else {
          window.location.href = data.authorize_url;
        }
        return;
      }
      if (data.redirect) {
        window.location.href = data.redirect;
        return;
      }
    } catch {
      window.location.href = "/auth/discord/login";
    } finally {
      setLoading(false);
    }
  };

  return { handleClick, loading };
}

// ─── Verification step card ────────────────────────────────────────────────────

function StepCard({ icon, title, description, complete, enabled, children }) {
  const wrapperClass = [
    "card-wrapper",
    complete ? "completed-card" : "",
    !enabled ? "disabled-card" : "",
  ]
    .filter(Boolean)
    .join(" ");

  return (
    <div className={wrapperClass}>
      <div className="card cards-components">
        {icon}
        <div className="card-header">
          <h3 className="card-title">{title}</h3>
        </div>
        <div className="card-body">
          <p>{description}</p>
        </div>
        <div className="card-buttons">{children}</div>
      </div>
    </div>
  );
}

// ─── Verification steps section ───────────────────────────────────────────────

function VerificationSection({
  casComplete,
  discordComplete,
  casLoginUrl,
  discordLoginUrl,
  discordConfigured,
  logoutUrl,
  verificationError,
  verificationState,
  discordUser,
  isAdmin,
}) {
  const { handleClick: handleDiscordClick, loading: discordLoading } = useDiscordRedirect();
  const step2Enabled = casComplete;
  const step3Enabled = discordComplete;

  const contextLine = discordComplete ? (
    <span className="badge text-bg-success">All steps complete</span>
  ) : casComplete ? (
    "Next up: connect your Discord account."
  ) : (
    "Start by signing in with your ASURITE ID."
  );

  let statusMessage = null;
  if (discordComplete) {
    const username = verificationState?.discord_username || discordUser?.username;
    statusMessage = (
      <p className="mb-0">
        Your ASU account
        {verificationState?.asurite && (
          <> (<strong>{verificationState.asurite}</strong>)</>
        )}{" "}
        is linked with Discord. Welcome to Devil2Devil
        {username && `, ${username}`}!
      </p>
    );
  } else if (casComplete) {
    statusMessage = (
      <p className="mb-0">
        You're signed in with ASU
        {verificationState?.asurite && (
          <> as <strong>{verificationState.asurite}</strong></>
        )}
        {verificationState?.email && ` (${verificationState.email})`}. Connect
        your Discord account to finish verification.
      </p>
    );
  }

  return (
    <section id="verification-steps" className="py-5 bg-white">
      <div className="container">
        <div className="mb-4">
          <div className="uds-highlighted-heading">
            <h2>
              <span className="highlight-gold">Verify Your Discord Account</span>
            </h2>
          </div>
          <div className="text-muted small mt-2">{contextLine}</div>
          {(discordComplete || casComplete || verificationError) && (
            <div className="mt-3 text-black">
              {statusMessage}
              {verificationError && (
                <div className="alert alert-warning border-0 fw-semibold text-dark bg-warning-subtle mt-3 mb-0">
                  Verification issue: {verificationError}
                </div>
              )}
            </div>
          )}
        </div>

        <div className="uds-card-arrangement">
          <div className="uds-card-arrangement-content-container default" />
          <div className="uds-card-arrangement-card-container auto-arrangement four-columns">

            {/* Step 1 — My ASU */}
            <StepCard
              icon={<i className="fas fa-desktop fa-2x card-icon-top" aria-hidden="true" />}
              title="My ASU"
              description="Log in to MyASU so we can verify your admission status. You'll be returned here to link your Discord account."
              complete={casComplete}
              enabled={true}
            >
              {casLoginUrl ? (
                <a href={casLoginUrl} className="btn btn-maroon">
                  {casComplete ? "Reauthenticate with ASU" : "My ASU"}
                </a>
              ) : (
                <a href="#" className="btn btn-secondary disabled" aria-disabled="true">
                  ASU login unavailable
                </a>
              )}
            </StepCard>

            {/* Step 2 — Discord */}
            <StepCard
              icon={<i className="fab fa-discord fa-2x card-icon-top" aria-hidden="true" />}
              title="Discord"
              description={
                discordComplete
                  ? `Discord is linked${discordUser?.username ? ` as ${discordUser.username}` : ""}. You can reconnect to refresh permissions.`
                  : step2Enabled
                  ? "Approve the Forkman bot to verify you in the server and grant your verified role automatically."
                  : "Complete Step 1 to unlock this step."
              }
              complete={discordComplete}
              enabled={step2Enabled}
            >
              {discordConfigured && discordLoginUrl ? (
                <button
                  type="button"
                  onClick={handleDiscordClick}
                  disabled={!step2Enabled || discordLoading}
                  className={`btn btn-maroon${!step2Enabled ? " disabled" : ""}`}
                  aria-disabled={!step2Enabled || undefined}
                >
                  {discordLoading
                    ? "Connecting…"
                    : discordComplete
                    ? "Manage Discord Link"
                    : "Connect Discord"}
                </button>
              ) : (
                <div className="alert alert-secondary small mb-0">
                  Discord integration is not configured.
                </div>
              )}
            </StepCard>

            {/* Step 3 — Devil2Devil Server */}
            <StepCard
              icon={<i className="fas fa-comments fa-2x card-icon-top" aria-hidden="true" />}
              title="Devil2Devil Server"
              description="Head to the Devil2Devil Discord community and start meeting the Class of Fall 2026!"
              complete={false}
              enabled={step3Enabled}
            >
              <a
                href={
                  step3Enabled
                    ? "https://discord.com/channels/1187144343400751234/1435338904994709626"
                    : "#"
                }
                className={`btn btn-maroon${!step3Enabled ? " disabled" : ""}`}
                aria-disabled={!step3Enabled || undefined}
                {...(step3Enabled
                  ? { target: "_blank", rel: "noopener noreferrer" }
                  : {})}
              >
                Visit Devil2Devil
              </a>
            </StepCard>

            {/* Step 4 — Instagram */}
            <StepCard
              icon={<i className="fab fa-instagram fa-2x card-icon-top" aria-hidden="true" />}
              title="Future Sun Devils Instagram"
              description="Follow @FutureSunDevils on Instagram and click the link in our bio to join the server."
              complete={false}
              enabled={true}
            >
              <a
                href="https://www.instagram.com/futuresundevils/"
                className="btn btn-maroon"
                target="_blank"
                rel="noopener noreferrer"
              >
                Instagram
              </a>
            </StepCard>

          </div>
        </div>

        {discordComplete && (
          <div className="d-flex justify-content-center gap-3 mt-4 flex-wrap">
            {isAdmin && (
              <a href="/admin" className="btn btn-maroon text-white">
                Admin Dashboard
              </a>
            )}
            {logoutUrl && (
              <form method="POST" action={logoutUrl}>
                <button type="submit" className="btn btn-maroon text-white btn-no-hover">
                  Log out of My ASU and Discord
                </button>
              </form>
            )}
          </div>
        )}
      </div>
    </section>
  );
}

// ─── About section ─────────────────────────────────────────────────────────────

function AboutSection() {
  return (
    <div className="spacing-top-72 spacing-bottom-32">
      <div className="container">
        <div className="row g-5 align-items-center">
          <div className="col-lg-4 text-center text-lg-start">
            <img
              src={profileGif}
              alt="Devil2Devil profile graphic"
              className="img-fluid rounded"
              loading="lazy"
            />
          </div>
          <div className="col-lg-8">
            <div className="uds-highlighted-heading">
              <h2>
                <span className="highlight-gold">Devil2Devil Fall 2026</span>
              </h2>
            </div>
            <p>
              Devil2Devil serves as ASU's vibrant Discord community for admitted
              students enrolling in the Fall 2026 semester. Whether you're an
              incoming first-year, transfer or master's-level graduate student,
              from as close as central Phoenix to as far-flung as Hanoi, Vietnam,
              you can seamlessly connect with peers on Discord's engaging platform.
              Upon joining, you'll be automatically sorted into channels based on
              your campus location, enabling you to form instant connections within
              your academic community. It's a hub for forging friendships, finding
              potential roommates, engaging with current students about campus life
              and staying updated on all things ASU, ensuring a smooth transition
              before you set foot on campus in the fall.
            </p>
            <p>
              Devil2Devil is open for engagement starting in November 2025 and is
              tailored for students attending in-person degree programs at ASU's
              Downtown Phoenix, Polytechnic, Tempe and West Valley campuses, as
              well as LA Center.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}

// ─── Home page ─────────────────────────────────────────────────────────────────

export default function Home({ status }) {
  const {
    cas_complete,
    discord_complete,
    cas_login_url,
    discord_login_url,
    discord_configured,
    logout_url,
    verification_error,
    verification_state,
    discord_user,
    is_admin,
  } = status;

  return (
    <>
      <VerificationSection
        casComplete={cas_complete}
        discordComplete={discord_complete}
        casLoginUrl={cas_login_url}
        discordLoginUrl={discord_login_url}
        discordConfigured={discord_configured}
        logoutUrl={logout_url}
        verificationError={verification_error}
        verificationState={verification_state}
        discordUser={discord_user}
        isAdmin={is_admin}
      />
      <AboutSection />
    </>
  );
}
