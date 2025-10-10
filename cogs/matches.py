import logging
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from core.config import HENRIK_BASE
from core.http import http_get
from core.store import get_alias, get_link, store_match_batch
from core.utils import check_cooldown, clean_text, q


class MatchesCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    def _resolve_self(self, user_id: int) -> Optional[tuple[str, str, str]]:
        info = get_link(user_id)
        if not info:
            return None
        return info["name"], info["tag"], info.get("region", "ap")

    @app_commands.command(name="vmatches", description="Recent matches with K/D/A summary")
    @app_commands.describe(
        count="Number of matches (1~10)",
        mode="Game mode filter",
        map="Map filter",
        target="Registered alias to inspect (empty = your linked account)",
    )
    async def vmatches(
        self,
        inter: discord.Interaction,
        count: int = 5,
        mode: Optional[str] = None,
        map: Optional[str] = None,
        target: Optional[str] = None,
    ):
        if remain := check_cooldown(inter.user.id):
            await inter.response.send_message(f"Retry later. {remain}s left", ephemeral=True)
            return

        count = max(1, min(10, count))

        alias_input = clean_text(target)
        owner_key = f"user:{inter.user.id}"
        if alias_input:
            alias_info = get_alias(alias_input)
            if not alias_info:
                await inter.response.send_message(f"Alias `{alias_input}` not found.", ephemeral=True)
                return
            name = alias_info["name"]
            tag = alias_info["tag"]
            region = alias_info.get("region", "ap")
            owner_key = f"alias:{alias_info['alias_norm']}"
        else:
            resolved = self._resolve_self(inter.user.id)
            if resolved is None:
                await inter.response.send_message("not linking", ephemeral=True)
                return
            name, tag, region = resolved

        mode = clean_text(mode)
        map = clean_text(map)

        await inter.response.defer()
        try:
            acc = await http_get(f"{HENRIK_BASE}/v1/account/{q(name)}/{q(tag)}")
            puuid = (acc.get("data") or {}).get("puuid")
            if not puuid:
                raise RuntimeError("Puuid missing in HenrikDev response")

            params = {"size": str(count)}
            if mode:
                params["mode"] = mode
            if map:
                params["map"] = map

            js = await http_get(f"{HENRIK_BASE}/v3/matches/{region}/{q(name)}/{q(tag)}", params=params)
            matches = (js.get("data") or [])
            if not matches:
                await inter.followup.send("No recent matches.")
                return

            try:
                store_match_batch(owner_key, puuid, matches)
            except Exception as store_err:
                logging.getLogger(__name__).warning("Failed to persist match cache: %s", store_err, exc_info=True)

            lines = []
            for match in matches:
                metadata = match.get("metadata", {})
                map_name = metadata.get("map", "?")
                mode_name = metadata.get("mode", "?")

                all_players = (match.get("players") or {}).get("all_players") or []
                me = next((p for p in all_players if p.get("puuid") == puuid), None)
                stats = (me or {}).get("stats") or {}
                k = stats.get("kills", 0)
                d = stats.get("deaths", 0)
                a = stats.get("assists", 0)

                result = "?"
                team = me.get("team") if me else None
                if team and isinstance(match.get("teams"), dict):
                    result = "Win" if match["teams"].get(team, {}).get("has_won") else "Lose"

                lines.append(f"{map_name} / {mode_name} · {result} · {k}/{d}/{a}")

            await inter.followup.send("**Recent Matches**\n" + "\n".join(f"- {line}" for line in lines))
        except Exception as e:
            await inter.followup.send(f"Error: {e}")


async def setup(bot: commands.Bot):
    await bot.add_cog(MatchesCog(bot))
