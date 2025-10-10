from typing import Optional
import discord
from discord import app_commands
from discord.ext import commands
from core.config import HENRIK_BASE, TIERS_DIR
from core.http import http_get
from core.store import get_alias, get_link, store_match_batch
from core.utils import check_cooldown, q, tier_key, trunc2

async def fetch_matches(region: str, name: str, tag: str, *, mode: Optional[str], size: int) -> dict:
    # mode 공란이면 competitive
    params = {"mode": mode.strip() if mode and mode.strip() else "competitive", "size": str(max(1, min(10, size)))}
    url = f"{HENRIK_BASE}/v3/matches/{region}/{q(name)}/{q(tag)}"
    return await http_get(url, params=params)

class SummaryCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    def _resolve_target(self, user_id: int) -> Optional[tuple[str, str, str]]:
        info = get_link(user_id)
        if not info:
            return None
        return info["name"], info["tag"], info.get("region", "ap")

    @app_commands.command(name="vsummary", description="Recent summary (tier image / WR / KD / comment)")
    @app_commands.describe(
        count="1~10, empty=10",
        target="Registered alias to inspect (empty = your linked account)",
    )
    async def vsummary(self, inter: discord.Interaction, count: Optional[int] = None, target: Optional[str] = None):
        if count is None:
            count = 10
        count = max(1, min(10, count))
        if remain := check_cooldown(inter.user.id):
            await inter.response.send_message(f"Retry later. {remain}s left", ephemeral=True)
            return

        alias_input = (target or "").strip() if target else ""
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
            resolved = self._resolve_target(inter.user.id)
            if resolved is None:
                await inter.response.send_message("not linking", ephemeral=True)
                return
            name, tag, region = resolved
        await inter.response.defer()
        try:

            acc = await http_get(f"{HENRIK_BASE}/v1/account/{q(name)}/{q(tag)}")
            puuid = (acc.get("data") or {}).get("puuid")
            if not puuid:
                raise RuntimeError("Puuid missing in HenrikDev response")

            mmr = await http_get(f"{HENRIK_BASE}/v2/mmr/{region}/{q(name)}/{q(tag)}")
            cur = (mmr.get("data") or {}).get("current_data") or {}
            tier_name = cur.get("currenttierpatched") or "Unrated"
            rr = cur.get("ranking_in_tier", 0)

            js = await fetch_matches(region, name, tag, mode=None, size=count)
            matches = (js.get("data") or [])
            if not matches:
                await inter.followup.send("No recent matches.")
                return

            wins = losses = 0
            tot_k = tot_d = 0
            for m in matches:
                players = ((m.get("players") or {}).get("all_players") or [])
                me = next((p for p in players if p.get("puuid") == puuid), None)
                if not me:
                    continue
                s = me.get("stats") or {}
                k, d = s.get("kills", 0), s.get("deaths", 0)
                tot_k += k; tot_d += d
                team = me.get("team")
                if team and isinstance(m.get("teams"), dict):
                    wins += 1 if m["teams"].get(team, {}).get("has_won") else 0
                    losses += 0 if m["teams"].get(team, {}).get("has_won") else 1

            total = wins + losses
            winrate = (wins/total*100) if total else 0
            kd = trunc2(tot_k/tot_d) if tot_d else float(tot_k)

            try:
                store_match_batch(owner_key, puuid, matches)
            except Exception as store_err:
                import logging
                logging.getLogger(__name__).warning("Failed to persist match cache: %s", store_err, exc_info=True)

            if winrate >= 50 and kd >= 1: msg = "오~ 좀 잘하는데"
            elif winrate >= 50 and kd < 1: msg = "오~ 버스 잘 타는데"
            elif winrate <= 45 and kd >= 1: msg = "이걸 지고 있네 ㅋㅋㅋㅋ"
            elif winrate <= 45 and kd < 1: msg = "개못하네 ㅋㅋㅋ 지는 이유가 있다"
            else: msg = ""

            color = discord.Color.from_rgb(46, 204, 113) if winrate >= 55 else (
                    discord.Color.from_rgb(241, 196, 15) if winrate >= 45 else
                    discord.Color.from_rgb(231, 76, 60))

            desc = (
                f"**{name}** recent **{total}**: **{wins}W {losses}L** (**{winrate:.0f}%**)\n"
                f"**KD : {kd:.2f}**\n"
                f"**{msg}**" if msg else
                f"**{name}** recent **{total}**: **{wins}W {losses}L** (**{winrate:.0f}%**)\n"
                f"**KD : {kd:.2f}**"
            )
            diff_block = f"\n```diff\n+ W {wins}\n- L {losses}\n```"

            embed = discord.Embed(title=f"{tier_name} {rr}RR", description=desc + diff_block, color=color)

            img = TIERS_DIR / (tier_key(tier_name) + ".png")
            if img.exists():
                file = discord.File(img, filename=img.name)
                embed.set_thumbnail(url=f"attachment://{img.name}")
                await inter.followup.send(embed=embed, file=file)
            else:
                await inter.followup.send(embed=embed)

        except Exception as e:
            msg = str(e) or e.__class__.__name__
            await inter.followup.send(f"Error: {msg}")

async def setup(bot: commands.Bot):
    await bot.add_cog(SummaryCog(bot))
