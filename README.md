# Forklift

Forklift is the backend for **Devil2Devil**, ASU's Discord community. It's a Flask
application paired with a Discord bot (py-cord) that verifies students, manages
Discord roles, tracks server activity, runs a support-ticket system, and answers
student questions with an AI-backed Q&A bot — all behind a React admin dashboard.

# Test Commit

## What it does

- **Student verification** — students sign in with ASU CAS and link their Discord
  account via OAuth; verified members are granted Discord roles automatically
  (`asu_discord/cogs/verification.py`, `routes/cas.py`, `routes/discord.py`).
- **Salesforce sync** — verified users' ASURITE IDs are matched against Salesforce
  to pull enrollment/opportunity data and keep role assignments accurate
  (`asu_discord/salesforce.py`, `utils/salesforce.py`).
- **Support tickets** — a Discord-based ticketing system (categories, transcripts,
  attachments) manageable from the admin dashboard (`asu_discord/cogs/ticketing.py`).
- **Server analytics** — messages, voice sessions, forum activity, moderation
  events, and scheduled-event attendance are logged for reporting
  (`asu_discord/cogs/analytics.py`, `asu_discord/cogs/event_tracker.py`).
- **Q&A bot ("Forkman")** — answers student questions in the Gold Guide forum using
  an AWS Bedrock (Claude) knowledge base (`asu_discord/cogs/qna.py`,
  `asu_discord/cogs/forklift_qna.py`).
- **Admin dashboard** — a React (Vite + ASU Unity theme) SPA for managing
  verification exceptions, membership charts, tickets, automations, and analytics
  exports, served from `asu-unity-react/` and backed by `routes/admin.py`.
- **Scheduled jobs** — a lightweight cron manager (`cron/`) that, for example,
  uploads verified-user emails to SFTP and syncs departed users to Google Sheets.

## Project layout

```
main.py                 Flask app entrypoint; wires up blueprints, DB, cron, bot
asu_discord/             Discord bot (py-cord) and cogs
routes/                  Flask blueprints (admin, discord OAuth, CAS)
services/                External integrations (Google Sheets)
clients/                 External clients (SFTP)
cron/                    Background job scheduler
utils/                   Settings, database models, Salesforce client
scripts/                 One-off/admin CLI scripts (backfills, lookups, reports)
config/verification.yaml Verification role/eligibility config
asu-unity-react/         Admin dashboard frontend (React + Vite)
tests/                   Pytest suite
```

## Getting started

### Requirements

- Python 3.11+
- Node.js (for the admin dashboard)
- A Discord application/bot, and (optionally) ASU CAS, Salesforce, SFTP, and
  Google Sheets credentials for the integrations you want to enable

### Backend setup

```bash
pip install -r requirements.txt
cp .env.example .env   # fill in the values you need
python main.py
```

The app reads configuration entirely from environment variables — see
`.env.example` for the full list (Flask session settings, database URL, CAS,
Discord OAuth/bot, Salesforce, SFTP, and Google Sheets). Most integrations are
optional and no-op when their credentials are left unset.

### Frontend setup

```bash
cd asu-unity-react
npm install
npm run build   # or `npm run dev` for local development
```

`main.py` serves the built SPA from `asu-unity-react/dist` (override with
`REACT_BUILD_DIR`).

### Docker

```bash
docker compose up --build
```

See `docker-compose.yml` for the `forklift` service (web app + bot) and the
`lookup-members` one-off tool profile.

## Testing

```bash
pytest
```

## Contributing

Contributions are welcome — please open a pull request against `master`.
