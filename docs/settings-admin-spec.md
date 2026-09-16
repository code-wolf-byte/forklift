# Admin Settings Editor — Spec

> **Status: implemented** (phases 1–4). Phase 5, pointing the standalone
> scripts at the accessor, is still open — see §8.

Make the channel IDs, role IDs, and term codes that are currently frozen in `.env`,
`config/verification.yaml`, and Python source editable from the admin dashboard.

**Out of scope:** message/voice analytics channel scope (server-wide by design),
secrets (bot token, Salesforce creds, AWS keys), SFTP/Sheets config, a general
`.env` editor.

---

## 1. Inventory

Every setting this feature covers, with its current home and every consumer.

### Verification

| Key | Type | Today | Consumers |
|---|---|---|---|
| `verification_enabled` | bool | *(new — no prior equivalent)* | `api.assign_verified_role`, `api.assign_roles_from_profile` |

Off means the CAS and Discord OAuth routes run unchanged and still record the
member, but both grant paths return early: no verified role, no unverified-role
removal, and no Salesforce-derived roles. They return rather than raise, because
the OAuth callback turns a `DiscordAPIError` into a 502.

Both gates sit in `asu_discord/api.py` — the boundary the web flow calls. The
`/verify` and whitelist slash commands reach the cog directly and are deliberately
**not** gated: a moderator running one is an explicit override. Removal and refresh
(`remove_verified_role`, `refresh_roles_from_profile`) are likewise ungated, so
cleanup and the nightly Salesforce re-sync keep working while the switch is off.

### Channels

| Key | Today | Consumers |
|---|---|---|
| `qna_forum_channel_id` | env `QNA_FORUM_CHANNEL_ID` → `utils/settings.py:77` | `qna.py:58,81,102,113,122,291,439`; `analytics.py:522,549`; `scripts/backfill_qna.py:272` |

`CronJobConfig.channel_id` (`utils/database.py:190`) is **already editable** in the
Automations tab and stays there. Nothing to move.

### Roles

| Key | Type | Today | Consumers |
|---|---|---|---|
| `verified_role_id` | snowflake | env `DISCORD_VERIFIED_ROLE_ID` (required, `utils/settings.py` `DiscordConfig.from_env`) | `bot.py:61` → `verification.py:252,267` |
| `unverified_role_id` | snowflake | env `DISCORD_UNVERIFIED_ROLE_ID`, **falls back to literal `1207441184218161182`** at `verification.py:248` | `bot.py:49-64`, `verification.py:282` |
| `gold_guide_role_id` | snowflake | **hardcoded twice**: `qna.py:26`, `analytics.py:40` (`1187156709597270157`) | `qna.py:296,521`; `analytics.py:103` |
| `qna_helper_role_id` | snowflake | env `QNA_HELPER_ROLE_ID` | `qna.py:59,546-548` |
| `admin_restricted_role_ids` | list | `config/verification.yaml` `admin.restricted_role_ids` | `routes/admin.py:41-44,113`; `routes/discord.py:13-16` |
| `role_id_map` | dict[name → snowflake] | **hardcoded, 31 entries**: `asu_discord/roles.py:12` | `verification.py:19,344,529,543,575,610,642,672-683,695` (10 sites) |

`role_id_map` is duplicated by copy-paste in `scripts/get_studet_data.py:14-53` and
`scripts/strip_unverified.py:11+` — those drift silently today.

### Terms

| Key | Type | Today | Consumers |
|---|---|---|---|
| `target_term_code` | str, 4 digits | `config/verification.yaml` `verification.target_term_code` → `verification.py:67` | `verification.py:151,176` |
| `active_term_codes` | list[str] | **hardcoded `{"2267","2261"}` in 3 places**: `asu_discord/salesforce.py:97`, `utils/salesforce.py:287`, `scripts/international_stats.py:82` | `salesforce.py:141`, `utils/salesforce.py:324` |

These are the values that change on a human calendar and currently need a redeploy.

---

## 2. Data model

One table, one accessor. Values are JSON text so scalars, lists, and the role map
all use the same path.

```python
# utils/database.py — alongside CronJobConfig
class AppSetting(Base):
    """Admin-editable runtime settings. Absent key = fall back to code default."""
    __tablename__ = "app_settings"

    key = Column(String(64), primary_key=True)
    value = Column(Text, nullable=False)          # JSON-encoded
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    updated_by = Column(String(64), nullable=True)  # discord_user_id
```

`init_db()` already calls `Base.metadata.create_all` (`utils/database.py:386`), so the
table appears on next boot. **No seed rows, no `_ensure_*_columns` migration.**

**Precedence: DB row → env var → hardcoded default.** The existing constants stay in
code as the default layer. An empty `app_settings` table means today's behavior,
exactly. That is what makes this safe to ship in one go.

---

## 3. Accessor

New `utils/app_settings.py`:

```python
_DEFAULTS = {
    "qna_forum_channel_id":      CONFIG.QNA_FORUM_CHANNEL_ID,
    "verified_role_id":          DISCORD_CONFIG.verified_role_id if DISCORD_CONFIG else None,
    "unverified_role_id":        (DISCORD_CONFIG.unverified_role_id if DISCORD_CONFIG else None) or "1207441184218161182",
    "gold_guide_role_id":        "1187156709597270157",
    "qna_helper_role_id":        CONFIG.QNA_HELPER_ROLE_ID,
    "admin_restricted_role_ids": _yaml_admin_roles(),      # current verification.yaml read
    "role_id_map":               DEFAULT_ROLE_ID_MAP,      # renamed from roles.py ROLE_ID_MAP
    "target_term_code":          _yaml_term_code(),        # current verification.yaml read
    "active_term_codes":         ["2267", "2261"],
}

def get(key):            # DB → default, 30s TTL cache of the whole table
def get_all():           # {key: {value, default, is_overridden, updated_at, updated_by}}
def set_many(updates, *, updated_by):   # validates, writes, clears cache
```

**Cache:** one module dict + one timestamp, 30s TTL. Gunicorn runs a single process
with `--worker-class gthread --threads 4` (`Dockerfile:63`) and the bot lives in a
thread of that same process (`main.py:77`), so one cache covers everything. TTL rather
than explicit invalidation so it stays correct if workers are ever scaled.

`ponytail: 30s TTL, whole-table read. Per-key invalidation only if the table grows past a few dozen rows.`

---

## 4. Call-site migration

This is the bulk of the diff: import-time constants become call-time lookups.

| File:line | Now | After |
|---|---|---|
| `asu_discord/roles.py:12` | `ROLE_ID_MAP: Dict[str,int]` | rename to `DEFAULT_ROLE_ID_MAP`; add `def role_id_map() -> dict[str,int]` returning the setting |
| `verification.py` ×10 sites | `ROLE_ID_MAP[...]` / `.get()` / `.values()` | `role_id_map()` — hoist to one local per function, not per loop iteration |
| `verification.py:67` | `TARGET_TERM_CODE` module constant | drop the constant; read inside `_is_enrolled_or_admitted` and its sibling (`:151`, `:176`) |
| `verification.py:248` | `unverified_role_id=1207441184218161182` param default | delete the literal; `_unverified_role` (`:282`) reads the setting |
| `verification.py:267` | `self.verified_role_id` (ctor, from env) | `_verified_role` reads the setting |
| `bot.py:49-64` | parses role IDs into cog kwargs | keep kwargs as the boot-time default only; cogs prefer the setting |
| `qna.py:26`, `analytics.py:40` | two `GOLD_GUIDE_ROLE_ID` literals | delete both; read at `qna.py:296,521` and `analytics.py:103` |
| `qna.py:58-59` | `self.forum_channel_id` / `self.helper_role_id` set in `__init__` | make them `@property` reading the setting — this is what removes the bot restart |
| `analytics.py:522-524` | `getattr(qna_cog, "forum_channel_id", None)` | unchanged; picks up the new property for free |
| `routes/admin.py:41-44` | `_ADMIN_RESTRICTED_ROLE_IDS` module constant | read at `:113` |
| `routes/discord.py:13-16` | same yaml read | read at its use site |
| `salesforce.py:97,141` + `utils/salesforce.py:287,324` | `TARGET_TERM_CODES` frozen set | `set(settings.get("active_term_codes"))` inside the filter |

**Breaks a test:** `tests/test_verification_roles.py:8,23-27` imports `TARGET_TERM_CODE`
and asserts it equals `"2267"`. Update it to call the accessor.

**Leave alone:** `MEMBER_ROLE_CATEGORIES` (`routes/admin.py:432`) is a display grouping,
not IDs. But it lists role *names* that must exist in `role_id_map` — cover that with an
assert (§7), since it's already out of sync (missing `Commited`, `College of Health Solutions`).

---

## 5. API

All `@require_full_admin` — officers must not edit settings.

| Endpoint | Behavior |
|---|---|
| `GET /api/admin/settings` | `get_all()` — value, default, `is_overridden`, `updated_at`, `updated_by` per key |
| `PUT /api/admin/settings` | partial `{key: value}`; `null` value deletes the row (reset to default); validates before writing; returns the new `get_all()` |
| `GET /api/admin/discord-roles` | **new** in `asu_discord/api.py`, mirroring `get_guild_channels` (`api.py:188-215`): REST `GET /guilds/{id}/roles`, drop `@everyone` and `managed` roles, sort by `position` desc, return `{id, name, color}` |

**Gotcha:** `get_guild_channels` filters to `_DISCORD_TEXT_CHANNEL_TYPES = {0, 5}`
(`api.py:185`). The QnA forum is type **15** (`GUILD_FORUM`) and therefore **does not
appear** in the existing dropdown. Add 15 and return `type` in each dict so the UI can
filter — do not widen the set silently, the Automations channel picker must stay
text-only.

### Validation (reject with 400, name the offending key)

- Snowflake: digits only, 17–20 chars.
- `target_term_code`: exactly 4 digits. `active_term_codes`: non-empty list of same.
- `role_id_map`: keys must equal the known default key set (reject unknown; allow a key to be blanked); all values valid snowflakes.
- **Existence check:** every role/channel ID must appear in the live guild roles/channels fetch before the write is accepted. This is the guard that stops a typo silently disabling verification.
- Audit `updated_by` from `session["verification_state"]["discord_user_id"]`.

---

## 6. Frontend

`asu-unity-react/src/pages/admin/Settings.jsx`, registered in `Admin.jsx`:
`NAV` "System" group (`Admin.jsx:52-56`) with `fa-sliders-h`, plus a case in
`renderView` (`Admin.jsx:126-141`). Gate the nav entry on `adminUser.is_admin` — the
sidebar currently shows every item to officers too.

Reuse the `Automations.jsx` pattern verbatim: `edits`/`saving`/`errors` state maps,
shadcn `Select` fed by a fetched list, one Save button per section.

| Section | Fields |
|---|---|
| Channels | `qna_forum_channel_id` — Select over forum-type channels |
| Roles | `verified_role_id`, `unverified_role_id`, `gold_guide_role_id`, `qna_helper_role_id` — Select over guild roles |
| Access | `admin_restricted_role_ids` — multi-select |
| Role Mapping | table of the 31 `role_id_map` entries, name → role Select, grouped by the `MEMBER_ROLE_CATEGORIES` headings |
| Terms | `target_term_code` text input, `active_term_codes` chip list |

Each field shows "default" vs "overridden" and a Reset link (PUT `null`).

### UI warnings (static copy, no logic)

- Changing `verified_role_id` does **not** retro-assign — members already verified keep the old role.
- Changing `role_id_map` takes effect on the next verification or the next `refresh_salesforce_roles` run; it does not re-sync existing members.
- Changing `qna_forum_channel_id` does not re-key existing `qna_posts` history.
- `admin_restricted_role_ids` only controls officer tier; full admins come from `users.is_admin` in the DB, so a bad value cannot lock out real admins.

---

## 7. Test

One file, `tests/test_app_settings.py`, asserting:

1. Empty table → every `get()` returns today's constant (the no-op guarantee).
2. A DB row overrides the default; `null` write restores it.
3. Invalid snowflake / 3-digit term code / unknown `role_id_map` key → rejected.
4. Every name in `MEMBER_ROLE_CATEGORIES` exists in the default `role_id_map`. *(Passes — the drift
   runs the other way: `Commited` and `College of Health Solutions` are mapped but uncategorised,
   which the subset assert allows.)*

Plus the `tests/test_verification_roles.py` update from §4.

---

## 8. Phasing

1. `AppSetting` table + `utils/app_settings.py` + defaults + tests. No behavior change, mergeable alone.
2. Migrate the call sites in §4. Still no UI; settings are DB-editable by hand.
3. `GET/PUT /api/admin/settings`, `get_guild_roles`, forum channel type fix.
4. `Settings.jsx`.
5. Optional cleanup: point `scripts/get_studet_data.py`, `strip_unverified.py`, `international_stats.py` at the accessor instead of their private copies.

Phases 1–2 are the real work and carry the risk; 3–4 are mechanical.

## 9. Deliberately skipped

- Setting history / rollback — `updated_at` + `updated_by` is enough to ask someone what they did.
- Alembic — the repo uses `create_all` + `_ensure_*_columns`; a new table needs neither.
- Live cog reload on save — the 30s TTL plus call-time reads makes it unnecessary.
- Editing secrets or infra config from the browser.
