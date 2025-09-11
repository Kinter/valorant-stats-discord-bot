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

TIER_EMOJI = {
    "Radiant": ":radiant:",
    "Immortal 1": ":immortal1:",
    "Immortal 2": ":immortal2:",
    "Immortal 3": ":immortal3:",
    "Ascendant 1": ":ascendant1:",
    "Ascendant 2": ":ascendant2:",
    "Ascendant 3": ":ascendant3:",
    "Diamond 1": ":diamond1:",
    "Diamond 2": ":diamond2:",
    "Diamond 3": ":diamond3:",
    "Diamond 4": ":diamond4:",
    "Platinum 1": ":platinum1:",
    "Platinum 2": ":platinum2:",
    "Platinum 3": ":platinum3:",
    "Platinum 4": ":platinum4:",
    "Gold 1": ":gold1:",
    "Gold 2": ":gold2:",
    "Gold 3": ":gold3:",
    "Gold 4": ":gold4:",
    "Silver 1": ":silver1:",
    "Silver 2": ":silver2:",
    "Silver 3": ":silver3:",
    "Silver 4": ":silver4:",
    "Bronze 1": ":bronze1:",
    "Bronze 2": ":bronze2:",
    "Bronze 3": ":bronze3:",
    "Bronze 4": ":bronze4:",
    "Iron 1": ":iron1:",
    "Iron 2": ":iron2:",
    "Iron 3": ":iron3:",
    "Iron 4": ":iron4:",
    "Unrated": ":unrated:",
}

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
    assert _session is not None
    hdrs = dict(headers or {})
    if HENRIK_API_KEY:
        hdrs["Authorization"] = HENRIK_API_KEY
    async with _session.get(url, params=params, headers=hdrs) as r:
        txt = await r.text()
        if r.status != 200:
            raise RuntimeError(f"GET {url} -> {r.status}: {txt[:240]}")
        return json.loads(txt)

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
    return urllib.parse.quote(s, safe="")

async def fetch_matches(region: str, name: str, tag: str,
                        mode: Optional[str] = None,
                        map: Optional[str] = None,
                        size: Optional[int] = None) -> dict:
    safe_name = urllib.parse.quote(name, safe="")
    safe_tag  = urllib.parse.quote(tag,  safe="")
    url = f"{HENRIK_BASE}/v3/matches/{region}/{safe_name}/{safe_tag}"
    params = {}
    if (mode or "").strip():
        params["mode"] = mode
    else:
        params["mode"] = "competitive"
    if map:
        params["map"] = map
    if size:
        params["size"] = str(max(1, min(10, size)))
    return await http_get(url, params=params)

def trunc2(x: float) -> float:
    return int(x * 100) / 100

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
            bot.tree.clear_commands(guild=guild)
            bot.tree.copy_global_to(guild=guild)
            synced = await bot.tree.sync(guild=guild)
            print(f"[SYNC] {GUILD_ID} 길드에 {len(synced)}개 슬래시 명령 동기화")
        else:
            synced = await bot.tree.sync()
            print(f"[SYNC] 전역에 {len(synced)}개 동기화")
    except Exception as e:
        print("[SYNC ERROR]", e)
    print(f"로그인: {bot.user} (ID: {bot.user.id})")

async def close_session():
    global _session
    if _session:
        await _session.close()
        _session = None

# -------------------- Commands --------------------
@bot.tree.command(name="resync", description="슬래시 명령 재동기화")
async def resync(inter: discord.Interaction):
    await inter.response.defer(ephemeral=True)
    guild = discord.Object(id=int(GUILD_ID))
    bot.tree.clear_commands(guild=guild)
    bot.tree.copy_global_to(guild=guild)
    synced = await bot.tree.sync(guild=guild)
    await inter.followup.send(f"길드 동기화 완료: {len(synced)}개", ephemeral=True)

@bot.tree.command(name="link", description="본인 Riot ID를 연결")
@app_commands.describe(name="Riot ID 이름", tag="Riot ID 태그", region="ap/kr/eu/na 등")
async def link(inter: discord.Interaction, name: str, tag: str, region: str = "ap"):
    await inter.response.defer(ephemeral=True)
    region = norm_region(region)
    safe_name, safe_tag = q(name), q(tag)
    acc = await http_get(f"{HENRIK_BASE}/v1/account/{safe_name}/{safe_tag}")
    links = load_links()
    links[str(inter.user.id)] = {"name": name, "tag": tag, "region": region, "ts": int(time.time())}
    save_links(links)
    await inter.followup.send(f"연결 완료: **{name}#{tag}** (지역 {region.upper()})", ephemeral=True)

@bot.tree.command(name="unlink", description="연결 해제")
async def unlink(inter: discord.Interaction):
    await inter.response.defer(ephemeral=True)
    links = load_links()
    if str(inter.user.id) in links:
        info = links.pop(str(inter.user.id))
        save_links(links)
        await inter.followup.send(f"연결 해제: {info['name']}#{info['tag']}", ephemeral=True)
    else:
        await inter.followup.send("연결된 정보 없음", ephemeral=True)

async def resolve_target(user: discord.abc.User, name: Optional[str], tag: Optional[str]) -> tuple[str,str,str]:
    links = load_links()
    if name and tag:
        return name, tag, "ap"
    info = links.get(str(user.id))
    if not info:
        raise RuntimeError("연결된 Riot ID가 없습니다. 먼저 `/link` 하세요.")
    return info["name"], info["tag"], info.get("region","ap")

@bot.tree.command(name="vprofile", description="프로필/MMR 확인")
async def vprofile(inter: discord.Interaction):
    await inter.response.defer()
    name, tag, region = await resolve_target(inter.user, None, None)
    acc = await http_get(f"{HENRIK_BASE}/v1/account/{q(name)}/{q(tag)}")
    mmr = await http_get(f"{HENRIK_BASE}/v2/mmr/{region}/{q(name)}/{q(tag)}")
    cur = (mmr.get("data") or {}).get("current_data") or {}
    tier = cur.get("currenttierpatched") or "Unrated"
    rr   = cur.get("ranking_in_tier", 0)
    await inter.followup.send(f"{name}#{tag} • {tier} {rr}RR")

@bot.tree.command(name="vmatches", description="최근 매치 요약")
async def vmatches(inter: discord.Interaction, count: int = 5):
    await inter.response.defer()
    name, tag, region = await resolve_target(inter.user, None, None)
    acc = await http_get(f"{HENRIK_BASE}/v1/account/{q(name)}/{q(tag)}")
    puuid = (acc.get("data") or {}).get("puuid")
    js = await fetch_matches(region, name, tag, size=count)
    matches = (js.get("data") or [])
    lines = []
    for m in matches:
        players = ((m.get("players") or {}).get("all_players") or [])
        my = next((p for p in players if p.get("puuid") == puuid), None)
        stats = (my or {}).get("stats", {}) if my else {}
        k,d,a = stats.get("kills",0), stats.get("deaths",0), stats.get("assists",0)
        lines.append(f"{m['metadata']['map']} {m['metadata']['mode']} {k}/{d}/{a}")
    await inter.followup.send("\n".join(lines))

@bot.tree.command(name="vagent", description="에이전트 정보")
async def vagent(inter: discord.Interaction, name: str):
    await inter.response.defer()
    agents = await http_get(f"{VAL_ASSET}/agents", params={"isPlayableCharacter":"true"})
    arr = agents.get("data") or []
    found = next((a for a in arr if a.get("displayName","").lower() == name.lower()), None)
    if not found:
        await inter.followup.send("에이전트 없음"); return
    await inter.followup.send(found.get("displayName","Agent"))

@bot.tree.command(name="vsummary", description="최근 전적 요약 (티어/승률/KD/멘트)")
async def vsummary(inter: discord.Interaction, count: int = 10):
    await inter.response.defer()
    name, tag, region = await resolve_target(inter.user, None, None)
    acc = await http_get(f"{HENRIK_BASE}/v1/account/{q(name)}/{q(tag)}")
    puuid = (acc.get("data") or {}).get("puuid")
    mmr = await http_get(f"{HENRIK_BASE}/v2/mmr/{region}/{q(name)}/{q(tag)}")
    cur = (mmr.get("data") or {}).get("current_data") or {}
    tier_name = cur.get("currenttierpatched") or "Unrated"
    rr = cur.get("ranking_in_tier", 0)
    emoji = TIER_EMOJI.get(tier_name, ":grey_question:")

    js = await fetch_matches(region, name, tag, size=count)
    matches = (js.get("data") or [])
    wins, losses = 0, 0
    tot_k, tot_d = 0, 0
    for m in matches:
        players = ((m.get("players") or {}).get("all_players") or [])
        my = next((p for p in players if p.get("puuid") == puuid), None)
        if not my: continue
        k,d,a = (my.get("stats") or {}).get("kills",0), (my.get("stats") or {}).get("deaths",0), (my.get("stats") or {}).get("assists",0)
        tot_k += k; tot_d += d
        team = my.get("team")
        if team and isinstance(m.get("teams"), dict):
            has_won = bool(m["teams"].get(team, {}).get("has_won"))
            if has_won: wins+=1
            else: losses+=1
    total = wins+losses
    winrate = (wins/total*100) if total else 0
    kd = trunc2(tot_k/tot_d) if tot_d else float(tot_k)
    if winrate >= 50 and kd >= 1: msg = "오~ 좀 잘하는데"
    elif winrate >= 50 and kd < 1: msg = "오~ 버스 잘 타는데"
    elif winrate <= 45 and kd >= 1: msg = "이걸 지고 있네 ㅋㅋㅋㅋ"
    elif winrate <= 45 and kd < 1: msg = "개못하네 ㅋㅋㅋ 지는 이유가 있다"
    else: msg = ""
    out = (
        f"{emoji}  {rr}RR\n"
        f"{name}님의 최근 {total}판 전적 : {wins}승 {losses}패 ({winrate:.0f}%)\n"
        f"KD : {kd:.2f}\n"
        f"{msg}"
    )
    await inter.followup.send(out)

# -------------------- 실행 --------------------
if __name__ == "__main__":
    if not DISCORD_TOKEN:
        raise SystemExit("DISCORD_TOKEN 이 .env 에 없습니다")
    try:
        bot.run(DISCORD_TOKEN)
    finally:
        asyncio.run(close_session())
