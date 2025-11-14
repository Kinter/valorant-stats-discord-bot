import logging
from typing import List, Optional

import discord
from discord import app_commands
from discord.app_commands import locale_str
from discord.ext import commands

from core.api import fetch_player_info
from core.config import HENRIK_BASE, TIERS_DIR
from core.http import http_get
from core.store import get_alias, search_aliases, store_match_batch
from core.utils import (
    alias_display,
    check_cooldown,
    clean_text,
    format_exception_message,
    is_account_not_found_error,
    q,
    tier_key,
    trunc2,
)


async def fetch_matches(
    region: str, name: str, tag: str, *, mode: Optional[str], size: int
) -> dict:
    params = {
        "mode": mode.strip() if mode and mode.strip() else "competitive",
        "size": str(max(1, min(10, size))),
    }
    url = f"{HENRIK_BASE}/v3/matches/{region}/{q(name)}/{q(tag)}"
    return await http_get(url, params=params)


class SummaryCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    vsummary_count_desc = locale_str(
        "Number of matches (1-10, default 10)", ko="조회할 경기 수 (기본 10)"
    )
    vsummary_target_desc = locale_str(
        "Registered alias to inspect", ko="조회할 별명 선택"
    )

    @app_commands.command(
        name="최근전적요약",
        description="티어, 승률, KD, 코멘트로 최근 활약을 요약합니다.",
    )
    @app_commands.describe(count=vsummary_count_desc, target=vsummary_target_desc)
    async def vsummary(
        self,
        inter: discord.Interaction,
        count: Optional[int] = None,
        target: Optional[str] = None,
    ) -> None:
        count = 10 if count is None else max(1, min(10, count))

        if remain := check_cooldown(inter.user.id):
            await inter.response.send_message(
                f"잠시 후에 다시 시도해 주세요. 남은 시간: {remain}초", ephemeral=True
            )
            return

        alias_input = clean_text(target)
        if not alias_input:
            await inter.response.send_message(
                "별명을 입력해 주세요. 먼저 `/별명등록` 명령으로 Riot ID를 등록할 수 있습니다.",
                ephemeral=True,
            )
            return

        alias_info = get_alias(alias_input)
        if not alias_info:
            await inter.response.send_message(
                f"`{alias_input}` 별명을 찾을 수 없습니다.", ephemeral=True
            )
            return

        name = alias_info["name"]
        tag = alias_info["tag"]
        region = alias_info.get("region", "ap")
        owner_key = f"alias:{alias_info['alias_norm']}"

        await inter.response.defer()
        try:
            info = await fetch_player_info(name, tag, region=region)
            puuid = info["puuid"]
            cur = info.get("current_mmr") or {}
            tier_name = cur.get("currenttierpatched") or "Unrated"
            rr = cur.get("ranking_in_tier", 0)

            js = await fetch_matches(region, name, tag, mode=None, size=count)
            matches = js.get("data") or []
            if not matches:
                await inter.followup.send("최근 경기 기록이 없습니다.")
                return

            wins = losses = 0
            tot_k = tot_d = 0
            for match in matches:
                players = (match.get("players") or {}).get("all_players") or []
                me = next((p for p in players if p.get("puuid") == puuid), None)
                if not me:
                    continue

                stats = me.get("stats") or {}
                k = stats.get("kills", 0)
                d = stats.get("deaths", 0)
                tot_k += k
                tot_d += d

                team = me.get("team")
                if team and isinstance(match.get("teams"), dict):
                    has_won = (match["teams"].get(team) or {}).get("has_won")
                    if has_won:
                        wins += 1
                    else:
                        losses += 1

            total = wins + losses
            winrate = (wins / total * 100) if total else 0
            kd = trunc2(tot_k / tot_d) if tot_d else float(tot_k)

            try:
                store_match_batch(owner_key, puuid, matches)
            except Exception as store_err:
                logging.getLogger(__name__).warning(
                    "Failed to persist match cache: %s", store_err, exc_info=True
                )

            if winrate >= 50 and kd >= 1:
                msg = "오~ 요즘 잘하고 있네"
            elif winrate >= 50 and kd < 1:
                msg = "오~ 승리엔 팀워크가!"
            elif winrate <= 45 and kd >= 1:
                msg = "혼자 고생하는 느낌이야"
            elif winrate <= 45 and kd < 1:
                msg = "연패는 이제 그만...!"
            else:
                msg = ""

            desc = (
                f"**{name}** 최근 경기 **{total}전**: **{wins}승 {losses}패** (**{winrate:.0f}%**)\n"
                f"**KD : {kd:.2f}**"
            )
            if msg:
                desc += f"\n**{msg}**"
            diff_block = f"\n```diff\n+ 승 {wins}\n- 패 {losses}\n```"

            color = (
                discord.Color.from_rgb(46, 204, 113)
                if winrate >= 55
                else discord.Color.from_rgb(241, 196, 15)
                if winrate >= 45
                else discord.Color.from_rgb(231, 76, 60)
            )
            embed = discord.Embed(
                title=f"{tier_name} {rr}RR", description=desc + diff_block, color=color
            )

            img = TIERS_DIR / (tier_key(tier_name) + ".png")
            if img.exists():
                file = discord.File(img, filename=img.name)
                embed.set_thumbnail(url=f"attachment://{img.name}")
                await inter.followup.send(embed=embed, file=file)
            else:
                await inter.followup.send(embed=embed)

        except Exception as e:
            if is_account_not_found_error(e):
                await inter.followup.send(
                    "계정을 찾을 수 없습니다. Riot ID 이름과 태그를 확인해 주세요.",
                    ephemeral=True,
                )
            else:
                msg = format_exception_message(e)
                await inter.followup.send(
                    f"오류가 발생했습니다: {msg}", ephemeral=True
                )

    def _alias_choices(
        self, query: Optional[str]
    ) -> List[app_commands.Choice[str]]:
        records = search_aliases(query, limit=25)
        return [
            app_commands.Choice(name=alias_display(rec), value=rec["alias"])
            for rec in records
        ]

    @vsummary.autocomplete("target")
    async def vsummary_target_autocomplete(
        self, inter: discord.Interaction, current: str
    ):
        return self._alias_choices(current)


async def setup(bot: commands.Bot):
    await bot.add_cog(SummaryCog(bot))
