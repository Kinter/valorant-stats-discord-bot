from typing import Optional
from pathlib import Path
import discord
from discord import app_commands
from discord.ext import commands
from core.config import HENRIK_BASE, TIERS_DIR
from core.http import http_get
from core.store import get_link
from core.utils import check_cooldown, q, tier_key, trunc2

async def fetch_matches(region: str, name: str, tag: str, *, mode: Optional[str], size: int) -> dict:
    """mode 비었으면 competitive로 기본 적용"""
    params = {"mode": mode.strip() if mode and mode.strip() else "competitive",
              "size": str(max(1, min(10, size)))}
    url = f"{HENRIK_BASE}/v3/matches/{region}/{q(name)}/{q(tag)}"
    return await http_get(url, params=params)

class SummaryCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    def _resolve_target(self, user_id: int) -> tuple[str, str, str]:
        info = get_link(user_id)
        if not info:
            raise RuntimeError("No linked Riot ID. Use /link first.")
        return info["name"], info["tag"], info.get("region", "ap")

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
            count = 10
        count = max(1, min(10, count))
        mode = (gamemode.value if gamemode else None)  # ""면 아래 fetch_matches에서 competitive로 대체

        # 쿨다운
        if remain := check_cooldown(inter.user.id):
            await inter.response.send_message(f"Retry later. {remain}s left", ephemeral=True)
            return

        await inter.response.defer()

        try:
            # 대상
            name, tag, region = self._resolve_target(inter.user.id)

            # 계정/puuid
            acc = await http_get(f"{HENRIK_BASE}/v1/account/{q(name)}/{q(tag)}")
            puuid = (acc.get("data") or {}).get("puuid")

            # 현재 티어/RR
            mmr = await http_get(f"{HENRIK_BASE}/v2/mmr/{region}/{q(name)}/{q(tag)}")
            cur = (mmr.get("data") or {}).get("current_data") or {}
            tier_name = cur.get("currenttierpatched") or "Unrated"
            rr = cur.get("ranking_in_tier", 0)

            # 매치 조회 (mode 비면 competitive)
            js = await fetch_matches(region, name, tag, mode=mode, size=count)
            matches = (js.get("data") or [])
            if not matches:
                await inter.followup.send("No recent matches.")
                return

            # 집계
            wins = losses = 0
            tot_k = tot_d = 0

            for m in matches:
                players = ((m.get("players") or {}).get("all_players") or [])
                me = next((p for p in players if p.get("puuid") == puuid), None)
                if not me:
                    continue

                s = me.get("stats") or {}
                k, d = s.get("kills", 0), s.get("deaths", 0)
                tot_k += k
                tot_d += d

                # ── 승/패 판정: 대소문자 정규화 ──
                teams_raw = (m.get("teams") or {})
                teams = {str(k).lower(): v for k, v in teams_raw.items()}
                my_team = (me.get("team") or "").lower()

                has_won = None
                if my_team in teams and isinstance(teams[my_team], dict):
                    has_won = teams[my_team].get("has_won")

                # 데스매치 등 팀 승패가 없는 모드는 카운트 제외
                if isinstance(has_won, bool):
                    if has_won:
                        wins += 1
                    else:
                        losses += 1
                # else: 승패 정보 없음 → skip (총판 수 계산에 포함하지 않음)

            total = wins + losses
            winrate = (wins / total * 100) if total else 0
            kd = trunc2(tot_k / tot_d) if tot_d else float(tot_k)

            # 멘트
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

            # 임베드 색
            if winrate >= 55:
                color = discord.Color.from_rgb(46, 204, 113)
            elif winrate >= 45:
                color = discord.Color.from_rgb(241, 196, 15)
            else:
                color = discord.Color.from_rgb(231, 76, 60)

            # 본문
            mode_label = (gamemode.name if gamemode else "경쟁(기본)")

            desc = (
               f"모드: **{mode_label}**\n"
               f"**{tier_name} {rr}RR**\n"
               f"최근 {total}판: **{wins}W {losses}L** (**{winrate:.0f}%**)\n"
               f"KD : **{kd:.2f}**\n"
            )

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
