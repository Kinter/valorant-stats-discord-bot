import asyncio
import logging
import time
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands, tasks

from core.config import HENRIK_BASE, TIERS_DIR
from core.http import http_get
from core.store import (
    get_link,
    get_user_data,
    list_links,
    upsert_user_data,
)
from core.utils import check_cooldown, q, tier_key, trunc2

logger = logging.getLogger(__name__)

DEFAULT_MODE = "competitive"
DEFAULT_SAMPLE = 10
CACHE_TTL = 5 * 60

MODE_LABELS = {
    "competitive": "경쟁",
    "unrated": "일반",
    "deathmatch": "데스매치",
}


async def fetch_matches(region: str, name: str, tag: str, *, mode: Optional[str], size: int) -> dict:
    """mode 비었으면 competitive로 기본 적용"""
    params = {
        "mode": mode.strip() if mode and mode.strip() else DEFAULT_MODE,
        "size": str(max(1, min(10, size))),
    }
    url = f"{HENRIK_BASE}/v3/matches/{region}/{q(name)}/{q(tag)}"
    return await http_get(url, params=params)


def _resolve_mode_label(mode: str) -> str:
    return MODE_LABELS.get(mode, mode.capitalize() or MODE_LABELS[DEFAULT_MODE])


def _compute_streak(outcomes: list[Optional[bool]]) -> tuple[str, int]:
    streak_type = "none"
    streak_count = 0
    for result in outcomes:
        if result is None:
            if streak_count > 0:
                break
            continue
        if streak_count == 0:
            streak_type = "win" if result else "loss"
            streak_count = 1
            continue
        if (result and streak_type == "win") or (not result and streak_type == "loss"):
            streak_count += 1
        else:
            break
    return streak_type, streak_count


async def build_summary(
    region: str,
    name: str,
    tag: str,
    *,
    mode: Optional[str],
    size: int,
) -> dict:
    resolved_mode = (mode or "").strip() or DEFAULT_MODE

    acc = await http_get(f"{HENRIK_BASE}/v1/account/{q(name)}/{q(tag)}")
    puuid = (acc.get("data") or {}).get("puuid")
    if not puuid:
        raise RuntimeError("Could not resolve account puuid.")

    mmr = await http_get(f"{HENRIK_BASE}/v2/mmr/{region}/{q(name)}/{q(tag)}")
    cur = (mmr.get("data") or {}).get("current_data") or {}
    tier_name = cur.get("currenttierpatched") or "Unrated"
    rr = cur.get("ranking_in_tier", 0)

    js = await fetch_matches(region, name, tag, mode=resolved_mode, size=size)
    matches = (js.get("data") or [])

    wins = losses = 0
    tot_k = tot_d = 0
    outcomes: list[Optional[bool]] = []

    for match in matches:
        players = ((match.get("players") or {}).get("all_players") or [])
        me = next((p for p in players if p.get("puuid") == puuid), None)
        if not me:
            outcomes.append(None)
            continue

        stats = me.get("stats") or {}
        k, d = stats.get("kills", 0), stats.get("deaths", 0)
        tot_k += k
        tot_d += d

        teams_raw = (match.get("teams") or {})
        teams = {str(k).lower(): v for k, v in teams_raw.items()}
        my_team = (me.get("team") or "").lower()

        has_won = None
        if my_team in teams and isinstance(teams[my_team], dict):
            has_won = teams[my_team].get("has_won")

        if isinstance(has_won, bool):
            if has_won:
                wins += 1
            else:
                losses += 1
            outcomes.append(has_won)
        else:
            outcomes.append(None)

    total = wins + losses
    winrate = (wins / total * 100) if total else 0.0
    kd = trunc2(tot_k / tot_d) if tot_d else float(tot_k)

    if winrate >= 50 and kd >= 1:
        msg = "오~ 좀 잘하는데"
    elif winrate >= 50 and kd < 1:
        msg = "오~ 버스 잘 타는데"
    elif winrate <= 45 and kd >= 1:
        msg = "이걸 지고 있네 ㅋㅋㅋㅋ"
    elif winrate <= 45 and kd < 1:
        msg = "개못하네 ㅋㅋㅋ 지는 이유가 있다"
    else:
        msg = ""

    streak_type, streak_count = _compute_streak(outcomes)

    return {
        "name": name,
        "tag": tag,
        "region": region,
        "tier_name": tier_name,
        "rr": rr,
        "wins": wins,
        "losses": losses,
        "total": total,
        "winrate": winrate,
        "kd": kd,
        "message": msg,
        "mode": resolved_mode,
        "mode_label": _resolve_mode_label(resolved_mode),
        "sample_size": max(1, min(10, size)),
        "matches_found": len(matches),
        "streak": {
            "type": streak_type,
            "count": streak_count,
        },
    }


class SummaryCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        if not self.refresh_userdata.is_running():
            self.refresh_userdata.start()

    def cog_unload(self) -> None:
        if self.refresh_userdata.is_running():
            self.refresh_userdata.cancel()

    def _resolve_target(self, user_id: int) -> tuple[str, str, str]:
        info = get_link(user_id)
        if not info:
            raise RuntimeError("No linked Riot ID. Use /link first.")
        return info["name"], info["tag"], info.get("region", "ap")

    def _load_cached_summary(
        self,
        user_id: int,
        name: str,
        tag: str,
        region: str,
        mode: str,
        sample: int,
    ) -> Optional[dict]:
        cache = get_user_data(user_id)
        if not cache:
            return None

        data = cache.get("data") or {}
        if data.get("name") != name or data.get("tag") != tag or data.get("region") != region:
            return None
        updated_at = cache.get("updated_at") or 0
        if data.get("mode") != mode:
            return None
        if data.get("sample_size") != sample:
            return None
        if (time.time() - updated_at) > CACHE_TTL:
            return None
        return data

    async def _ensure_summary(self, user_id: int, name: str, tag: str, region: str, *, mode: str, sample: int) -> dict:
        cached = self._load_cached_summary(user_id, name, tag, region, mode, sample)
        if cached:
            return cached

        summary = await build_summary(region, name, tag, mode=mode, size=sample)
        upsert_user_data(user_id, summary)
        return summary

    async def _refresh_single_user(self, link: dict) -> None:
        try:
            summary = await build_summary(
                link.get("region", "ap"),
                link["name"],
                link["tag"],
                mode=DEFAULT_MODE,
                size=DEFAULT_SAMPLE,
            )
            upsert_user_data(link["user_id"], summary)
        except Exception:
            logger.exception("Failed to refresh summary for user_id=%s", link.get("user_id"))

    @tasks.loop(minutes=5)
    async def refresh_userdata(self) -> None:
        links = list_links()
        if not links:
            return
        for link in links:
            await self._refresh_single_user(link)
            await asyncio.sleep(1)

    @refresh_userdata.before_loop
    async def before_refresh(self) -> None:
        await self.bot.wait_until_ready()

    # ── 새 입력 필드: gamemode 선택지 추가 ─────────────────────────────
    @app_commands.command(name="vsummary", description="Recent summary (tier image / WR / KD / comment)")
    @app_commands.describe(
        count="1~10 (empty=10)",
        gamemode="게임 모드 선택: 경쟁/일반/데스매치/기타"
    )
    @app_commands.choices(
        gamemode=[
            app_commands.Choice(name="경쟁", value="competitive"),
            app_commands.Choice(name="일반", value="unrated"),
            app_commands.Choice(name="데스매치", value="deathmatch"),
            app_commands.Choice(name="기타(기본값)", value=""),  # 빈 값 → competitive로 처리
        ]
    )
    async def vsummary(
        self,
        inter: discord.Interaction,
        count: Optional[int] = None,
        gamemode: Optional[app_commands.Choice[str]] = None,
    ):
        # 기본값 처리
        if count is None:
            count = DEFAULT_SAMPLE
        count = max(1, min(10, count))
        mode = (gamemode.value if gamemode else None)
        resolved_mode = (mode or "").strip() or DEFAULT_MODE

        # 쿨다운
        if remain := check_cooldown(inter.user.id):
            await inter.response.send_message(f"Retry later. {remain}s left", ephemeral=True)
            return

        await inter.response.defer()

        try:
            # 대상
            name, tag, region = self._resolve_target(inter.user.id)

            summary = await self._ensure_summary(
                inter.user.id,
                name,
                tag,
                region,
                mode=resolved_mode,
                sample=count,
            )

            if summary.get("matches_found", 0) == 0:
                await inter.followup.send("No recent matches.")
                return

            wins = summary["wins"]
            losses = summary["losses"]
            winrate = summary["winrate"]
            kd = summary["kd"]
            tier_name = summary["tier_name"]
            rr = summary["rr"]
            msg = summary.get("message", "")
            total = summary.get("total", wins + losses)

            # 임베드 색
            if winrate >= 55:
                color = discord.Color.from_rgb(46, 204, 113)
            elif winrate >= 45:
                color = discord.Color.from_rgb(241, 196, 15)
            else:
                color = discord.Color.from_rgb(231, 76, 60)

            if gamemode:
                if gamemode.value:
                    mode_label = gamemode.name
                else:
                    mode_label = f"{summary['mode_label']}(기본)"
            else:
                mode_label = "경쟁(기본)"

            desc_parts = [
                f"모드: **{mode_label}**",
                f"**{tier_name} {rr}RR**",
                f"최근 {total}판: **{wins}W {losses}L** (**{winrate:.0f}%**)",
                f"KD : **{kd:.2f}**",
            ]
            desc = "\n".join(desc_parts) + "\n"

            streak = summary.get("streak") or {}
            streak_type = streak.get("type")
            streak_count = streak.get("count", 0)
            if streak_count:
                streak_word = "연승" if streak_type == "win" else "연패"
                desc += f"현재 {streak_word}: **{streak_count}**\n"

            if msg:
                desc += f"{msg}\n"

            diff_block = f"\n```diff\n+ W {wins}\n- L {losses}\n```"

            embed = discord.Embed(
                title=f"{name}#{tag}",
                description=desc + diff_block,
                color=color
            )

            # 티어 썸네일
            img = TIERS_DIR / f"{tier_key(tier_name)}.png"
            try:
                if img.exists():
                    file = discord.File(img, filename=img.name)
                    embed.set_thumbnail(url=f"attachment://{img.name}")
                    await inter.followup.send(embed=embed, file=file)
                else:
                    await inter.followup.send(embed=embed)
            except Exception:
                await inter.followup.send(embed=embed)

        except Exception as e:
            await inter.followup.send(f"Error: {e}")


async def setup(bot: commands.Bot):
    await bot.add_cog(SummaryCog(bot))
