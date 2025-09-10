import os
import json
import time
import asyncio
import urllib.parse
from pathlib import Path
from typing import Optional, Dict, Any

import aiohttp
import discord
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv

# -------------------- 환경 --------------------
load_dotenv()
DISCORD_TOKEN   = os.getenv("DISCORD_TOKEN")
GUILD_ID        = os.getenv("GUILD_ID")
HENRIK_API_KEY  = os.getenv("HENRIK_API_KEY")

intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)

# -------------------- 상수 --------------------
HENRIK_BASE = "https://api.henrikdev.xyz/valorant"
VAL_ASSET   = "https://valorant-api.com/v1"
DATA_DIR    = Path("data")
LINKS_FILE  = DATA_DIR / "links.json"
DATA_DIR.mkdir(exist_ok=True)
if not LINKS_FILE.exists():
    LINKS_FILE.write_text("{}", encoding="utf-8")

# -------------------- 유틸 --------------------
_session: Optional[aiohttp.ClientSession] = None

async def http_get(url: str, *, params: dict | None = None, headers: dict | None = None) -> dict:
    """Henrik API Key를 Authorization 헤더에 자동 주입"""
    assert _session is not None
    hdrs = dict(headers or {})
    if HENRIK_API_KEY:
        hdrs["Authorization"] = HENRIK_API_KEY
    async with _session.get(url, params=params, headers=hdrs) as r:
        txt = await r.text()
        if r.status != 200:
            raise RuntimeError(f"GET {url} -> {r.status}: {txt[:240]}")
        try:
            return json.loads(txt)
        except json.JSONDecodeError:
            raise RuntimeError(f"Invalid JSON from {url}: {txt[:120]}")

def load_links() -> Dict[str, Any]:
    try:
        return json.loads(LINKS_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}

def save_links(d: Dict[str, Any]) -> None:
    LINKS_FILE.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")

REGIONS = {"ap","kr","eu","na","br","latam"}
def norm_region(s: str) -> str:
    s = (s or "").lower()
    return s if s in REGIONS else "ap"

COOLDOWN_SEC = 5
_last_used: Dict[int, float] = {}
def check_cooldown(user_id: int) -> Optional[int]:
    now = time.time()
    last = _last_used.get(user_id, 0)
    remain = COOLDOWN_SEC - int(now - last)
    if remain > 0:
        return remain
    _last_used[user_id] = now
    return None

def q(s: str) -> str:
    """URL path-safe 인코딩"""
    return urllib.parse.quote(s, safe="")

# -------------------- 봇 이벤트 --------------------
@bot.event
async def on_ready():
    global _session
    if _session is None:
        _session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=12))

    names = [c.name for c in bot.tree.get_commands()]
    print(f"[DEBUG] commands in tree = {len(names)} -> {names}")

    try:
        if GUILD_ID and GUILD_ID.isdigit():
            guild = discord.Object(id=int(GUILD_ID))
            # 개발 중: 글로벌 커맨드를 길드로 복사해서 즉시 반영
            try:
                bot.tree.clear_commands(guild=guild)
                bot.tree.copy_global_to(guild=guild)
                print("[DEBUG] guild commands reset + copied from global")
            except Exception as e:
                print("[DEBUG] copy/clear failed:", e)

            synced = await bot.tree.sync(guild=guild)
            print(f"[SYNC] {GUILD_ID} 길드에 {len(synced)}개 슬래시 명령 동기화")
        else:
            synced = await bot.tree.sync()
            print(f"[SYNC] 전역에 {len(synced)}개 슬래시 명령 동기화(전파 지연 가능)")
    except Exception as e:
        print("[SYNC ERROR]", e)

    print(f"로그인: {bot.user} (ID: {bot.user.id})")

async def close_session():
    global _session
    if _session:
        await _session.close()
        _session = None

# -------------------- /resync (관리자용) --------------------
@bot.tree.command(name="resync", description="슬래시 명령 재동기화(소유자 전용)")
async def resync(inter: discord.Interaction):
    app = await bot.application_info()
    if inter.user.id != app.owner.id:
        await inter.response.send_message("권한 없음", ephemeral=True); return
    await inter.response.defer(ephemeral=True)
    try:
        if GUILD_ID and GUILD_ID.isdigit():
            guild = discord.Object(id=int(GUILD_ID))
            bot.tree.clear_commands(guild=guild)
            bot.tree.copy_global_to(guild=guild)
            synced = await bot.tree.sync(guild=guild)
            await inter.followup.send(f"길드 동기화 완료: {len(synced)}개", ephemeral=True)
        else:
            synced = await bot.tree.sync()
            await inter.followup.send(f"전역 동기화 완료: {len(synced)}개 (전파 지연 가능)", ephemeral=True)
    except Exception as e:
        await inter.followup.send(f"동기화 오류: {e}", ephemeral=True)

# -------------------- /link /unlink --------------------
@bot.tree.command(name="link", description="본인 Riot ID를 봇과 연결합니다 (전적 조회 동의)")
@app_commands.describe(name="Riot ID 이름", tag="Riot ID 태그", region="ap/kr/eu/na 등")
async def link(inter: discord.Interaction, name: str, tag: str, region: str = "ap"):
    if remain := check_cooldown(inter.user.id):
        await inter.response.send_message(f"잠시 후 재시도하십시오. {remain}초 남음", ephemeral=True)
        return

    await inter.response.defer(ephemeral=True)
    region = norm_region(region)

    # URL 인코딩 적용
    safe_name, safe_tag = q(name), q(tag)

    try:
        # 계정 존재 확인
        acc = await http_get(f"{HENRIK_BASE}/v1/account/{safe_name}/{safe_tag}")
        if acc.get("status") != 200:
            raise RuntimeError("계정 확인 실패")
    except Exception as e:
        await inter.followup.send(f"계정을 확인하지 못했습니다: {e}", ephemeral=True)
        return

    links = load_links()
    links[str(inter.user.id)] = {
        "name": name,  # 원문 저장
        "tag": tag,
        "region": region,
        "ts": int(time.time())
    }
    save_links(links)

    await inter.followup.send(
        f"연결 완료: **{name}#{tag}** (지역 {region.upper()})\n"
        "이 봇은 비공식 HenrikDev API를 사용하여 전적을 조회합니다. `/unlink`로 언제든 동의 철회 가능.",
        ephemeral=True
    )

@bot.tree.command(name="unlink", description="봇과 연결된 Riot ID를 해제합니다")
async def unlink(inter: discord.Interaction):
    if remain := check_cooldown(inter.user.id):
        await inter.response.send_message(f"잠시 후 재시도하십시오. {remain}초 남음", ephemeral=True)
        return

    await inter.response.defer(ephemeral=True)
    links = load_links()
    if str(inter.user.id) in links:
        info = links.pop(str(inter.user.id))
        save_links(links)
        await inter.followup.send(f"연결 해제: {info['name']}#{info['tag']}", ephemeral=True)
    else:
        await inter.followup.send("연결된 정보가 없습니다.", ephemeral=True)

# -------------------- 전적/프로필 --------------------
async def resolve_target(user: discord.abc.User, name: Optional[str], tag: Optional[str]) -> tuple[str,str,str]:
    links = load_links()
    if name and tag:
        return name, tag, "ap"
    info = links.get(str(user.id))
    if not info:
        raise RuntimeError("연결된 Riot ID가 없습니다. 먼저 `/link` 하십시오.")
    return info["name"], info["tag"], info.get("region","ap")

@bot.tree.command(name="vprofile", description="연결된 Riot ID(또는 지정된 ID)의 프로필/MMR")
@app_commands.describe(name="(선택) Riot ID 이름", tag="(선택) Riot ID 태그")
async def vprofile(inter: discord.Interaction, name: Optional[str] = None, tag: Optional[str] = None):
    if remain := check_cooldown(inter.user.id):
        await inter.response.send_message(f"잠시 후 재시도하십시오. {remain}초 남음", ephemeral=True)
        return

    await inter.response.defer()
    try:
        name, tag, region = await resolve_target(inter.user, name, tag)
        safe_name, safe_tag = q(name), q(tag)

        acc = await http_get(f"{HENRIK_BASE}/v1/account/{safe_name}/{safe_tag}")
        if acc.get("status") != 200:
            raise RuntimeError("계정 조회 실패")
        data = acc.get("data", {})
        card  = data.get("card", {})
        level = data.get("account_level", 0)
        title = data.get("title") or ""

        mmr = await http_get(f"{HENRIK_BASE}/v2/mmr/{region}/{safe_name}/{safe_tag}")
        cur = (mmr.get("data") or {}).get("current_data") or {}
        tier = cur.get("currenttierpatched") or "Unrated"
        rr   = cur.get("ranking_in_tier", 0)

        embed = discord.Embed(title=f"{name}#{tag}", description=f"레벨 {level} • {title}", color=discord.Color.red())
        embed.add_field(name="지역", value=region.upper())
        embed.add_field(name="현재 랭크", value=f"{tier} ({rr} RR)")
        if card.get("small"):
            embed.set_thumbnail(url=card["small"])
        await inter.followup.send(embed=embed)

    except Exception as e:
        await inter.followup.send(f"오류: {e}")

@bot.tree.command(name="vmatches", description="최근 매치 K/D/A 요약")
@app_commands.describe(count="가져올 경기 수(1~10)")
async def vmatches(inter: discord.Interaction, count: int = 5):
    if remain := check_cooldown(inter.user.id):
        await inter.response.send_message(f"잠시 후 재시도하십시오. {remain}초 남음", ephemeral=True)
        return

    await inter.response.defer()
    try:
        name, tag, region = await resolve_target(inter.user, None, None)
        safe_name, safe_tag = q(name), q(tag)
        count = max(1, min(10, count))

        js = await http_get(f"{HENRIK_BASE}/v3/matches/{region}/{safe_name}/{safe_tag}")
        matches = (js.get("data") or [])[:count]
        if not matches:
            await inter.followup.send("최근 전적이 없습니다.")
            return

        lines = []
        for m in matches:
            meta  = m.get("metadata", {})
            mapn  = meta.get("map", "?")
            mode  = meta.get("mode", "?")
            stats = m.get("stats", {})
            team  = stats.get("team")
            k, d, a = stats.get("kills",0), stats.get("deaths",0), stats.get("assists",0)

            has_won = False
            teams = m.get("teams")
            if team and isinstance(teams, dict) and team in teams:
                has_won = bool(teams[team].get("has_won"))

            res = "Win" if has_won else "Lose"
            lines.append(f"{mapn} / {mode} • {res} • {k}/{d}/{a}")

        await inter.followup.send("**최근 전적**\n" + "\n".join(f"- {t}" for t in lines))

    except Exception as e:
        await inter.followup.send(f"오류: {e}")

@bot.tree.command(name="vagent", description="에이전트 이미지/설명")
@app_commands.describe(name="예: Jett, Sage, Sova …")
async def vagent(inter: discord.Interaction, name: str):
    if remain := check_cooldown(inter.user.id):
        await inter.response.send_message(f"잠시 후 재시도하십시오. {remain}초 남음", ephemeral=True)
        return

    await inter.response.defer()
    try:
        agents = await http_get(f"{VAL_ASSET}/agents", params={"isPlayableCharacter":"true"})
        arr = agents.get("data") or []
        found = next((a for a in arr if a.get("displayName","").lower() == name.lower()), None)
        if not found:
            await inter.followup.send("에이전트를 찾지 못했습니다.")
            return
        embed = discord.Embed(
            title=found.get("displayName","Agent"),
            description=found.get("description",""),
            color=discord.Color.blue()
        )
        icon = found.get("displayIconSmall") or found.get("displayIcon")
        if icon:
            embed.set_thumbnail(url=icon)
        role = (found.get("role") or {}).get("displayName","")
        if role:
            embed.add_field(name="역할", value=role)
        await inter.followup.send(embed=embed)
    except Exception as e:
        await inter.followup.send(f"오류: {e}")

# -------------------- 실행 --------------------
if __name__ == "__main__":
    if not DISCORD_TOKEN:
        raise SystemExit("DISCORD_TOKEN 이 .env 에 없습니다")
    try:
        bot.run(DISCORD_TOKEN)
    finally:
        asyncio.run(close_session())
