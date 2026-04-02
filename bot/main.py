"""
WhaleAlert Main Orchestrator
============================
Ana döngü: Twitter tara → NLP analiz et → On-chain kontrol et → Telegram'a gönder

Çalıştırma:
    python main.py

Ortam değişkenleri: .env dosyasından okunur (bkz. .env.example)
"""

import asyncio
import json
import logging
import os
import sys
import time
from pathlib import Path

# Projeyi PYTHONPATH'e ekle (eğer bot/ içinden çalıştırılıyorsa)
sys.path.insert(0, str(Path(__file__).parent))

from config import (
    SCAN_INTERVAL_MINUTES,
    STATE_FILE,
    LOG_LEVEL,
    WATCH_ACCOUNTS,
    WHALE_THRESHOLD_USD,
)
from twitter_scraper import TwitterScraper
from nlp_analyzer import NLPAnalyzer, AnalysisResult
from onchain_tracker import OnChainTracker, WhaleAnalysis
from telegram_bot import TelegramAlertBot

# ──────────────────────────────────────────────────────────────────────────────
# Logging
# ──────────────────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL.upper(), logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("data/whalebot.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger("whalebot.main")


# ──────────────────────────────────────────────────────────────────────────────
# State Yönetimi (Tekrarlı alert önleme)
# ──────────────────────────────────────────────────────────────────────────────

def load_state() -> dict:
    """Son işlenen tweet ID'lerini dosyadan yükler."""
    path = Path(STATE_FILE)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def save_state(state: dict) -> None:
    """Son tweet ID'lerini dosyaya kaydeder."""
    path = Path(STATE_FILE)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)


def is_new_tweet(tweet: dict, state: dict) -> bool:
    """Bu tweet daha önce işlenmediyse True döner."""
    account = tweet.get("author", "")
    tweet_id = tweet.get("id", "")
    last_id = state.get(account, "0")
    return tweet_id > last_id


def update_state(tweets: list[dict], state: dict) -> dict:
    """State'i en son tweet ID'leriyle günceller."""
    for tweet in tweets:
        account  = tweet.get("author", "")
        tweet_id = tweet.get("id", "")
        if tweet_id > state.get(account, "0"):
            state[account] = tweet_id
    return state


# ──────────────────────────────────────────────────────────────────────────────
# Mismatch Dedektörü
# ──────────────────────────────────────────────────────────────────────────────

class MismatchDetector:
    """
    NLP sonuçları ile on-chain analizi birleştirerek
    EXIT WARNING veya INSIDER ACCUMULATION kararı verir.
    """

    def __init__(self, tracker: OnChainTracker, telegram: TelegramAlertBot):
        self.tracker  = tracker
        self.telegram = telegram

    def process(self, nlp_result: AnalysisResult) -> None:
        """
        Bir NLP sonucunu işler:
         - Ticker varsa on-chain kontrol yapar
         - Mismatch varsa Telegram'a alert gönderir
         - Ticker yoksa ama tema varsa basit NLP alert'i gönderir
        """
        if not nlp_result.should_alert:
            return

        if nlp_result.tickers:
            # Her tespit edilen ticker için on-chain analiz
            for ticker in nlp_result.tickers[:3]:   # maks 3 ticker
                try:
                    onchain = self.tracker.analyze_ticker(ticker)
                    self._dispatch(nlp_result, onchain)
                except Exception as e:
                    logger.error(f"On-chain analiz hatası ({ticker}): {e}")
                    # On-chain başarısız olsa bile basit alert gönder
                    self.telegram.send_simple_alert_sync(nlp_result)
        else:
            # Ticker yok ama tema var → basit alert
            self.telegram.send_simple_alert_sync(nlp_result)

    def _dispatch(self, nlp: AnalysisResult, onchain: WhaleAnalysis) -> None:
        """Analiz sonucuna göre alert tipini belirler ve gönderir."""

        verdict = onchain.verdict

        if verdict in ("EXIT_WARNING", "INSIDER_ACCUMULATION"):
            # Tam mismatch alert
            logger.info(
                f"🎯 MISMATCH DETECTED | @{nlp.author} | "
                f"${onchain.ticker} | {verdict}"
            )
            self.telegram.send_mismatch_alert_sync(nlp, onchain)

        elif nlp.sentiment_label in ("BULLISH", "BEARISH"):
            # On-chain nötr ama güçlü NLP sinyali → basit alert
            logger.info(
                f"📡 NLP ALERT | @{nlp.author} | "
                f"${onchain.ticker} | {nlp.sentiment_label}"
            )
            self.telegram.send_simple_alert_sync(nlp)

        else:
            logger.debug(f"Nötr sinyal, alert yok: ${onchain.ticker}")


# ──────────────────────────────────────────────────────────────────────────────
# Ana Bot Döngüsü
# ──────────────────────────────────────────────────────────────────────────────

class WhaleTrendBot:
    """Ana bot orchestrator sınıfı."""

    def __init__(self):
        logger.info("🐋 WhaleAlert Bot başlatılıyor...")
        self.scraper   = TwitterScraper()
        self.analyzer  = NLPAnalyzer()
        self.tracker   = OnChainTracker()
        self.telegram  = TelegramAlertBot()
        self.detector  = MismatchDetector(self.tracker, self.telegram)
        self.state     = load_state()
        logger.info("✅ Tüm modüller hazır.")

    def run(self) -> None:
        """Ana tarama döngüsünü başlatır (sonsuza kadar çalışır)."""
        # Başlangıç bildirimi
        try:
            self.telegram.send_startup_sync()
        except Exception as e:
            logger.warning(f"Startup mesajı gönderilemedi: {e}")

        logger.info(
            f"🚀 Tarama döngüsü başlıyor | "
            f"Interval: {SCAN_INTERVAL_MINUTES} dakika | "
            f"Hesaplar: {len(WATCH_ACCOUNTS)}"
        )

        while True:
            try:
                self._scan_cycle()
            except KeyboardInterrupt:
                logger.info("Bot durduruldu (Ctrl+C)")
                break
            except Exception as e:
                logger.error(f"Döngü hatası: {e}", exc_info=True)
                time.sleep(30)   # hata durumunda 30s bekle

            logger.info(f"⏳ {SCAN_INTERVAL_MINUTES} dakika bekleniyor...")
            time.sleep(SCAN_INTERVAL_MINUTES * 60)

    def _scan_cycle(self) -> None:
        """Tek bir tarama döngüsü."""
        logger.info("🔍 Tarama başladı...")

        # 1. Tweet çekimi
        tweets = self.scraper.fetch_recent_tweets(
            since_minutes=SCAN_INTERVAL_MINUTES + 2   # biraz fazla al (overlap)
        )

        # 2. Yeni tweet filtresi
        new_tweets = [t for t in tweets if is_new_tweet(t, self.state)]
        logger.info(f"{len(new_tweets)} yeni tweet işlenecek ({len(tweets)} toplam çekildi)")

        if not new_tweets:
            logger.info("Yeni tweet yok.")
            return

        # 3. NLP analizi
        nlp_results = self.analyzer.analyze_batch(new_tweets)

        # 4. Mismatch tespiti & Telegram alert
        alert_count = 0
        for result in nlp_results:
            if result.should_alert:
                self.detector.process(result)
                alert_count += 1

        # 5. State güncelle
        self.state = update_state(new_tweets, self.state)
        save_state(self.state)

        logger.info(
            f"✅ Döngü tamamlandı | "
            f"{len(new_tweets)} tweet | "
            f"{alert_count} alert gönderildi"
        )


# ──────────────────────────────────────────────────────────────────────────────
# Giriş Noktası
# ──────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    # data/ dizinini oluştur
    Path("data").mkdir(exist_ok=True)

    bot = WhaleTrendBot()
    bot.run()
