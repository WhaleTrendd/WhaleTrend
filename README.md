# 🐋 Whale Trend — Alpha Alert Bot

> **X/Twitter'da söylenenler ile on-chain whale hareketleri arasındaki uyumsuzluğu tespit eden yapay zeka destekli Telegram botu.**

---

## ⚡ Özellikler

| Modül | Özellik |
|---|---|
| **Twitter Scraper** | 15+ seçili hesap izleme, Apify & RapidAPI backend |
| **NLP Motoru** | Ticker tespiti ($BTC vb.), sentiment analizi, 9 tematik konsept |
| **On-Chain Tracker** | Ethereum + BSC, Etherscan/BscScan API, $100K+ işlem filtresi |
| **Telegram Bot** | Anlık alert, inline butonlar, kanal + DM desteği |

### 🚨 Senaryo A — EXIT WARNING
KOL **bullish** tweet → Whale'ler borsaya **para gönderiyor** → **SATIŞ sinyali**

### 💎 Senaryo B — INSIDER ACCUMULATION
KOL yeni **konsept paylaşıyor** → Smart money **sessizce biriktiriyor** → **ALIM sinyali**

---

## 🚀 Kurulum

### 1. Depoyu Klonla / İndir
```
cd c:\Users\kerem\Desktop\WHALETREND
```

### 2. Python Sanal Ortamı
```bash
python -m venv venv
venv\Scripts\activate        # Windows
# source venv/bin/activate   # Linux/Mac
```

### 3. Bağımlılıkları Kur
```bash
pip install -r requirements.txt

# (Opsiyonel) spaCy modeli
python -m spacy download en_core_web_sm
```

### 4. Ortam Değişkenlerini Ayarla
```bash
copy .env.example .env
# .env dosyasını bir metin editörüyle açın ve API anahtarlarını doldurun
```

### 5. Test Modu (API anahtarı gerekmez)
```bash
# .env içinde: TWITTER_BACKEND=mock
cd bot
python main.py
```

### 6. Canlı Moda Geç
```
.env → TWITTER_BACKEND=apify  (veya rapidapi)
```

---

## 🔑 API Anahtarları

### Telegram Bot Token
1. Telegram'da `@BotFather`'a git
2. `/newbot` komutu → bot adını gir
3. Token'ı kopyala → `.env` → `TELEGRAM_BOT_TOKEN`

### Chat ID Bulma
1. Botunu bir kanala ekle veya botla konuş
2. `@userinfobot` ile kendi ID'ni öğren
3. Kanal ID için: `@getidsbot`

### Apify (Twitter Scraper)
- [apify.com](https://apify.com) → Ücretsiz kayıt
- Dashboard → Settings → Integrations → API Token
- Aktör: `quacker/twitter-scraper` (ücretsiz)

### Etherscan & BscScan
- [etherscan.io/myapikey](https://etherscan.io/myapikey) → Ücretsiz (100k req/gün)
- [bscscan.com/myapikey](https://bscscan.com/myapikey) → Ücretsiz

---

## 📁 Proje Yapısı

```
WHALETREND/
├── bot/
│   ├── main.py              # Ana orchestrator döngüsü
│   ├── config.py            # Tüm ayarlar ve listeler
│   ├── twitter_scraper.py   # X/Twitter tarama
│   ├── nlp_analyzer.py      # Keyword + sentiment analizi
│   ├── onchain_tracker.py   # Whale işlem takibi
│   └── telegram_bot.py      # Alert gönderme
├── data/
│   ├── last_tweet_ids.json  # State dosyası (otomatik)
│   └── whalebot.log         # Log dosyası (otomatik)
├── .env.example             # API anahtarı şablonu
├── requirements.txt
└── README.md
```

---

## ⚙️ Konfigürasyon

`bot/config.py` üzerinden aşağıdakileri özelleştirebilirsiniz:

| Ayar | Açıklama |
|---|---|
| `WATCH_ACCOUNTS` | İzlenecek X/Twitter hesapları |
| `BULLISH_KEYWORDS` | Bullish anahtar kelimeler (TR + EN) |
| `BEARISH_KEYWORDS` | Bearish anahtar kelimeler (TR + EN) |
| `THEMATIC_KEYWORDS` | "AI x Crypto", "ZK", "RWA" vb. konseptler |
| `WHALE_THRESHOLD_USD` | Minimum işlem büyüklüğü (default: $100K) |
| `SCAN_INTERVAL_MINUTES` | Tarama sıklığı (default: 5 dakika) |
| `EXCHANGE_ADDRESSES` | Borsa deposit adresleri |

---

## 📊 Örnek Telegram Alert

```
🚨 WHALE TREND ALERT
2026-04-02 19:45 UTC

━━━━━━━━━━━━━━━━━━━━━━━
🚨 SCENARIO A — EXIT WARNING
━━━━━━━━━━━━━━━━━━━━━━━
@elonmusk bullish tweet attı,
ama elit whaleler borsaya para gönderiyor!

👤 Kaynak: @elonmusk
🏷️ Ticker(lar): $DOGE
🟢 Sentiment: BULLISH (+0.67)
🎯 Temalar: Meme

💬 Tweet:
"Doge is inevitable. The people's crypto. 100x incoming!"

🔗 On-Chain Özet:
  🔴 Borsa Deposit: 3 işlem — $4,250,000
    └ Binance / ethereum / 0x7f3a8b0c1d...
    └ OKX / ethereum / 0x2e9f4a7c3b...

⚡ WhaleTrend Alpha Agent • Sadece $WHALE hodlerlarına
```

---

## 🛣️ Yol Haritası

- [x] **Faz 1** — Twitter tarama + NLP + On-chain + Telegram
- [ ] **Faz 2** — Solana desteği + CoinGecko fiyat entegrasyonu
- [ ] **Faz 3** — Discord webhook desteği
- [ ] **Faz 4** — Phantom/Jupiter otomatik trade entegrasyonu
- [ ] **Faz 5** — Web dashboard (React)

---

> **Uyarı:** Bu bot yatırım tavsiyesi vermez. Kripto yatırımları yüksek risk içerir. Kendi araştırmanızı yapın (DYOR).
