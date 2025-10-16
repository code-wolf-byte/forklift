## Automated SAML metadata refresh

The application exposes the service provider metadata at `/saml/metadata`. To keep
the file valid, schedule the metadata generator with the refresh flag each night
so the file regenerates when expired:

```cron
0 0 * * * /path/to/venv/bin/python /home/tupreti/Projects/forklift/metadata.py --refresh-if-expired >> /var/log/forklift_metadata.log 2>&1
```

Adjust the Python interpreter path as needed for your deployment. The CLI checks
the `validUntil` attribute in `sp-metadata.xml` and only writes a new file when
the existing metadata is missing or expired.

## Discord + ASU verification flow

1. A user starts at `/auth/saml/login`, completes ASU SSO, and returns to the Assertion Consumer Service at `/auth/saml/acs`. The ACS endpoint persists the SAML identity attributes (ASURITE, email, affiliations, etc.) and primes the verification session.
2. After SAML succeeds the browser is redirected to `/auth/discord/login`, which initiates Discord OAuth2 consent.
3. Discord redirects to `/auth/discord/callback`. The callback exchanges the authorization code, retrieves the Discord profile, joins the user to the configured guild, and assigns the verified role with the bot token.
4. The verification session is marked complete, and the combined record is stored in the `users` table with the SAML metadata, Discord identifiers, and verification status.

## Container image

Build a production image with Gunicorn and xmlsec support:

```bash
docker build -t forklift:latest .
```

Run the container locally while mounting the certs and persistent data folder:

```bash
mkdir -p data certs
cp .env.example .env  # adjust values before running
docker run --rm -p 8000:8000 \
  --env-file .env \
  -v "$(pwd)/certs:/app/certs:ro" \
  -v "$(pwd)/data:/app/data" \
  forklift:latest
```

### docker-compose with Watchtower

The provided `docker-compose.yml` now includes three services:

- `forklift` – the Gunicorn + Flask application.
- `nginx` – a TLS-terminating reverse proxy using the supplied ASU SSO-friendly config.
- `watchtower` – optional auto-updater that tracks both containers via labels.

Before the first launch create the bind-mount directories:

```bash
mkdir -p data certs letsencrypt letsencrypt-webroot webroot
```

Run certbot on the host with `--config-dir "$(pwd)/letsencrypt"` and `--webroot "$(pwd)/letsencrypt-webroot"` (or copy your existing `/etc/letsencrypt` tree) so the containerized Nginx can read the certificates plus `options-ssl-nginx.conf`. When ready, build/run the stack:

```bash
docker compose up -d --build
```

Watchtower only updates services carrying the `watchtower.scope=forklift` label. Adjust the `command` flags if you prefer poll-based or schedule-based updates.

### Required environment variables

```
DISCORD_CLIENT_ID=<Discord application client id>
DISCORD_CLIENT_SECRET=<Discord application client secret>
DISCORD_REDIRECT_URI=https://your-domain/auth/discord/callback
DISCORD_BOT_TOKEN=<Discord bot token with Manage Roles permission>
DISCORD_GUILD_ID=<Target guild snowflake>
DISCORD_VERIFIED_ROLE_ID=<Role snowflake to assign after verification>
FLASK_SECRET_KEY=<random string used for Flask sessions>
DATABASE_URL=sqlite:////app/data/forklift.db    # defaults to the mounted ./data volume
```

Optional overrides:

```
DISCORD_SCOPE=identify guilds.join           # customize OAuth scopes
DISCORD_SUCCESS_REDIRECT=/verified           # relative redirect after success
DISCORD_FAILURE_REDIRECT=/verification-error # relative redirect on failure
SAML_ATTR_ASURITE=uid                        # override ASU attribute mapping
SAML_ATTR_EMAIL=mail
SAML_ATTR_FULL_NAME=displayName
SAML_ATTR_FIRST_NAME=givenName
SAML_ATTR_LAST_NAME=sn
SAML_ATTR_AFFILIATIONS=eduPersonAffiliation
SAML_METADATA_PATH=/app/data/sp-metadata.xml
SAML_IDP_METADATA=/app/data/idp-metadata.xml
```

If you rely on Nginx for TLS termination, keep certbot’s deployment hooks pointed at the `letsencrypt` and `letsencrypt-webroot` directories so the container sees fresh certificates without rebuilds.

### Automating SP certificate deployment

The script `scripts/setup_sp_certs.sh` bootstraps certificate management on the host where certbot runs:

```bash
sudo bash scripts/setup_sp_certs.sh
```

It copies the active `cert.pem`/`privkey.pem` (or `fullchain.pem` if enabled) into the mounted `certs/` directory, installs a certbot deploy hook to repeat the copy after future renewals, and executes

```bash
docker compose exec -T forklift python -m utils.metadata --refresh-if-expired
```

so the service provider metadata is re-signed with the new key automatically. Edit the configuration block at the top of the script to match your server paths, user, and docker-compose command before running it.

The default SAML attribute mapping matches ASU SSO metadata. Adjust the names if
your IdP uses different URIs or friendly names. The Discord bot must be present
in the guild with the `Manage Roles` permission and the verified role must be
below the bot's highest role.
