from __future__ import annotations

import asyncio
import json
import re

from discord import app_commands, Interaction
from discord.ext import commands

from core import config

_links_lock = asyncio.Lock()
RIOT_ID_RE = re.compile(r"^[^#\s]{2,16}#[A-Za-z0-9]{3,5}$")


def _load_links() -> dict[str, dict[str, str]]:
    if not config.LINKS_FILE.exists():
        return {}
    try:
        data = json.loads(config.LINKS_FILE.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return data  # { guild_id: { alias: riot_id } }
    except Exception:
        pass
    return {}


def _save_links(data: dict[str, dict[str, str]]) -> None:
    config.LINKS_FILE.write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def _format_alias_row(alias: str, riot_id: str) -> str:
    return f"• `{alias}` → `{riot_id}`"


async def _autocomplete_alias(
    interaction: Interaction, current: str
) -> list[app_commands.Choice[str]]:
    guild_id = str(interaction.guild_id)
    data = _load_links()
    mapping = data.get(guild_id, {})
    q = current.lower()
    results: list[app_commands.Choice[str]] = []
    for alias, rid in mapping.items():
        if q in alias.lower() or q in rid.lower():
            results.append(app_commands.Choice(name=f"{alias} ({rid})", value=alias))
        if len(results) >= 20:
            break
    return results


class Alias(commands.Cog):
    """별명(닉네임) ↔ RiotID(#Tag) 매핑 관리"""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # 등록 (add / upsert)
    @app_commands.command(name="등록", description="RiotID#Tag 를 별명으로 등록합니다.")
    @app_commands.describe(
        riot_id="예: 이름#KR1",
        nickname="생략 시 RiotID 전체 문자열을 별명으로 사용",
    )
    async def add(self, interaction: Interaction, riot_id: str, nickname: str | None = None):
        if not RIOT_ID_RE.match(riot_id):
            await interaction.response.send_message(
                "❌ 형식이 올바르지 않습니다. 예: `Player#KR1` (이름: 2~16자, 태그: 3~5자 영숫자)",
                ephemeral=True,
            )
            return

        guild_id = str(interaction.guild_id)
        alias = nickname or riot_id

        async with _links_lock:
            data = _load_links()
            data.setdefault(guild_id, {})
            data[guild_id][alias] = riot_id
            _save_links(data)

        await interaction.response.send_message(
            f"✅ 등록 완료: `{alias}` → `{riot_id}`", ephemeral=True
        )

    # 삭제
    @app_commands.command(name="별명삭제", description="등록한 별명을 삭제합니다.")
    @app_commands.describe(nickname="삭제할 별명")
    @app_commands.autocomplete(nickname=_autocomplete_alias)
    async def remove(self, interaction: Interaction, nickname: str):
        guild_id = str(interaction.guild_id)
        async with _links_lock:
            data = _load_links()
            mapping = data.get(guild_id, {})
            if nickname not in mapping:
                await interaction.response.send_message("❌ 해당 별명이 없습니다.", ephemeral=True)
                return
            removed = mapping.pop(nickname)
            if mapping:
                data[guild_id] = mapping
            else:
                data.pop(guild_id, None)
            _save_links(data)
        await interaction.response.send_message(
            f"🗑️ 삭제 완료: `{nickname}` (기존 `{removed}`)", ephemeral=True
        )

    # 목록
    @app_commands.command(name="별명목록", description="이 서버의 등록된 별명을 모두 보여줍니다.")
    async def list_aliases(self, interaction: Interaction):
        guild_id = str(interaction.guild_id)
        data = _load_links()
        mapping = data.get(guild_id, {})
        if not mapping:
            await interaction.response.send_message("ℹ️ 등록된 별명이 없습니다.", ephemeral=True)
            return

        items = [_format_alias_row(a, r) for a, r in mapping.items()]
        header = f"**등록된 별명 ({len(items)}개)**\n"
        text = header + "\n".join(items[:50])
        if len(items) > 50:
            text += f"\n… 외 {len(items) - 50}개"
        await interaction.response.send_message(text)

    # 조회
    @app_commands.command(name="별명조회", description="별명에 매핑된 RiotID를 보여줍니다.")
    @app_commands.describe(nickname="조회할 별명")
    @app_commands.autocomplete(nickname=_autocomplete_alias)
    async def show(self, interaction: Interaction, nickname: str):
        guild_id = str(interaction.guild_id)
        data = _load_links()
        riot_id = data.get(guild_id, {}).get(nickname)
        if not riot_id:
            await interaction.response.send_message("❌ 등록된 별명이 없습니다.", ephemeral=True)
            return
        await interaction.response.send_message(f"`{nickname}` → `{riot_id}`", ephemeral=True)

    @staticmethod
    def resolve(guild_id: int | str, key: str) -> str | None:
        if isinstance(guild_id, int):
            guild_id = str(guild_id)
        if RIOT_ID_RE.match(key):
            return key
        data = _load_links()
        return data.get(guild_id, {}).get(key)


async def setup(bot: commands.Bot):
    await bot.add_cog(Alias(bot))
