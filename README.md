# 🐋 Whale Trend — Alpha Alert Bot

> **An AI-powered Telegram bot that detects mismatches between what influencers say on X/Twitter and what on-chain whales are actually doing.**

---

## ⚡ Features

| Module | Feature |
|---|---|
| **Twitter Scraper** | Monitors 15+ selected accounts, Apify & RapidAPI backend |
| **NLP Engine** | Ticker detection (e.g. $BTC), sentiment analysis, 9 thematic concepts |
| **On-Chain Tracker** | Ethereum + BSC + Solana, Etherscan/BscScan/Helius API, $100K+ transaction filter |
| **Telegram Bot** | Real-time alerts, inline buttons, channel + DM support |

### 🚨 Scenario A — EXIT WARNING
KOL posts a **bullish** tweet → Whales are sending funds to **exchanges** → **SELL signal**

### 💎 Scenario B — INSIDER ACCUMULATION
KOL shares a new **concept/narrative** → Smart money accumulates **silently** → **BUY signal**

---

## 🚀 Installation

### 1. Clone / Download Repository
```bash
cd c:\Users\kerem\Desktop\WHALETREND
```

### 2. Create Python Virtual Environment
```bash
python -m venv venv
venv\Scripts\activate        # Windows
# source venv/bin/activate   # Linux/Mac
```

### 3. Install Dependencies
```bash
pip install -r requirements.txt

# (Optional) Download spaCy model
python -m spacy download en_core_web_sm
```

### 4. Configure Environment Variables
```bash
copy .env.example .env
# Open the .env file with a text editor and fill in the API keys
```

### 5. Test Mode (No API keys required)
```bash
# Inside .env set: TWITTER_BACKEND=mock
cd bot
python main.py
```

### 6. Switch to Live Mode
```
Update .env → TWITTER_BACKEND=apify (or rapidapi)
```

---

## 🔑 API Keys

### Telegram Bot Token
1. Go to `@BotFather` on Telegram
2. Type `/newbot` → enter your bot name
3. Copy the token → paste to `.env` → `TELEGRAM_BOT_TOKEN`

### Finding Chat IDs
1. Add the bot to your channel or send it a direct message
2. Find your personal ID via `@userinfobot`
3. For channel IDs: use `@getidsbot`

### Apify (Twitter Scraper)
- [apify.com](https://apify.com) → Free registration
- Dashboard → Settings → Integrations → API Token
- Actor: `quacker/twitter-scraper` (Free tier)

### Etherscan & BscScan
- [etherscan.io/myapikey](https://etherscan.io/myapikey) → Free (100k req/day)
- [bscscan.com/myapikey](https://bscscan.com/myapikey) → Free

---

## 📁 Project Structure

```
WHALETREND/
├── bot/
│   ├── main.py              # Main orchestrator loop
│   ├── config.py            # Main configurations and lists
│   ├── twitter_scraper.py   # X/Twitter scraping
│   ├── nlp_analyzer.py      # Keyword + sentiment analysis
│   ├── onchain_tracker.py   # Whale transaction tracking
│   ├── telegram_bot.py      # Sending alerts
│   ├── database.py          # SQLite persistence & duplicate prevention
│   ├── price_tracker.py     # CoinGecko prices & trends
│   ├── alert_filter.py      # Smart deduplication & priority scoring
│   ├── wallet_tracker.py    # 28+ elite wallets database
│   ├── report_generator.py  # Daily/weekly analytics & token reports
│   └── scheduler.py         # Multi-threaded job scheduling
├── data/
│   ├── last_tweet_ids.json  # State file (auto-generated)
│   └── whalebot.log         # Core log file (auto-generated)
├── .env.example             # API keys template
├── requirements.txt         # Python dependencies
└── README.md                # Project documentation
```

---

## ⚙️ Configuration

You can customize the core settings inside `bot/config.py`:

| Setting | Description |
|---|---|
| `WATCH_ACCOUNTS` | List of X/Twitter accounts to track |
| `BULLISH_KEYWORDS` | Bullish keywords |
| `BEARISH_KEYWORDS` | Bearish keywords |
| `THEMATIC_KEYWORDS` | "AI x Crypto", "ZK", "RWA" and other thematic concepts |
| `WHALE_THRESHOLD_USD` | Minimum whale transaction size (default: $100K) |
| `SCAN_INTERVAL_MINUTES` | Scanning frequency (default: 5 minutes) |
| `EXCHANGE_ADDRESSES` | Known exchange deposit hot wallets |

---

## 📊 Example Telegram Alert

```
🚨 WHALE TREND ALERT
2026-04-02 19:45 UTC

━━━━━━━━━━━━━━━━━━━━━━━
🚨 SCENARIO A — EXIT WARNING
━━━━━━━━━━━━━━━━━━━━━━━
@elonmusk just shared a bullish tweet,
but elite whales are depositing to exchanges!

👤 Source: @elonmusk
🏷️ Tickers: $DOGE
🟢 Sentiment: BULLISH (+0.67)
🎯 Themes: Meme

💬 Tweet:
"Doge is inevitable. The people's crypto. 100x incoming!"

🔗 On-Chain Summary:
  🔴 Exchange Deposit: 3 transactions — $4,250,000
    └ Binance / ethereum / 0x7f3a8b0c1d...
    └ OKX / ethereum / 0x2e9f4a7c3b...

⚡ WhaleTrend Alpha Agent • $WHALE Hodlers Only
```

---

## 🛣️ Roadmap

- [x] **Phase 1** — Twitter scraper + NLP + On-chain + Telegram
- [x] **Phase 2** — Backend scaling (Solana, Backtesting, Wallet databases)
- [ ] **Phase 3** — Discord webhook integration & Report Generation
- [ ] **Phase 4** — Phantom/Jupiter automated inverse trading
- [ ] **Phase 5** — Web dashboard (React) implementation

---

> **Disclaimer:** This bot does not provide financial advice. Cryptocurrency investments entail high risk. Do your own research (DYOR).
