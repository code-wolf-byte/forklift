import heroImage from "../assets/devil2devil-hero.jpeg";
import profileGif from "../assets/devil2devil-profile.gif";

// ─── Hero ─────────────────────────────────────────────────────────────────────

function HeroSection() {
  return (
    <div className="uds-hero-lg">
      <div className="hero-overlay" />
      <img
        className="hero"
        src={heroImage}
        alt=""
        loading="lazy"
        decoding="async"
      />
      <h1>
        <span className="highlight-gold">Devil2Devil</span>
      </h1>
      <div className="content hero-cta">
        <p className="text-white">
          Find new friends, join communities and make connections in ASU's
          Devil2Devil Discord server for admitted students.
        </p>
        <div className="d-flex flex-wrap gap-3 align-items-center mt-4 hero-cta-buttons">
          <a
            className="btn btn-maroon text-white"
            href="https://devil2devil.asu.edu/"
            target="_blank"
            rel="noopener noreferrer"
          >
            Learn more
          </a>
        </div>
      </div>
    </div>
  );
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
                <a
                  href={discordLoginUrl}
                  className={`btn btn-maroon${!step2Enabled ? " disabled" : ""}`}
                  aria-disabled={!step2Enabled || undefined}
                >
                  {discordComplete ? "Manage Discord Link" : "Connect Discord"}
                </a>
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
      <HeroSection />
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
