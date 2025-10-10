# Valorant Discord Bot 🎮

A Discord bot to easily check Valorant stats directly in your server.  
This project is **unofficial** and uses the [HenrikDev API](https://docs.henrikdev.xyz/).

> ⚠️ Data is provided by HenrikDev API. You must request your own API key. See [HenrikDev Docs](https://docs.henrikdev.xyz/).

---

## ✨ Features

- `/link` : Link your Riot ID to the bot
- `/unlink` : Unlink Riot ID
- `/vprofile` : View profile and MMR of the linked Riot ID
- `/vmatches` : Show recent matches with map/mode/W-L/KDA summary
- `/vsummary` : Show summarized stats (win rate, KD, tier image, fun comment)
- `/vagent` : Get information about agents
- `/resync` : Force resync of slash commands (owner only)

---

## 🛠️ Installation & Usage

### 1. Clone repository
```bash
git clone https://github.com/yourname/discord-bot.git
cd discord-bot
```

### 2. Create & activate virtual environment

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

### 4. Environment variables
Create a `.env` file in the project root:
```env
DISCORD_TOKEN=your_discord_bot_token
HENRIK_API_KEY=your_henrikdev_api_key
```

> ⚠️ You **must** request an API key from HenrikDev to use this bot.  
> [HenrikDev Docs](https://docs.henrikdev.xyz/)

### 5. Run the bot
```bash
python -u main.py
```

---

## 📂 Project Structure

```
discord_bot/
├─ main.py               # main bot entrypoint
├─ requirements.txt      # Python dependencies
├─ .env                  # tokens and API keys (excluded via .gitignore)
├─ data/                 # runtime data (bot.sqlite3 etc.)
├─ assets/
│   └─ tiers/            # tier images (radiant.png, diamond1.png ...)
└─ README.md             # project readme
```

---

## ✅ TODO

- [ ] Refactor code into `cogs/` modules
- [ ] Improve `/vmatches` output (highlight W/L)
- [ ] Add KD / win rate graphs
- [ ] Add `/agentstats`, `/compare` commands
- [ ] Stronger error handling for HenrikDev API
- [ ] Add deployment pipeline (Docker/GitHub Actions)

---

## ⚠️ Notes

- This project is **unofficial**.  
- Riot Games is not affiliated with this bot.  
- `.env` and `data/` files must never be committed to git.  
- HenrikDev API may change or enforce stricter rate limits in the future.

---

## 🧾 Credits

- Code generated with assistance from **ChatGPT (OpenAI)**.  
- Data provided by **HenrikDev API**.
