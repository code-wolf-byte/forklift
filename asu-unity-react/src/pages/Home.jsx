import heroImage from "../assets/devil2devil-hero.jpeg";
import profileGif from "../assets/devil2devil-profile.gif";
import discordLogo from "../assets/discord.png";

// ─── Hero ─────────────────────────────────────────────────────────────────────

function HeroSection() {
  return (
    <section
      className="hero-section py-5"
      style={{ backgroundImage: `url(${heroImage})` }}
      aria-label="Devil2Devil hero"
    >
      <div className="container hero-content">
        <div className="row">
          <div className="col-12 col-md-8 col-lg-6">
            <h1 className="display-4 fw-bold text-white mb-3">
              <span className="text-gold">Devil</span>
              <span className="text-white">2</span>
              <span className="text-gold">Devil</span>
            </h1>
            <p className="lead text-white mb-4">
              Find new friends, join communities and make connections in ASU's
              Devil2Devil Discord server for admitted students.
            </p>
            <a
              href="https://devil2devil.asu.edu/"
              className="btn btn-gold btn-lg"
              target="_blank"
              rel="noopener noreferrer"
            >
              Learn more
            </a>
          </div>
        </div>
      </div>
    </section>
  );
}

// ─── Verification step card ────────────────────────────────────────────────────

function StepCard({
  stepNumber,
  icon,
  title,
  description,
  complete,
  enabled,
  children,
}) {
  const cardClass = [
    "card h-100 step-card",
    complete ? "completed" : "",
    !enabled ? "disabled" : "",
  ]
    .filter(Boolean)
    .join(" ");

  return (
    <div className="col-12 col-sm-6 col-xl-3">
      <div className={cardClass}>
        <div className="card-body py-4 px-3">
          <div className="d-flex justify-content-between align-items-start mb-2">
            <span className="badge bg-secondary">Step {stepNumber}</span>
            {complete && (
              <span className="badge-complete">
                <i className="fas fa-check me-1" aria-hidden="true" />
                Completed
              </span>
            )}
          </div>
          <div className="step-icon my-3">{icon}</div>
          <h3 className="h5 card-title">{title}</h3>
          <p className="card-text text-muted small">{description}</p>
          <div className="card-actions">{children}</div>
        </div>
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
}) {
  const step2Enabled = casComplete;
  const step3Enabled = discordComplete;

  return (
    <section id="verification-steps" className="py-5">
      <div className="container">
        <div className="text-center mb-5">
          <h2 className="fw-bold">
            Get Started with{" "}
            <span style={{ color: "#8c1d40" }}>Devil2Devil</span>
          </h2>
          <p className="text-muted">
            Complete the steps below to join the community.
          </p>
        </div>

        {verificationError && (
          <div className="alert alert-danger mb-4" role="alert">
            <i className="fas fa-exclamation-triangle me-2" aria-hidden="true" />
            {verificationError}
          </div>
        )}

        <div className="row g-4">
          {/* Step 1 — My ASU */}
          <StepCard
            stepNumber={1}
            icon={<i className="fas fa-user-circle fa-2x" aria-hidden="true" />}
            title="My ASU"
            description="Login with your ASURITE ID to verify your admission status."
            complete={casComplete}
            enabled={true}
          >
            {casComplete ? (
              <>
                <span className="text-success small fw-semibold">
                  <i className="fas fa-check me-1" />
                  Verified as {verificationState?.asurite}
                </span>
                <a href={casLoginUrl} className="btn btn-sm btn-outline-maroon">
                  Reauthenticate
                </a>
              </>
            ) : (
              <a href={casLoginUrl} className="btn btn-maroon btn-sm">
                My ASU
              </a>
            )}
          </StepCard>

          {/* Step 2 — Discord */}
          <StepCard
            stepNumber={2}
            icon={
              <img
                src={discordLogo}
                alt="Discord logo"
                style={{ height: "2.5rem" }}
              />
            }
            title="Connect Discord"
            description="Connect your Discord account and approve the Forkman bot."
            complete={discordComplete}
            enabled={step2Enabled}
          >
            {discordComplete ? (
              <span className="text-success small fw-semibold">
                <i className="fas fa-check me-1" />
                {discordUser?.username
                  ? `Connected as ${discordUser.username}`
                  : "Discord linked"}
              </span>
            ) : discordConfigured ? (
              <a
                href={discordLoginUrl}
                className="btn btn-maroon btn-sm"
                aria-disabled={!step2Enabled}
              >
                Connect Discord
              </a>
            ) : (
              <span className="text-muted small">Discord not configured</span>
            )}
          </StepCard>

          {/* Step 3 — Join Server */}
          <StepCard
            stepNumber={3}
            icon={
              <i className="fab fa-discord fa-2x" style={{ color: "#5865f2" }} aria-hidden="true" />
            }
            title="Devil2Devil Server"
            description="Join the Devil2Devil Discord community for Class of Fall 2026."
            complete={false}
            enabled={step3Enabled}
          >
            <a
              href="https://discord.gg/devil2devil"
              className="btn btn-maroon btn-sm"
              target="_blank"
              rel="noopener noreferrer"
              aria-disabled={!step3Enabled}
            >
              Visit Devil2Devil
            </a>
          </StepCard>

          {/* Step 4 — Instagram */}
          <StepCard
            stepNumber={4}
            icon={
              <i
                className="fab fa-instagram fa-2x"
                style={{ color: "#e1306c" }}
                aria-hidden="true"
              />
            }
            title="Future Sun Devils"
            description="Follow @FutureSunDevils on Instagram to stay up to date."
            complete={false}
            enabled={true}
          >
            <a
              href="https://www.instagram.com/futuresundevils/"
              className="btn btn-maroon btn-sm"
              target="_blank"
              rel="noopener noreferrer"
            >
              Instagram
            </a>
          </StepCard>
        </div>

        {discordComplete && logoutUrl && (
          <div className="text-center mt-4">
            <form method="POST" action={logoutUrl} style={{ display: "inline" }}>
              <button type="submit" className="btn btn-outline-secondary btn-sm">
                <i className="fas fa-sign-out-alt me-1" aria-hidden="true" />
                Sign out
              </button>
            </form>
          </div>
        )}
      </div>
    </section>
  );
}

// ─── About section ─────────────────────────────────────────────────────────────

function AboutSection() {
  return (
    <section id="about" className="py-5 bg-light">
      <div className="container">
        <div className="row align-items-center g-5">
          <div className="col-12 col-md-5 text-center">
            <img
              src={profileGif}
              alt="Devil2Devil community"
              className="img-fluid rounded shadow"
              loading="lazy"
              style={{ maxHeight: "320px" }}
            />
          </div>
          <div className="col-12 col-md-7">
            <h2 className="fw-bold mb-3">
              <span style={{ color: "#8c1d40" }}>Devil2Devil</span>{" "}
              <span className="text-gold" style={{ color: "#ffb310" }}>
                Fall 2026
              </span>
            </h2>
            <p className="mb-3">
              Devil2Devil is ASU's Discord community hub for students enrolling
              in Fall 2026. Connect with fellow students across all ASU campuses
              — Tempe, West, Polytechnic, Downtown Phoenix, and the LA Center.
            </p>
            <p className="text-muted small mb-0">
              Open for engagement starting in November 2025.
            </p>
          </div>
        </div>
      </div>
    </section>
  );
}

// ─── Next Steps section ────────────────────────────────────────────────────────

const NEXT_STEPS = [
  {
    label: "First-year student",
    href: "https://admission.asu.edu/first-year/next-steps",
  },
  {
    label: "Transfer student",
    href: "https://admission.asu.edu/transfer/next-steps",
  },
  {
    label: "Graduate student",
    href: "https://graduate.asu.edu/prospective-students/steps-apply",
  },
  {
    label: "International first-year",
    href: "https://admission.asu.edu/international/first-year",
  },
  {
    label: "International transfer",
    href: "https://admission.asu.edu/international/transfer",
  },
  {
    label: "International graduate",
    href: "https://graduate.asu.edu/prospective-students/international-students",
  },
];

function NextStepsSection() {
  return (
    <section className="py-5">
      <div className="container">
        <h2 className="fw-bold mb-2">Next Steps</h2>
        <p className="text-muted mb-4">
          Find your personalized next steps based on your student type.
        </p>
        <div className="next-steps-grid">
          {NEXT_STEPS.map((step) => (
            <a
              key={step.href}
              href={step.href}
              className="next-step-card"
              target="_blank"
              rel="noopener noreferrer"
            >
              <span className="step-label">{step.label}</span>
              <i
                className="fas fa-chevron-right text-muted"
                aria-hidden="true"
              />
            </a>
          ))}
        </div>
      </div>
    </section>
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
      />
      <AboutSection />
      <NextStepsSection />
    </>
  );
}
