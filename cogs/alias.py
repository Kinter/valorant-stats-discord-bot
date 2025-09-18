from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Dict, Any, Optional

import aiohttp
import discord
from discord.ext import commands
from discord import app_commands

ALIASES_PATH = Path("data/aliases.json")
HENRIK_BASE = "https://api.henrikdev.xyz"
HENRIK_KEY = os.getenv("HENRIK_API_KEY", "")


def _load_aliases() -> Dict[str, Dict[str, Dict[str, str]]]:
    """
    파일 스키마:
    {
      "<guild_id>": {
        "<alias>": {"game_name": "이름", "tag_line": "태그", "region": "AP"}
      }
    }
    """
    if not ALIASES_PATH.exists():
        ALIASES_PATH.parent.mkdir(parents=True, exist_ok=True)
        ALIASES_PATH.write_text("{}", encoding="utf-8")
    with ALIASES_PATH.open("r", encoding="utf-8") as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            return {}


def _save_aliases(data: Dict[str, Any]) -> None:
    ALIASES_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = ALIASES_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(ALIASES_PATH)


async def fetch_summary(game_name: str, tag_line: str, region: str = "AP") -> Dict[str, Any]:
    if not HENRIK_KEY:
        raise RuntimeError("HENRIK_API_KEY 환경변수가 설정되지 않았습니다.")
    headers = {"Authorization": HENRIK_KEY}
    async with aiohttp.ClientSession(headers=headers) as sess:
        # MMR/Rank
        async with sess.get(f"{HENRIK_BASE}/valorant/v1/mmr/{region}/{game_name}/{tag_line}") as r:
            mmr = await r.json()
        # Recent matches (1~5개)
        async with sess.get(f"{HENRIK_BASE}/valorant/v3/matches/{region}/{game_name}/{tag_line}?size=1") as r:
            matches = await r.json()

    # 방어적 파싱
    rank = None
    mmr_part = None
    last_match = None

    try:
        data = mmr.get("data") or {}
        current_data = data.get("current_data") or {}
        rank = {"tier": current_data.get("currenttier_patched"), "rr": current_data.get("ranking_in_tier")}
        mmr_part = {"elo": data.get("mmr_change_to_last_game") or data.get("elo")}
    except Exception:
        pass

    try:
        md = (matches.get("data") or [None])[0]
        if md:
            last_match = {
                "id": md.get("metadata", {}).get("matchid"),
                "mode": md.get("metadata", {}).get("mode"),
                "map": md.get("metadata", {}).get("map"),
                "result": "Win" if (md.get("teams", {}).get("red", {}).get("has_won") or md.get("teams", {}).get("blue", {}).get("has_won")) else "Loss",
                "kda": [
                    (md.get("players", {}).get("all_players", [{}])[0].get("stats", {}) or {}).get("kills"),
                    (md.get("players", {}).get("all_players", [{}])[0].get("stats", {}) or {}).get("deaths"),
                    (md.get("players", {}).get("all_players", [{}])[0].get("stats", {}) or {}).get("assists"),
                ],
            }
    except Exception:
        pass

    return {"rank": rank, "mmr": mmr_part, "last_match": last_match}


class AliasesCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="등록", description="/등록 \"이름#태그\" \"별명\" — 별명을 Riot ID에 연결합니다.")
    async def register_alias(self, interaction: discord.Interaction, riot_id: str, alias: str, region: str = "AP"):
        riot_id = riot_id.strip().replace("\u200b", "")
        alias = alias.strip()
        if "#" not in riot_id:
            return await interaction.response.send_message("형식이 올바르지 않습니다. 예) 철수#KR1", ephemeral=True)
        game_name, tag_line = riot_id.split("#", 1)
        if not (1 <= len(alias) <= 24):
            return await interaction.response.send_message("별명은 1~24자여야 합니다.", ephemeral=True)

        store = _load_aliases()
        g = store.setdefault(str(interaction.guild_id), {})
        g[alias] = {"game_name": game_name, "tag_line": tag_line, "region": region}
        _save_aliases(store)
        await interaction.response.send_message(f"등록 완료: **{alias}** → **{game_name}#{tag_line}** [{region}]", ephemeral=True)

    @app_commands.command(name="전적", description="/전적 \"별명\" — 별명으로 현재 전적 요약을 조회합니다.")
    async def summary_by_alias(self, interaction: discord.Interaction, alias: str):
        alias = alias.strip()
        store = _load_aliases()
        mapping = (store.get(str(interaction.guild_id)) or {}).get(alias)
        if not mapping:
            # 별명 대신 직접 Riot ID를 넣은 경우도 허용
            if "#" in alias:
                game_name, tag_line = alias.split("#", 1)
                region = "AP"
            else:
                return await interaction.response.send_message("별명이 등록되어 있지 않습니다. 먼저 /등록을 사용하십시오.", ephemeral=True)
        else:
            game_name, tag_line, region = mapping["game_name"], mapping["tag_line"], mapping.get("region", "AP")

        try:
            snap = await fetch_summary(game_name, tag_line, region)
        except Exception as e:
            return await interaction.response.send_message(f"전적 조회 중 오류: {e}", ephemeral=True)

        rank = snap.get("rank") if isinstance(snap, dict) else None
        mmr = snap.get("mmr") if isinstance(snap, dict) else None
        lm = snap.get("last_match") if isinstance(snap, dict) else None
        desc_lines = []
        if rank:
            desc_lines.append(f"랭크: {rank.get('tier')} ({rank.get('rr')} RR)")
        if mmr:
            desc_lines.append(f"MMR: {mmr.get('elo')}")
        if lm:
            k, d, a = (lm.get("kda") or [None, None, None])
            desc_lines.append(f"최근 경기: {lm.get('mode')} | {lm.get('map')} | {lm.get('result')} | KDA {k}/{d}/{a}")
        if not desc_lines:
            desc_lines.append("표시할 정보가 없습니다.")

        embed = discord.Embed(title=f"{game_name}#{tag_line} 전적 요약", description="\n".join(desc_lines))
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="별명제거", description="/별명제거 \"별명\" — 별명 매핑을 삭제합니다.")
    async def alias_remove(self, interaction: discord.Interaction, alias: str):
        store = _load_aliases()
        g = store.get(str(interaction.guild_id)) or {}
        if alias in g:
            del g[alias]
            store[str(interaction.guild_id)] = g
            _save_aliases(store)
            return await interaction.response.send_message(f"제거됨: **{alias}**", ephemeral=True)
        await interaction.response.send_message("해당 별명이 없습니다.", ephemeral=True)

    @app_commands.command(name="별명목록", description="현재 길드에 등록된 별명 목록을 보여줍니다.")
    async def alias_list(self, interaction: discord.Interaction):
        g = (_load_aliases().get(str(interaction.guild_id)) or {})
        if not g:
            return await interaction.response.send_message("현재 별명이 없습니다.", ephemeral=True)
        lines = [f"• **{k}** → {v['game_name']}#{v['tag_line']} [{v.get('region','AP')}]" for k, v in sorted(g.items())]
        embed = discord.Embed(title="별명 목록", description="\n".join(lines))
        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(AliasesCog(bot))
