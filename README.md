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

### Required environment variables

```
DISCORD_CLIENT_ID=<Discord application client id>
DISCORD_CLIENT_SECRET=<Discord application client secret>
DISCORD_REDIRECT_URI=https://your-domain/auth/discord/callback
DISCORD_BOT_TOKEN=<Discord bot token with Manage Roles permission>
DISCORD_GUILD_ID=<Target guild snowflake>
DISCORD_VERIFIED_ROLE_ID=<Role snowflake to assign after verification>
FLASK_SECRET_KEY=<random string used for Flask sessions>
DATABASE_URL=sqlite:////path/to/forklift.db  # optional, defaults to local sqlite file
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
```

The default SAML attribute mapping matches ASU SSO metadata. Adjust the names if
your IdP uses different URIs or friendly names. The Discord bot must be present
in the guild with the `Manage Roles` permission and the verified role must be
below the bot's highest role.
