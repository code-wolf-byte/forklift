import discord
import logging
import asyncio
import os
from typing import Iterable

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

ROLE_ID_MAP = {
    "First Generation Student": 1210322592544596030,
    "International Student": 1187457897966338129,
    "First Year": 1187164746454138900,
    "Transfer Student": 1187164763189416078,
    "Graduate Student": 1187164940923060284,
    "Upperclassmen": 1205549707938766878,
    "Barrett The Honors College": 1187459588287635466,
    "Ira A. Fulton Schools of Engineering": 1187460517422444676,
    "College of Liberal Arts and Sciences": 1187460910936232099,
    "College of Global Futures": 1187459643304312852,
    "Edson College of Nursing and Health Innovation": 1187460135434588322,
    "Herberger Institute for Design and the Arts": 1187460355618779316,
    "Thunderbird School of Global Management": 1187460980247117865,
    "Mary Lou Fulton Teachers College": 1187460649798881432,
    "New College of Interdisciplinary Arts and Sciences": 1187460740316151831,
    "College of Integrative Sciences and Arts": 1187459946552492112,
    "W.P. Carey School of Business": 1187461362356605039,
    "Walter Cronkite School of Journalism and Mass Communication": 1187461060320571442,
    "Watts College of Public Service and Community Solutions": 1187461173533233192,
    "University College": 1263595373058981898,
    "Tempe": 1282464973255348366,
    "Downtown Phoenix": 1282465059431252051,
    "Polytechnic": 1282465090808971397,
    "LA Center": 1282501414433849378,
    "West Valley": 1282465131749576704,
    "Online": 1465991804993278113,
}

GUILD_ID = 1187144343400751234
UNVERIFIED_ROLE_ID = 1207441184218161182
TOKEN = os.environ.get("DISCORD_BOT_TOKEN")


async def _remove_role_with_retry(
    member: discord.Member,
    role: discord.Role,
    *,
    reason: str,
) -> None:
    try:
        await member.remove_roles(role, reason=reason)
        return
    except discord.HTTPException as exc:
        retry_after = getattr(exc, "retry_after", None)
        if retry_after is not None:
            await asyncio.sleep(float(retry_after))
            await member.remove_roles(role, reason=reason)
            return
        raise


async def main():
    if not TOKEN:
        raise SystemExit("DISCORD_BOT_TOKEN is not set in the environment.")
    intents = discord.Intents.all()
    client = discord.Client(intents=intents)

    @client.event
    async def on_ready():
        logger.info("Logged in as %s (ID: %s)", client.user, client.user.id)
        logger.info("------" * 5)
        try:
            guild = client.get_guild(GUILD_ID)
            if guild is None:
                logger.error("Guild %s not found", GUILD_ID)
                return
            await guild.chunk()
            unverified_role = guild.get_role(UNVERIFIED_ROLE_ID)
            if unverified_role is None:
                logger.error("Unverified role %s not found", UNVERIFIED_ROLE_ID)
                return
            target_role_ids = set(ROLE_ID_MAP.values())

            for member in guild.members:
                if unverified_role not in member.roles:
                    continue
                for role in member.roles:
                    if role.id not in target_role_ids:
                        continue
                    try:
                        await _remove_role_with_retry(
                            member, role, reason="Strip roles from unverified users"
                        )
                        logger.info("Removed %s from %s", role.name, member.name)
                        await asyncio.sleep(0.5)
                        break
                    except Exception as exc:
                        logger.error(
                            "Failed to remove %s from %s: %s",
                            role.name,
                            member.name,
                            exc,
                        )
        finally:
            await client.close()

    await client.start(TOKEN)


if __name__ == "__main__":
    asyncio.run(main())
