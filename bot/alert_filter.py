"""
Alert Filter & Deduplication Engine
=====================================
Akıllı filtre sistemi:

  1. Cooldown Koruması   — Aynı ticker için N dakika içinde tekrar alert yok
  2. Min Engagement      — Düşük etkileşimli tweetleri filtreler
  3. Spam Hesap Listesi  — Bilinen spam/bot hesapları gizler
  4. Priority Scoring    — Önemli hesaplara daha yüksek öncelik atar
  5. Rate Limiting       — Dakikada maks N alert gönderir (Telegram flood önleme)
  6. Smart Dedup         — Aynı tweetin farklı backend'den çift gelmesini önler
"""

import time
import logging
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Optional

from nlp_analyzer import AnalysisResult

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────────────
# Konfigürasyon
# ──────────────────────────────────────────────────────────────────────────────

# Aynı ticker için tekrar alert gönderilmeyecek süre (dakika)
TICKER_COOLDOWN_MINUTES = 30

# Aynı hesap için tekrar alert gönderilmeyecek süre (dakika)
ACCOUNT_COOLDOWN_MINUTES = 15

# Bir dakikada gönderilebilecek maksimum alert sayısı
MAX_ALERTS_PER_MINUTE = 5

# Minimum tweet etkileşim skoru (likes + retweets*3)
MIN_ENGAGEMENT_SCORE = 0

# Hesap öncelik skorları (1-10, yüksek = daha önemli)
ACCOUNT_PRIORITY: dict[str, int] = {
    "VitalikButerin": 10,
    "saylor":         10,
    "elonmusk":       9,
    "brian_armstrong":8,
    "cz_binance":     8,
    "APompliano":     7,
    "cdixon":         7,
    "BalajiS":        7,
    "ErikVoorhees":   6,
    "MMCrypto":       6,
    "lookonchain":    9,   # on-chain alpha kaynağı
    "whale_alert":    9,   # whale hareketi kaynağı
    "WuBlockchain":   8,
    "CoinDesk":       6,
    "Cointelegraph":  6,
}

# Bilinen spam/bot hesapları (bunlardan alert gönderilmez)
SPAM_ACCOUNTS: set[str] = {
    "cryptogiveaway", "airdrop_news", "free_btc_bot",
    "pumpgroup", "pumpannounce",
}

# Sentiment gücü için minimum eşik
MIN_SENTIMENT_ABS = 0.2

# Minimum ticker sayısı — ticker yoksa sadece tema varsa da alertleyelim
MIN_ALERT_CONDITION_MET = True   # True → ticker VEYA tema yeterli


# ──────────────────────────────────────────────────────────────────────────────
# Filtre Sonucu
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class FilterResult:
    allowed:        bool
    reason:         str        # reddedildiyse neden
    priority_score: float = 0.0
    boosted:        bool  = False   # VIP hesap boost'u uygulandı mı


# ──────────────────────────────────────────────────────────────────────────────
# Alert Filtre Motoru
# ──────────────────────────────────────────────────────────────────────────────

class AlertFilter:
    """
    Her alert adayını çeşitli filtrelerden geçirir.
    Yalnızca kaliteli, tekil, önemli sinyaller iletilir.
    """

    def __init__(self):
        # {ticker: last_alert_timestamp}
        self._ticker_cooldowns:  dict[str, float] = {}
        # {account: last_alert_timestamp}
        self._account_cooldowns: dict[str, float] = {}
        # Son 1 dakika içinde gönderilen alert timestampları
        self._rate_window: deque[float] = deque()
        # İşlenmiş tweet ID seti (duplicate önleme)
        self._seen_tweet_ids: set[str] = set()
        # İstatistikler
        self._stats = defaultdict(int)

        logger.info("AlertFilter baslatildi")

    # ── Ana Kontrol ────────────────────────────────────────────────────────────

    def should_alert(
        self,
        result: AnalysisResult,
        tweet: dict,
    ) -> FilterResult:
        """
        Bir NLP sonucu için alert gönderilip gönderilmeyeceğine karar verir.
        """
        tweet_id = tweet.get("id", "")
        account  = result.author.lower()

        # 1. Spam hesap kontrolü
        if account in SPAM_ACCOUNTS:
            return self._reject("spam_account")

        # 2. Duplicate tweet kontrolü
        if tweet_id in self._seen_tweet_ids:
            return self._reject("duplicate_tweet")

        # 3. NLP eşiği — ticker veya tema yoksa geç
        has_ticker = bool(result.tickers)
        has_theme  = bool(result.themes)
        if not has_ticker and not has_theme:
            return self._reject("no_ticker_or_theme")

        # 4. Sentiment gücü
        if abs(result.sentiment_score) < MIN_SENTIMENT_ABS and not has_theme:
            return self._reject("sentiment_too_weak")

        # 5. Minimum engagement skoru
        engagement = (
            tweet.get("likes", 0) +
            tweet.get("retweets", 0) * 3
        )
        if engagement < MIN_ENGAGEMENT_SCORE:
            return self._reject("low_engagement")

        # 6. Ticker cooldown
        for ticker in result.tickers:
            if self._is_ticker_on_cooldown(ticker):
                return self._reject(f"ticker_cooldown:{ticker}")

        # 7. Hesap cooldown (VIP hesaplara indirim)
        priority = ACCOUNT_PRIORITY.get(result.author, 5)
        cooldown_minutes = ACCOUNT_COOLDOWN_MINUTES
        if priority >= 9:
            cooldown_minutes = cooldown_minutes // 3   # VIP → daha sık alert
        if self._is_account_on_cooldown(result.author, cooldown_minutes):
            return self._reject(f"account_cooldown:{result.author}")

        # 8. Rate limiting (dakikada maks N alert)
        if not self._check_rate_limit():
            return self._reject("rate_limit")

        # ── Geçti: priority skoru hesapla ve onayla ─────────────────────────
        score = self._compute_priority_score(result, tweet, priority)
        self._mark_allowed(tweet_id, result.author, result.tickers)

        return FilterResult(
            allowed        = True,
            reason         = "passed",
            priority_score = score,
            boosted        = priority >= 8,
        )

    # ── Cooldown Yönetimi ──────────────────────────────────────────────────────

    def _is_ticker_on_cooldown(self, ticker: str) -> bool:
        last = self._ticker_cooldowns.get(ticker, 0)
        return (time.time() - last) < (TICKER_COOLDOWN_MINUTES * 60)

    def _is_account_on_cooldown(self, account: str, minutes: int) -> bool:
        last = self._account_cooldowns.get(account.lower(), 0)
        return (time.time() - last) < (minutes * 60)

    def _mark_allowed(self, tweet_id: str, author: str, tickers: list[str]):
        now = time.time()
        self._seen_tweet_ids.add(tweet_id)
        self._account_cooldowns[author.lower()] = now
        for t in tickers:
            self._ticker_cooldowns[t] = now
        self._rate_window.append(now)
        self._stats["allowed"] += 1

    # ── Rate Limiting ──────────────────────────────────────────────────────────

    def _check_rate_limit(self) -> bool:
        """Dakika başına maks alert sayısını kontrol eder."""
        now = time.time()
        cutoff = now - 60
        while self._rate_window and self._rate_window[0] < cutoff:
            self._rate_window.popleft()
        return len(self._rate_window) < MAX_ALERTS_PER_MINUTE

    # ── Priority Score ─────────────────────────────────────────────────────────

    @staticmethod
    def _compute_priority_score(
        result: AnalysisResult,
        tweet: dict,
        account_priority: int,
    ) -> float:
        """
        0-100 arası öncelik skoru hesaplar.
        Yüksek skor = daha önemli sinyal.
        """
        score = 0.0

        # Hesap önceliği (0-40 puan)
        score += account_priority * 4

        # Sentiment gücü (0-20 puan)
        score += abs(result.sentiment_score) * 20

        # Tema sayısı (0-15 puan)
        score += min(len(result.themes) * 5, 15)

        # Ticker sayısı (0-10 puan)
        score += min(len(result.tickers) * 5, 10)

        # Etkileşim (0-15 puan)
        engagement = tweet.get("likes", 0) + tweet.get("retweets", 0) * 3
        score += min(engagement / 10000 * 15, 15)

        return round(min(score, 100), 1)

    # ── Reddetme ──────────────────────────────────────────────────────────────

    def _reject(self, reason: str) -> FilterResult:
        self._stats[f"rejected_{reason}"] += 1
        logger.debug(f"Alert reddedildi: {reason}")
        return FilterResult(allowed=False, reason=reason)

    # ── İstatistikler ──────────────────────────────────────────────────────────

    def get_stats(self) -> dict:
        return dict(self._stats)

    def reset_cooldowns(self):
        """Test/debug için cooldown'ları sıfırlar."""
        self._ticker_cooldowns.clear()
        self._account_cooldowns.clear()
        self._rate_window.clear()
        logger.info("Cooldown'lar sifirlandi")


# ──────────────────────────────────────────────────────────────────────────────
# Test
# ──────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    from nlp_analyzer import NLPAnalyzer

    analyzer = NLPAnalyzer()
    filt     = AlertFilter()

    tweets = [
        {
            "id": "001", "author": "VitalikButerin",
            "text": "$ETH ZK rollups are incredible. Accumulate now. Huge bull run coming.",
            "url": "https://twitter.com/test/001", "likes": 50000, "retweets": 8000,
        },
        {
            "id": "002", "author": "elonmusk",
            "text": "$DOGE is the future. 100x. AI x crypto is here.",
            "url": "https://twitter.com/test/002", "likes": 200000, "retweets": 40000,
        },
        {
            "id": "002",   # tekrar — duplicate
            "author": "elonmusk",
            "text": "$DOGE is the future. 100x. AI x crypto is here.",
            "url": "https://twitter.com/test/002", "likes": 200000, "retweets": 40000,
        },
        {
            "id": "003", "author": "randomguy123",
            "text": "I think maybe $BTC could possibly go up if conditions permit.",
            "url": "https://twitter.com/test/003", "likes": 2, "retweets": 0,
        },
    ]

    for tweet in tweets:
        result = analyzer.analyze(tweet)
        decision = filt.should_alert(result, tweet)
        status = "IZIN" if decision.allowed else "RED"
        print(
            f"[{status:4}] @{tweet['author']} | "
            f"score={decision.priority_score} | "
            f"reason={decision.reason}"
        )

    print(f"\nIstatistikler: {filt.get_stats()}")
