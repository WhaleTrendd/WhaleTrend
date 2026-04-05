"""
WhaleAlert Config
================
Tüm API anahtarları, cüzdan listeleri ve anahtar kelimeler bu dosya üzerinden yönetilir.
Gerçek değerleri .env dosyasına yazın, bu dosya sadece şema/varsayılan değerler içerir.
"""

import os
from dotenv import load_dotenv

load_dotenv()

# ─────────────────────────────────────────────
# TELEGRAM
# ─────────────────────────────────────────────
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
# Bildirimlerin gönderileceği kanal/kullanıcı ID listesi
# Kanal için: "@kanaladi" veya "-100xxxxxxxxxx"
# Özel mesaj için: kullanıcının chat_id'si
TELEGRAM_CHAT_IDS = os.getenv("TELEGRAM_CHAT_IDS", "").split(",")

# ─────────────────────────────────────────────
# TWITTER / X SCRAPER
# ─────────────────────────────────────────────
# Apify (önerilen) → https://apify.com/
APIFY_API_TOKEN = os.getenv("APIFY_API_TOKEN", "")
APIFY_TWITTER_ACTOR = "quacker/twitter-scraper"   # ücretsiz aktör

# RapidAPI (yedek) → https://rapidapi.com/
RAPIDAPI_KEY = os.getenv("RAPIDAPI_KEY", "")
RAPIDAPI_HOST = "twitter-api45.p.rapidapi.com"

# Hangi backend kullanılacak: "apify" | "rapidapi" | "mock" (test için)
TWITTER_BACKEND = os.getenv("TWITTER_BACKEND", "apify")

# İzlenecek X/Twitter hesapları
WATCH_ACCOUNTS = [
    "VitalikButerin",
    "saylor",
    "elonmusk",
    "APompliano",
    "brian_armstrong",
    "cz_binance",
    "ErikVoorhees",
    "cdixon",
    "BalajiS",
    "MMCrypto",
    # Ek hesaplar buraya eklenebilir
    "CoinDesk",
    "Cointelegraph",
    "WuBlockchain",
    "lookonchain",
    "whale_alert",
]

# Kaç dakikada bir tarama yapılsın
SCAN_INTERVAL_MINUTES = int(os.getenv("SCAN_INTERVAL_MINUTES", "5"))

# ─────────────────────────────────────────────
# ON-CHAIN TRACKER
# ─────────────────────────────────────────────
# Etherscan → https://etherscan.io/apis (ücretsiz tier: 5 req/s)
ETHERSCAN_API_KEY = os.getenv("ETHERSCAN_API_KEY", "")

# BscScan → https://bscscan.com/apis
BSCSCAN_API_KEY = os.getenv("BSCSCAN_API_KEY", "")

# Solscan (Solana) → https://public-api.solscan.io
SOLSCAN_API_KEY = os.getenv("SOLSCAN_API_KEY", "")   # opsiyonel

# Birden fazla zincir desteklenir
ENABLED_CHAINS = ["ethereum", "bsc"]   # "solana" eklenebilir

# Minimum işlem büyüklüğü (USD) - bunun altındaki işlemler görmezden gelinir
WHALE_THRESHOLD_USD = int(os.getenv("WHALE_THRESHOLD_USD", "100000"))

# Borsa deposit adresleri (EXIT WARNING için)
EXCHANGE_ADDRESSES = {
    "Binance":   ["0x28c6c06298d514db089934071355e5743bf21d60",
                  "0xdfd5293d8e347dfe59e90efd55b2956a1343963d"],
    "Coinbase":  ["0xa9d1e08c7793af67e9d92fe308d5697fb81d3e43"],
    "OKX":       ["0x6cc5f688a315f3dc28a7781717a9a798a59fda7b"],
    "Bybit":     ["0xf89d7b9c864f589bbf53a82105107622b35eaa40"],
}

# ─────────────────────────────────────────────
# NLP / KEYWORD ENGINE
# ─────────────────────────────────────────────
# Ticker regex pattern ($BTC, $ETH, vb.)
TICKER_PATTERN = r"\$[A-Z]{2,10}\b"

# Önemli kavramsal anahtar kelimeler (büyük/küçük harf duyarsız)
BULLISH_KEYWORDS = [
    "accumulate", "buy", "bullish", "moon", "pump", "hodl", "load",
    "dip", "opportunity", "undervalued", "gem", "alpha", "launch",
    "listing", "partnership", "integration", "upgrade", "mainnet",
    "staking", "airdrop", "wen", "soon", "massive", "huge", "big news",
    "100x", "10x", "breakout", "support", "bounce", "rip",
    # Türkçe
    "al", "yükseliş", "fırsat", "birikim", "ucuz",
]

BEARISH_KEYWORDS = [
    "sell", "dump", "bearish", "short", "exit", "overbought",
    "scam", "rug", "ponzi", "caution", "warning", "bubble",
    "overvalued", "crash", "rekt", "liquidation", "capitulation",
    "distribution", "top", "resistance",
    # Türkçe
    "sat", "düşüş", "uyarı", "dikkat", "balon",
]

# Tematik kavramlar (Scenario B - INSIDER ACCUMULATION için)
THEMATIC_KEYWORDS = {
    "AI x Crypto":      ["ai", "artificial intelligence", "llm", "gpt", "agent", "agentic"],
    "ZK / Privacy":     ["zk", "zero knowledge", "zkp", "privacy", "zkml", "zkvm"],
    "RWA":              ["rwa", "real world asset", "tokenized", "tokenization", "treasury"],
    "DePIN":            ["depin", "decentralized physical", "iot", "sensor", "network"],
    "Layer2":           ["layer 2", "l2", "rollup", "optimistic", "zk rollup", "scaling"],
    "Restaking":        ["restaking", "eigenlayer", "avs", "lrt", "liquid restaking"],
    "Meme":             ["meme", "doge", "shib", "pepe", "viral", "community token"],
    "Gaming / NFT":     ["gamefi", "nft", "play to earn", "p2e", "metaverse", "gaming"],
    "DeFi":             ["defi", "dex", "amm", "yield", "liquidity", "tvl", "protocol"],
    "BTC Ecosystem":    ["bitcoin", "btc", "ordinals", "runes", "brc20", "sats"],
}

# Minimum sentiment skoru alert oluşturmak için (0.0 - 1.0)
SENTIMENT_THRESHOLD = float(os.getenv("SENTIMENT_THRESHOLD", "0.3"))

# ─────────────────────────────────────────────
# GENEL
# ─────────────────────────────────────────────
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
STATE_FILE = "data/last_tweet_ids.json"   # son taranan tweet ID'lerini sakla
