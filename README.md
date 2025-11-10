## Devils to Devils Verification

This Flask app links an ASU SSO session with a Discord account so admitted or
current students can join the Devils to Devils community with the verified role.
The HTML template mirrors the public ASU site while exposing states for new,
ASU-authenticated, and fully verified users.

## Local development

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # update secrets before running
python main.py
```

The server listens on `http://127.0.0.1:8000/`. Adjust values in `.env` to match
your SAML metadata, Discord application, and cookie preferences.

## Required environment variables

```
DISCORD_CLIENT_ID=<Discord application client id>
DISCORD_CLIENT_SECRET=<Discord application client secret>
DISCORD_REDIRECT_URI=https://your-domain/auth/discord/callback
DISCORD_BOT_TOKEN=<Discord bot token with Manage Roles permission>
DISCORD_GUILD_ID=<Target guild snowflake>
DISCORD_VERIFIED_ROLE_ID=<Role snowflake to assign after verification>
FLASK_SECRET_KEY=<random string used for Flask sessions>
DATABASE_URL=sqlite:////absolute/path/to/forklift.db
```

Optional overrides:

```
DISCORD_SCOPE=identify
DISCORD_TEST_GUILD_IDS=1082823852322725888
DISCORD_SUCCESS_REDIRECT=/verified
DISCORD_FAILURE_REDIRECT=/verification-error
SAML_ATTR_ASURITE=uid
SAML_ATTR_EMAIL=mail
SAML_ATTR_FULL_NAME=displayName
SAML_ATTR_FIRST_NAME=givenName
SAML_ATTR_LAST_NAME=sn
SAML_ATTR_AFFILIATIONS=eduPersonAffiliation
SAML_METADATA_PATH=/path/to/sp-metadata.xml
SAML_IDP_METADATA=/path/to/idp-metadata.xml
SAML_METADATA_VALIDITY_DAYS=365
```

## Verification flow

1. `/auth/saml/login` starts ASU SSO and persists key identity attributes at the
   Assertion Consumer Service (`/auth/saml/acs`).
2. On success the browser continues to `/auth/discord/login` for Discord OAuth2
   consent.
3. `/auth/discord/callback` exchanges the authorization code and assigns the
   verified role to members who are already in the guild.
4. The combined record is stored in the `users` table and the session is marked
   complete so the landing page shows the verified state.

## Automated SAML metadata refresh

Expose the generated service-provider metadata at `/saml/metadata`. Schedule the
refresh command so the file regenerates before the `validUntil` timestamp:

```cron
0 0 * * * /path/to/venv/bin/python /path/to/project/utils/metadata.py --refresh-if-expired >> /var/log/forklift_metadata.log 2>&1
```

The CLI only writes a new file when the existing metadata is missing or expired.
Adjust the interpreter path and logging location to match your deployment.

## Discord bot

The project ships with a lightweight Discord bot (powered by [py-cord]) that can
manage verification directly in the guild. Instantiate it with:

```python
from asu_discord import create_bot
from utils.settings import DISCORD_CONFIG

bot = create_bot(command_prefix="!")
bot.run(DISCORD_CONFIG.bot_token)
```

The bot loads a verification cog that exposes `!verify @member` and
`!unverify @member` commands (requires the `Manage Roles` permission) to assign
or remove the configured verification role. Use `/setup_verification` (requires
`Manage Server`) to post the Devils to Devils verification embed and "Verify
Here" button in the current channel. Populate `DISCORD_TEST_GUILD_IDS` (comma-
separated) to register the slash command as a guild command for those IDs so it
appears immediately while testing.

[py-cord]: https://pypi.org/project/py-cord/
