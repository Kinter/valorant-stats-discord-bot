import logging
from typing import List, Optional

import discord
from discord import app_commands
from discord.app_commands import locale_str
from discord.ext import commands

from core.config import HENRIK_BASE
from core.http import http_get
from core.store import get_alias, search_aliases, store_match_batch
from core.utils import (
    alias_display,
    check_cooldown,
    clean_text,
    format_exception_message,
    is_account_not_found_error,
    q,
)


class MatchesCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    vmatches_count_desc = locale_str(
        "Number of matches to fetch (1-10)", ko="조회할 경기 수 (1~10)"
    )
    vmatches_mode_desc = locale_str("Game mode filter", ko="게임 모드 필터")
    vmatches_map_desc = locale_str("Map filter", ko="맵 필터")
    vmatches_target_desc = locale_str(
        "Registered alias to inspect", ko="조회할 등록 별명"
    )

    @app_commands.command(
        name="최근경기",
        description="지도, 모드, 승패, K/D/A로 최근 경기를 확인합니다.",
    )
    @app_commands.describe(
        count=vmatches_count_desc,
        mode=vmatches_mode_desc,
        map=vmatches_map_desc,
        target=vmatches_target_desc,
    )
    async def vmatches(
        self,
        inter: discord.Interaction,
        count: int = 5,
        mode: Optional[str] = None,
        map: Optional[str] = None,
        target: Optional[str] = None,
    ) -> None:
        if remain := check_cooldown(inter.user.id):
            await inter.response.send_message(
                f"잠시 후에 다시 시도해 주세요. 남은 시간: {remain}초", ephemeral=True
            )
            return

        count = max(1, min(10, count))

        alias_input = clean_text(target)
        if not alias_input:
            await inter.response.send_message(
                "별명을 입력해 주세요. 먼저 `/register` 명령으로 Riot ID를 등록할 수 있습니다.",
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

            js = await http_get(
                f"{HENRIK_BASE}/v3/matches/{region}/{q(name)}/{q(tag)}",
                params=params,
            )
            matches = js.get("data") or []
            if not matches:
                await inter.followup.send("최근 경기 기록이 없습니다.")
                return

            try:
                store_match_batch(owner_key, puuid, matches)
            except Exception as store_err:
                logging.getLogger(__name__).warning(
                    "Failed to persist match cache: %s", store_err, exc_info=True
                )

            lines = []
            for match in matches:
                metadata = match.get("metadata", {}) or {}
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
                    has_won = (match["teams"].get(team) or {}).get("has_won")
                    if has_won is True:
                        result = "승"
                    elif has_won is False:
                        result = "패"

                lines.append(f"{map_name} / {mode_name} · {result} · {k}/{d}/{a}")

            body = "**최근 경기 요약**\n" + "\n".join(f"- {line}" for line in lines)
            await inter.followup.send(body)
        except Exception as e:
            if is_account_not_found_error(e):
                await inter.followup.send(
                    "계정을 찾을 수 없습니다. Riot ID 이름과 태그를 확인해 주세요.",
                    ephemeral=True,
                )
            else:
                err = format_exception_message(e)
                await inter.followup.send(
                    f"오류가 발생했습니다: {err}", ephemeral=True
                )

    def _alias_choices(
        self, query: Optional[str]
    ) -> List[app_commands.Choice[str]]:
        records = search_aliases(query, limit=25)
        return [
            app_commands.Choice(name=alias_display(rec), value=rec["alias"])
            for rec in records
        ]

    @vmatches.autocomplete("target")
    async def vmatches_target_autocomplete(
        self, inter: discord.Interaction, current: str
    ):
        return self._alias_choices(current)


async def setup(bot: commands.Bot):
    await bot.add_cog(MatchesCog(bot))
