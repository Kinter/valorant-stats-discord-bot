import asyncio
import logging
from typing import Any, Dict, List, Optional, Tuple

import discord
from discord.ext import commands, tasks

from core.config import HENRIK_BASE
from core.http import http_get
from core.store import (
    list_aliases,
    latest_match,
    store_match_batch,
    list_alert_channels,
)
from core.utils import clean_text, metadata_label, q, team_outcome_from_entry, team_result


log = logging.getLogger(__name__)


def _find_player(
    all_players: List[Dict[str, Any]],
    *,
    puuid: Optional[str],
    name: Optional[str] = None,
    tag: Optional[str] = None,
):
    puuid_norm = clean_text(puuid).lower() if puuid else ""
    if puuid_norm:
        for player in all_players:
            candidate = clean_text(player.get("puuid")).lower()
            if candidate and candidate == puuid_norm:
                return player

    name_norm = clean_text(name).lower()
    tag_norm = clean_text(tag).upper()
    if name_norm and tag_norm:
        for player in all_players:
            player_name = clean_text(
                player.get("game_name")
                or player.get("gameName")
                or player.get("name")
            ).lower()
            player_tag = clean_text(
                player.get("tag_line")
                or player.get("tagLine")
                or player.get("tag")
            ).upper()
            if player_name == name_norm and player_tag == tag_norm:
                return player

    return None


class AlertCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._last_seen: Dict[str, str] = {}
        self._bootstrapped = False
        self.poll_matches.start()

    def cog_unload(self) -> None:
        self.poll_matches.cancel()

    def _bootstrap_last_seen(self) -> None:
        for record in list_aliases():
            owner_key = f"alias:{record['alias_norm']}"
            latest = latest_match(owner_key)
            if latest and latest.get("match_id"):
                self._last_seen[owner_key] = latest["match_id"]
        self._bootstrapped = True
        log.info("[ALERT] Bootstrapped last seen matches for %s aliases", len(self._last_seen))

    @tasks.loop(minutes=5)
    async def poll_matches(self) -> None:
        await self.bot.wait_until_ready()

        if not self._bootstrapped:
            self._bootstrap_last_seen()

        aliases = list_aliases()
        if not aliases:
            return

        for entry in aliases:
            owner_key = f"alias:{entry['alias_norm']}"
            try:
                await self._process_alias(entry, owner_key)
            except Exception:
                log.exception("[ALERT] Failed to process alias %s", owner_key)
            await asyncio.sleep(1)

    async def _process_alias(self, entry: Dict[str, Any], owner_key: str) -> None:
        name = entry["name"]
        tag = entry["tag"]
        region = entry.get("region", "ap")
        puuid = entry.get("puuid")

        params = {"size": "1"}
        data = await http_get(f"{HENRIK_BASE}/v3/matches/{region}/{q(name)}/{q(tag)}", params=params)
        matches = data.get("data") or []
        if not matches:
            return

        match = matches[0]
        match_id = self._match_id(match)
        if not match_id:
            return

        if self._last_seen.get(owner_key) == match_id:
            return

        stored = store_match_batch(owner_key, puuid, [match])
        if stored == 0:
            # store_match_batch returns the number of newly inserted rows; zero means this match was already persisted.
            self._last_seen[owner_key] = match_id
            return

        self._last_seen[owner_key] = match_id
        embed = self._build_embed(entry, match, match_id)
        await self._dispatch_alert(embed)

    def _match_id(self, match: Dict[str, Any]) -> Optional[str]:
        metadata = match.get("metadata") or {}
        return (
            metadata.get("matchid")
            or metadata.get("matchId")
            or metadata.get("matchID")
            or match.get("match_id")
        )

    def _build_embed(self, entry: Dict[str, Any], match: Dict[str, Any], match_id: str) -> discord.Embed:
        metadata = match.get("metadata") or {}
        map_name = metadata_label(metadata, "map")
        mode_name = metadata_label(metadata, "mode")
        started = metadata.get("game_start_patched") or metadata.get("game_start") or "Unknown"
        player_stats, outcome = self._extract_player_stats(entry, match)

        color = discord.Color.from_rgb(149, 165, 166)  # default grey
        result_label = "결과 정보 없음"
        if outcome == "win":
            color = discord.Color.from_rgb(46, 204, 113)
            result_label = "승리"
        elif outcome == "loss":
            color = discord.Color.from_rgb(231, 76, 60)
            result_label = "패배"

        embed = discord.Embed(
            title=f"{entry['alias']} 최신 경기",
            description=f"{map_name} · {mode_name}",
            color=color,
        )
        embed.add_field(name="Riot ID", value=f"{entry['name']}#{entry['tag']}", inline=True)
        embed.add_field(name="결과", value=result_label, inline=True)

        if player_stats:
            k = player_stats.get("kills", 0)
            d = player_stats.get("deaths", 0)
            a = player_stats.get("assists", 0)
            embed.add_field(name="K/D/A", value=f"{k}/{d}/{a}", inline=True)

        rounds = self._round_score(match, outcome)
        if rounds:
            embed.add_field(name="라운드 스코어", value=rounds, inline=True)

        embed.set_footer(text=f"경기 시작: {started}")
        embed.timestamp = discord.utils.utcnow()
        embed.url = f"https://tracker.gg/valorant/match/{match_id}"
        return embed

    def _extract_player_stats(
        self, entry: Dict[str, Any], match: Dict[str, Any]
    ) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
        puuid = entry.get("puuid")
        if not puuid and not entry.get("name"):
            return None, None

        players = (match.get("players") or {}).get("all_players") or []
        me = _find_player(
            players,
            puuid=puuid,
            name=entry.get("name"),
            tag=entry.get("tag"),
        )
        if me is None:
            return None, None

        team = me.get("team")
        outcome = None
        result_flag = team_result(match.get("teams"), team)
        if result_flag is True:
            outcome = "win"
        elif result_flag is False:
            outcome = "loss"

        return me.get("stats") or {}, outcome

    def _round_score(self, match: Dict[str, Any], outcome: Optional[str]) -> Optional[str]:
        teams = match.get("teams")
        if not isinstance(teams, dict):
            return None

        scores: List[str] = []
        for name, info in teams.items():
            if not isinstance(info, dict):
                continue
            rounds_won = info.get("rounds_won")
            if rounds_won is None:
                continue
            has_won = team_outcome_from_entry(info)
            label = name.title()
            if has_won is True:
                label = "우리 팀" if outcome == "win" else "상대 팀"
            elif has_won is False:
                label = "우리 팀" if outcome == "loss" else "상대 팀"
            scores.append(f"{label}: {rounds_won}")
        return "\n".join(scores) if scores else None

    async def _dispatch_alert(self, embed: discord.Embed) -> None:
        targets = list_alert_channels()
        if not targets:
            return

        for entry in targets:
            guild = self.bot.get_guild(entry["guild_id"])
            if not guild:
                continue
            channel = guild.get_channel(entry["channel_id"])
            if channel is None:
                try:
                    channel = await guild.fetch_channel(entry["channel_id"])
                except (discord.Forbidden, discord.HTTPException):
                    continue
            if not isinstance(channel, (discord.TextChannel, discord.Thread)):
                continue
            try:
                await channel.send(embed=embed)
            except discord.HTTPException:
                log.exception(
                    "[ALERT] Failed to send alert to guild=%s channel=%s",
                    entry["guild_id"],
                    entry["channel_id"],
                )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(AlertCog(bot))
