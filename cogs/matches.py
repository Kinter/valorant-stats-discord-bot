import discord
from discord import app_commands
from discord.ext import commands
from typing import Optional
from core.utils import check_cooldown, q
from core.http import http_get
from core.store import get_link
from core.config import HENRIK_BASE

class MatchesCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    def _resolve_target(self, user_id: int):
        info = get_link(user_id)
        if not info:
            raise RuntimeError("No linked Riot ID. Use /link first.")
        return info["name"], info["tag"], info.get("region", "ap")

    @app_commands.command(name="vmatches", description="Recent matches with K/D/A summary")
    @app_commands.describe(count="Number of matches (1–10)", mode="Game mode filter", map="Map filter")
    async def vmatches(self, inter: discord.Interaction, count: int = 5, mode: Optional[str] = None, map: Optional[str] = None):
        if remain := check_cooldown(inter.user.id):
            await inter.response.send_message(f"Retry later. {remain}s left", ephemeral=True)
            return

        await inter.response.defer()
        try:
            name, tag, region = self._resolve_target(inter.user.id)
            acc = await http_get(f"{HENRIK_BASE}/v1/account/{q(name)}/{q(tag)}")
            puuid = (acc.get("data") or {}).get("puuid")
            params = {"size": str(max(1, min(10, count)))}
            if mode: params["mode"] = mode
            if map: params["map"] = map

            js = await http_get(f"{HENRIK_BASE}/v3/matches/{region}/{q(name)}/{q(tag)}", params=params)
            matches = (js.get("data") or [])
            if not matches:
                await inter.followup.send("No recent matches.")
                return

            lines = []
            for m in matches:
                meta = m.get("metadata", {})
                mapn = meta.get("map", "?")
                modep = meta.get("mode", "?")

                my = next((p for p in (m.get("players", {}).get("all_players") or []) if p.get("puuid") == puuid), None)
                stats = (my or {}).get("stats", {})
                k, d, a = stats.get("kills", 0), stats.get("deaths", 0), stats.get("assists", 0)

                team = my.get("team") if my else None
                res = "—"
                if team and isinstance(m.get("teams"), dict):
                    res = "Win" if m["teams"].get(team, {}).get("has_won") else "Lose"

                lines.append(f"{mapn} / {modep} • {res} • {k}/{d}/{a}")

            await inter.followup.send("**Recent Matches**\n" + "\n".join(f"- {t}" for t in lines))

        except Exception as e:
            await inter.followup.send(f"Error: {e}")

async def setup(bot: commands.Bot):
    await bot.add_cog(MatchesCog(bot))
