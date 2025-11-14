import asyncio
from time import monotonic
from typing import Optional, List, Tuple, Dict, Any

import discord
from discord import app_commands
from discord.app_commands import locale_str
from discord.ext import commands

from core.config import HENRIK_BASE, TIERS_DIR
from core.http import http_get
from core.store import list_aliases, remove_alias, upsert_alias
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
        self._tier_cache: Dict[str, Tuple[float, Tuple[str, Optional[str]]]] = {}
        self._tier_cache_ttl = 600.0
        self._tier_fetch_retries = 3
        self._tier_fetch_base_delay = 1.0
        self._tier_fetch_semaphore = asyncio.Semaphore(5)

    register_alias_desc = locale_str("Alias to reference later", ko="나중에 사용할 별명")
    register_name_desc = locale_str("Riot ID name", ko="Riot ID 이름")
    register_tag_desc = locale_str("Riot ID tag", ko="Riot ID 태그")
    register_region_desc = locale_str("Valorant region (ap/kr/eu/na/...)", ko="발로란트 지역(ap/kr/eu/na/...)")

    @app_commands.command(
        name="별명등록",
        description="입력한 Riot ID에 별명을 등록합니다.",
    )
    @app_commands.describe(
        alias=register_alias_desc,
        name=register_name_desc,
        tag=register_tag_desc,
        region=register_region_desc,
    )
    async def register(
        self,
        inter: discord.Interaction,
        alias: str,
        name: str,
        tag: str,
        region: Optional[str] = None,
    ) -> None:
        alias = clean_text(alias)
        name = clean_text(name)
        tag = clean_text(tag)
        region = norm_region(region or "ap")

        if not alias:
            await inter.response.send_message("별명이 비어 있습니다.", ephemeral=True)
            return
        if len(alias) > 32:
            await inter.response.send_message("별명은 32자 이하로 입력해주세요.", ephemeral=True)
            return
        if not name or not tag:
            await inter.response.send_message("Riot ID 이름과 태그를 모두 입력해주세요.", ephemeral=True)
            return

        if remain := check_cooldown(inter.user.id):
            await inter.response.send_message(
                f"잠시 후 다시 시도해주세요. 남은 대기시간: {remain}초", ephemeral=True
            )
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
                await inter.followup.send(
                    "계정을 찾을 수 없습니다. Riot ID 이름과 태그를 다시 확인해주세요.",
                    ephemeral=True,
                )
            else:
                err = format_exception_message(e)
                await inter.followup.send(f"등록에 실패했습니다: {err}", ephemeral=True)

    unregister_alias_desc = locale_str("Alias to remove", ko="삭제할 별명")

    @app_commands.command(
        name="별명삭제",
        description="등록된 Riot ID 별명을 삭제합니다.",
    )
    @app_commands.describe(alias=unregister_alias_desc)
    async def unregister(self, inter: discord.Interaction, alias: str) -> None:
        alias = clean_text(alias)
        if not alias:
            await inter.response.send_message("별명이 비어 있습니다.", ephemeral=True)
            return

        if remain := check_cooldown(inter.user.id):
            await inter.response.send_message(
                f"잠시 후 다시 시도해주세요. 남은 대기시간: {remain}초", ephemeral=True
            )
            return

        await inter.response.defer(ephemeral=True)
        removed = remove_alias(alias)
        if removed:
            await inter.followup.send(f"별명 **{alias}** 을(를) 삭제했습니다.", ephemeral=True)
        else:
            await inter.followup.send(f"별명 **{alias}** 을(를) 찾을 수 없습니다.", ephemeral=True)

    @app_commands.command(
        name="별명목록",
        description="등록된 Riot ID 별명 목록을 확인합니다.",
    )
    async def list_aliases_command(self, inter: discord.Interaction) -> None:
        if remain := check_cooldown(inter.user.id):
            await inter.response.send_message(
                f"잠시 후 다시 시도해주세요. 남은 대기시간: {remain}초", ephemeral=True
            )
            return

        records = list_aliases()
        if not records:
            await inter.response.send_message("등록된 별명이 없습니다.", ephemeral=True)
            return

        await inter.response.defer()

        tier_tasks: Dict[Tuple[str, str, str], asyncio.Task] = {}
        semaphore = asyncio.Semaphore(3)

        async def fetch_tier_with_cache(record: Dict[str, Any]) -> Tuple[str, Optional[str]]:
            key = (
                record.get("region", "ap"),
                record.get("name", ""),
                record.get("tag", ""),
            )
            task = tier_tasks.get(key)
            if task is None:
                async def _task() -> Tuple[str, Optional[str]]:
                    async with semaphore:
                        return await self._fetch_tier(record)

                task = asyncio.create_task(_task())
                tier_tasks[key] = task
            return await task

        tier_results = await asyncio.gather(
            *(fetch_tier_with_cache(rec) for rec in records)
        )

        embeds_payload: List[Tuple[discord.Embed, Optional[str]]] = []

        tier_results = await asyncio.gather(
            *(self._fetch_tier_with_semaphore(rec) for rec in records)
        )
        semaphore = asyncio.Semaphore(5)

        async def fetch_tier(record: Dict[str, Any]) -> Tuple[str, Optional[str]]:
            async with semaphore:
                try:
                    return await self._fetch_tier(record)
                except Exception:
                    return TIER_NOT_FOUND_LABEL, None

        tier_results = await asyncio.gather(*(fetch_tier(rec) for rec in records))

        for rec, (tier_name, image_url) in zip(records, tier_results):
            embed = discord.Embed(
                description=f"**{rec['name']}#{rec['tag']}** ({rec['region'].upper()})",
                color=discord.Color.blurple(),
            )
            embed.set_author(name=rec["alias"])
            display_tier = tier_name if tier_name and tier_name != "Unrated" else "언레이디드"
            embed.add_field(name="티어", value=display_tier or TIER_NOT_FOUND_LABEL, inline=False)

            local_path: Optional[str] = None
            if image_url:
                embed.set_thumbnail(url=image_url)
            else:
                local = self._local_tier_image(tier_name)
                if local is not None:
                    local_path = str(local)

            embeds_payload.append((embed, local_path))

        await self._send_alias_embeds(inter, embeds_payload)

    async def _fetch_tier_with_semaphore(self, record: Dict[str, Any]) -> Tuple[str, Optional[str]]:
        async with self._tier_fetch_semaphore:
            return await self._fetch_tier(record)

    def _tier_cache_key(self, record: Dict[str, Any]) -> str:
        region = (record.get("region") or "ap").lower()
        name = (record.get("name") or "").lower()
        tag = (record.get("tag") or "").lower()
        return f"{region}:{name}:{tag}"

    def _get_cached_tier(self, key: str) -> Optional[Tuple[str, Optional[str]]]:
        cached = self._tier_cache.get(key)
        if not cached:
            return None

        expires_at, value = cached
        if expires_at >= monotonic():
            return value

        self._tier_cache.pop(key, None)
        return None

    def _store_tier_cache(self, key: str, value: Tuple[str, Optional[str]]) -> None:
        self._tier_cache[key] = (monotonic() + self._tier_cache_ttl, value)

    async def _fetch_tier(self, record: Dict[str, Any]) -> Tuple[str, Optional[str]]:
        cache_key = self._tier_cache_key(record)
        cached_value = self._get_cached_tier(cache_key)
        if cached_value is not None:
            return cached_value

        name = record.get("name", "")
        tag = record.get("tag", "")
        region = record.get("region", "ap")
        delay = self._tier_fetch_base_delay
        for attempt in range(self._tier_fetch_retries):
            try:
                mmr = await http_get(f"{HENRIK_BASE}/v2/mmr/{region}/{q(name)}/{q(tag)}")
                data = (mmr.get("data") or {}).get("current_data") or {}
                tier_name = data.get("currenttierpatched") or TIER_NOT_FOUND_LABEL
                images = data.get("images") or {}
                image_url = images.get("small")
                result = (tier_name, image_url)
                self._store_tier_cache(cache_key, result)
                return result
            except Exception as exc:
                is_last_attempt = attempt == self._tier_fetch_retries - 1
                if is_last_attempt:
                    break

                error_text = str(exc)
                backoff_delay = delay
                if "429" in error_text:
                    backoff_delay *= 2

                await asyncio.sleep(backoff_delay)
                delay *= 2

        fallback = (TIER_NOT_FOUND_LABEL, None)
        self._store_tier_cache(cache_key, fallback)
        return fallback

    def _local_tier_image(self, tier_name: Optional[str]):
        key = tier_key(tier_name or TIER_NOT_FOUND_LABEL)
        path = TIERS_DIR / f"{key}.png"
        return path if path.exists() else None

    async def _send_alias_embeds(
        self,
        inter: discord.Interaction,
        payload: List[Tuple[discord.Embed, Optional[str]]],
    ) -> None:
        if not payload:
            await inter.followup.send("등록된 별명이 없습니다.")
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


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(RegisterCog(bot))
