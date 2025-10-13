from typing import Optional, List, Tuple, Dict, Any

import discord
from discord import app_commands
from discord.ext import commands

from core.config import HENRIK_BASE, TIERS_DIR
from core.http import http_get
from core.store import get_alias, list_aliases, remove_alias, upsert_alias
from core.utils import (
    check_cooldown,
    clean_text,
    norm_region,
    q,
    is_account_not_found_error,
    format_exception_message,
    tier_key,
)

TIER_NOT_FOUND_LABEL = "Unrated"


class RegisterCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="register", description="별칭을 등록해 플레이어를 빠르게 조회합니다.")
    @app_commands.describe(
        alias="나중에 사용할 별칭",
        name="라이엇 ID 이름",
        tag="라이엇 ID 태그",
        region="발로란트 지역 (ap/kr/eu/na/...)",
    )
    async def register(
        self,
        inter: discord.Interaction,
        alias: str,
        name: str,
        tag: str,
        region: Optional[str] = None,
    ):
        alias = clean_text(alias)
        name = clean_text(name)
        tag = clean_text(tag)
        region = norm_region(region or "ap")
        if not alias:
            await inter.response.send_message("별칭은 비워둘 수 없습니다.", ephemeral=True)
            return
        if len(alias) > 32:
            await inter.response.send_message("별칭은 32자 이하로 입력해 주세요.", ephemeral=True)
            return
        if not name or not tag:
            await inter.response.send_message("라이엇 ID 이름과 태그를 모두 입력해 주세요.", ephemeral=True)
            return

        if remain := check_cooldown(inter.user.id):
            await inter.response.send_message(f"잠시 후 다시 시도해 주세요. 남은 대기 시간: {remain}초", ephemeral=True)
            return

        await inter.response.defer(ephemeral=True)
        try:
            acc = await http_get(f"{HENRIK_BASE}/v1/account/{q(name)}/{q(tag)}")
            if acc.get("status") != 200:
                raise RuntimeError("Account not found")
            data = acc.get("data") or {}
            puuid = data.get("puuid")
            if not puuid:
                raise RuntimeError("Puuid missing in HenrikDev response")

            upsert_alias(alias, name, tag, region, puuid)
            await inter.followup.send(
                f"등록 완료: **{alias}** → **{name}#{tag}** ({region.upper()})", ephemeral=True
            )
        except Exception as e:
            if is_account_not_found_error(e):
                await inter.followup.send("계정을 찾을 수 없습니다. 계정 이름과 태그를 확인해 주세요.", ephemeral=True)
            else:
                err = format_exception_message(e)
                await inter.followup.send(f"등록에 실패했습니다: {err}", ephemeral=True)

    @app_commands.command(name="unregister", description="등록된 별칭을 삭제합니다.")
    @app_commands.describe(alias="삭제할 별칭")
    async def unregister(self, inter: discord.Interaction, alias: str):
        alias = clean_text(alias)
        if not alias:
            await inter.response.send_message("별칭은 비워둘 수 없습니다.", ephemeral=True)
            return

        if remain := check_cooldown(inter.user.id):
            await inter.response.send_message(f"잠시 후 다시 시도해 주세요. 남은 대기 시간: {remain}초", ephemeral=True)
            return

        await inter.response.defer(ephemeral=True)
        removed = remove_alias(alias)
        if removed:
            await inter.followup.send(f"별칭 **{alias}** 을(를) 삭제했습니다.", ephemeral=True)
        else:
            await inter.followup.send(f"별칭 **{alias}** 을(를) 찾을 수 없습니다.", ephemeral=True)

    @app_commands.command(name="aliases", description="등록된 별칭 목록을 보여줍니다.")
    async def aliases(self, inter: discord.Interaction):
        if remain := check_cooldown(inter.user.id):
            await inter.response.send_message(f"잠시 후 다시 시도해 주세요. 남은 대기 시간: {remain}초")
            return

        records = list_aliases()
        if not records:
            await inter.response.send_message("등록된 별칭이 없습니다.")
            return

        await inter.response.defer()

        embeds_payload: List[Tuple[discord.Embed, str | None]] = []
        for rec in records:
            tier_name, image_url = await self._fetch_tier(rec)
            embed = discord.Embed(
                description=f"**{rec['name']}#{rec['tag']}** ({rec['region'].upper()})",
                color=discord.Color.blurple(),
            )
            embed.set_author(name=rec["alias"])
            display_tier = tier_name if tier_name and tier_name != "Unrated" else "언레이트"
            embed.add_field(name="티어", value=display_tier or TIER_NOT_FOUND_LABEL, inline=False)

            local_path: str | None = None
            if image_url:
                embed.set_thumbnail(url=image_url)
            else:
                local = self._local_tier_image(tier_name)
                if local is not None:
                    local_path = str(local)

            embeds_payload.append((embed, local_path))

        await self._send_alias_embeds(inter, embeds_payload)

    async def _fetch_tier(self, record: Dict[str, Any]) -> Tuple[str, str | None]:
        name = record.get("name", "")
        tag = record.get("tag", "")
        region = record.get("region", "ap")
        try:
            mmr = await http_get(f"{HENRIK_BASE}/v2/mmr/{region}/{q(name)}/{q(tag)}")
            data = (mmr.get("data") or {}).get("current_data") or {}
            tier_name = data.get("currenttierpatched") or TIER_NOT_FOUND_LABEL
            images = data.get("images") or {}
            image_url = images.get("small")
            return tier_name, image_url
        except Exception:
            return TIER_NOT_FOUND_LABEL, None

    def _local_tier_image(self, tier_name: str | None):
        key = tier_key(tier_name or TIER_NOT_FOUND_LABEL)
        path = TIERS_DIR / f"{key}.png"
        return path if path.exists() else None

    async def _send_alias_embeds(
        self,
        inter: discord.Interaction,
        payload: List[Tuple[discord.Embed, str | None]],
    ) -> None:
        if not payload:
            await inter.followup.send("등록된 별칭이 없습니다.")
            return

        chunk_size = 10
        is_first = True
        for offset in range(0, len(payload), chunk_size):
            chunk = payload[offset : offset + chunk_size]
            embeds_to_send: List[discord.Embed] = []
            files: List[discord.File] = []
            for idx, (embed, local_path) in enumerate(chunk):
                embed_to_send = embed.copy()
                if local_path:
                    filename = f"tier_{offset + idx}.png"
                    file = discord.File(local_path, filename=filename)
                    embed_to_send.set_thumbnail(url=f"attachment://{filename}")
                    files.append(file)
                embeds_to_send.append(embed_to_send)

            kwargs: Dict[str, Any] = {"embeds": embeds_to_send}
            if files:
                kwargs["files"] = files

            if is_first:
                await inter.followup.send(**kwargs)
                is_first = False
            else:
                await inter.followup.send(**kwargs)


async def setup(bot: commands.Bot):
    await bot.add_cog(RegisterCog(bot))
