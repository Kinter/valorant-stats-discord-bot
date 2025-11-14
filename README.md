# Valorant Discord Bot

A Discord bot to check Valorant stats directly in your server.  
This project is **unofficial** and uses the [HenrikDev API](https://docs.henrikdev.xyz/).

> Data is provided by HenrikDev API. You must request your own API key. See the [HenrikDev docs](https://docs.henrikdev.xyz/).

---

## Features

- `/별명등록` (legacy `/register`) : Register a Riot ID under a shared alias (required for stat commands)
- `/별명삭제` (legacy `/unregister`) : Remove a previously registered alias
- `/별명목록` (legacy `/aliases`) : List registered aliases
- `/프로필` (legacy `/vprofile`) : View profile and MMR for a registered alias
- `/최근경기` (legacy `/vmatches`) : Show recent matches with map/mode/W-L/KDA summary (alias based)
- `/최근전적요약` (legacy `/vsummary`) : Show summarized stats (win rate, KD, tier image, fun comment)
- `/요원정보` (legacy `/vagent`) : Get information about agents
- `/명령동기화` (legacy `/resync`) : Force resync of slash commands (owner only)
- `/알림채널설정` / `/알림채널해제` : Configure live match alert channels for the server

---

## Installation & Usage

### 1. Clone the repository

```bash
git clone https://github.com/yourname/discord-bot.git
cd discord-bot
```

### 2. Create & activate a virtual environment

**Windows PowerShell**

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
```

**Linux/Mac**

```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure environment variables

Create a `.env` file in the project root:

```env
DISCORD_TOKEN=your_discord_bot_token
HENRIK_API_KEY=your_henrikdev_api_key
# Optional: DEBUG / INFO / WARNING / ERROR / CRITICAL
LOG_LEVEL=INFO
```

Set `LOG_LEVEL=DEBUG` if you need more verbose console logs while running the bot.

> You **must** request an API key from HenrikDev to use this bot.

### 5. Run the bot

```bash
python -m bot.py
```

### 6. Register aliases

Use `/별명등록 alias name tag region` in Discord to store a Riot ID under a friendly alias.
All stat commands (`/최근전적요약`, `/프로필`, `/최근경기`; legacy `/vsummary`, `/vprofile`, `/vmatches`) now require an alias.
Each fetch caches the latest match data in `data/bot.sqlite3` for later inspection.

---

## Project Structure

```
valorant-stats-discord-bot/
|-- bot.py               # main bot entrypoint
|-- requirements.txt     # Python dependencies
|-- .env                 # tokens and API keys (gitignored)
|-- data/                # runtime data (bot.sqlite3 etc.)
|-- assets/
|   `-- tiers/           # tier images (radiant.png, diamond1.png ...)
`-- README.md            # project readme
```

---

## Notes
### Remaining ideas / backlog
- Improve `/최근경기` output (highlight W/L)
- Add KD / win rate graphs
- Add `/agentstats`, `/compare` commands
- Strengthen HenrikDev API error handling
- Add context menu flow for quick alias lookups
- Refine `/최근전적요약` output highlighting (summaries, player name emphasis)
- Document existing Docker & CI workflow ownership

---

## Notes

- This project is **unofficial**.  
- Riot Games is not affiliated with this bot.  
- `.env` and `data/` files must never be committed to git.  
- HenrikDev API may change or enforce stricter rate limits in the future.

---

## Credits

- Code generated with assistance from **ChatGPT (OpenAI)**.  
- Data provided by **HenrikDev API**.
