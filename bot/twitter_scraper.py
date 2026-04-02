"""
Twitter / X Scraper
===================
Apify (birincil) veya RapidAPI (yedek) üzerinden seçili hesapların
son tweetlerini çeker.

Backends:
  - "apify"   → Apify quacker/twitter-scraper aktörü (ücretsiz kota var)
  - "rapidapi"→ twitter-api45.p.rapidapi.com
  - "mock"    → Test verisi döndürür (API anahtarı yokken)
"""

import json
import time
import logging
import requests
from datetime import datetime, timezone, timedelta
from typing import Optional

from config import (
    APIFY_API_TOKEN, APIFY_TWITTER_ACTOR,
    RAPIDAPI_KEY, RAPIDAPI_HOST,
    TWITTER_BACKEND, WATCH_ACCOUNTS,
)

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────────────
# Ana Scraper Sınıfı
# ──────────────────────────────────────────────────────────────────────────────
class TwitterScraper:
    """Seçili X/Twitter hesaplarından son tweetleri çeker."""

    def __init__(self):
        self.backend = TWITTER_BACKEND
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "WhaleAlert-Bot/1.0"})
        logger.info(f"Twitter scraper başlatıldı → backend: {self.backend}")

    # ── Public API ─────────────────────────────────────────────────────────────

    def fetch_recent_tweets(
        self,
        accounts: list[str] = None,
        since_minutes: int = 10,
        max_tweets_per_account: int = 20,
    ) -> list[dict]:
        """
        accounts listesindeki hesapların son <since_minutes> dakikadaki
        tweetlerini döndürür.

        Her tweet dict'i şu alanları içerir:
          id, author, text, created_at, url, likes, retweets
        """
        accounts = accounts or WATCH_ACCOUNTS
        since_dt = datetime.now(timezone.utc) - timedelta(minutes=since_minutes)
        all_tweets: list[dict] = []

        for account in accounts:
            try:
                tweets = self._fetch_for_account(
                    account, since_dt, max_tweets_per_account
                )
                all_tweets.extend(tweets)
                logger.debug(f"@{account}: {len(tweets)} tweet çekildi")
                time.sleep(0.5)   # rate-limit dostu bekleme
            except Exception as e:
                logger.warning(f"@{account} çekilirken hata: {e}")

        logger.info(f"Toplam {len(all_tweets)} yeni tweet çekildi ({len(accounts)} hesap)")
        return all_tweets

    # ── Backend Yönlendirici ────────────────────────────────────────────────────

    def _fetch_for_account(
        self, account: str, since_dt: datetime, max_count: int
    ) -> list[dict]:
        if self.backend == "apify":
            return self._apify_fetch(account, since_dt, max_count)
        elif self.backend == "rapidapi":
            return self._rapidapi_fetch(account, since_dt, max_count)
        elif self.backend == "mock":
            return self._mock_fetch(account)
        else:
            raise ValueError(f"Bilinmeyen backend: {self.backend}")

    # ── Apify Backend ──────────────────────────────────────────────────────────

    def _apify_fetch(
        self, account: str, since_dt: datetime, max_count: int
    ) -> list[dict]:
        """
        Apify Twitter Scraper aktörünü çalıştırır.
        Aktör: https://apify.com/quacker/twitter-scraper
        """
        run_url = (
            f"https://api.apify.com/v2/acts/{APIFY_TWITTER_ACTOR}/run-sync-get-dataset-items"
            f"?token={APIFY_API_TOKEN}&timeout=60"
        )
        payload = {
            "searchTerms": [f"from:{account}"],
            "maxItems": max_count,
            "addUserInfo": False,
        }
        resp = self.session.post(run_url, json=payload, timeout=90)
        resp.raise_for_status()
        raw_items = resp.json()

        tweets = []
        for item in raw_items:
            created = self._parse_dt(item.get("created_at") or item.get("createdAt"))
            if created and created < since_dt:
                continue
            tweets.append(self._normalize_apify(item, account))
        return tweets

    def _normalize_apify(self, item: dict, account: str) -> dict:
        return {
            "id":         str(item.get("id") or item.get("tweetId") or ""),
            "author":     account,
            "text":       item.get("text") or item.get("full_text") or "",
            "created_at": item.get("created_at") or item.get("createdAt") or "",
            "url":        f"https://twitter.com/{account}/status/{item.get('id','')}",
            "likes":      item.get("likeCount") or item.get("favorite_count") or 0,
            "retweets":   item.get("retweetCount") or item.get("retweet_count") or 0,
        }

    # ── RapidAPI Backend ───────────────────────────────────────────────────────

    def _rapidapi_fetch(
        self, account: str, since_dt: datetime, max_count: int
    ) -> list[dict]:
        """
        RapidAPI twitter-api45 endpoint'i kullanır.
        Endpoint: https://rapidapi.com/apigeek0/api/twitter-api45
        """
        url = f"https://{RAPIDAPI_HOST}/timeline.php"
        headers = {
            "X-RapidAPI-Key":  RAPIDAPI_KEY,
            "X-RapidAPI-Host": RAPIDAPI_HOST,
        }
        params = {"screenname": account}
        resp = self.session.get(url, headers=headers, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()

        raw_tweets = data.get("timeline") or data.get("tweets") or []
        tweets = []
        for item in raw_tweets[:max_count]:
            created = self._parse_dt(item.get("created_at"))
            if created and created < since_dt:
                continue
            tweets.append({
                "id":         str(item.get("tweet_id") or item.get("id") or ""),
                "author":     account,
                "text":       item.get("text") or "",
                "created_at": item.get("created_at") or "",
                "url":        f"https://twitter.com/{account}/status/{item.get('tweet_id','')}",
                "likes":      item.get("favorites") or 0,
                "retweets":   item.get("retweets") or 0,
            })
        return tweets

    # ── Mock Backend (test) ────────────────────────────────────────────────────

    def _mock_fetch(self, account: str) -> list[dict]:
        """Gerçek API olmadan test için sahte tweet verisi üretir."""
        import random
        now = datetime.now(timezone.utc).isoformat()
        samples = [
            f"Huge opportunity in $ETH right now. ZK rollups are the future. Accumulate! #crypto",
            f"Bitcoin ($BTC) is looking extremely bullish — institutional demand is insane.",
            f"Don't sleep on $SOL. AI x Crypto narrative is just getting started. 100x incoming.",
            f"Warning: $TOKEN whales just moved 50M to Binance. Exit signal? #whale #alert",
            f"DePIN is the next mega trend. $GRASS $IO showing insider accumulation patterns.",
            f"RWA tokenization is now real. $ONDO $POLYX breaking out. Mismatch detected.",
        ]
        return [{
            "id":         str(random.randint(10**17, 10**18)),
            "author":     account,
            "text":       random.choice(samples),
            "created_at": now,
            "url":        f"https://twitter.com/{account}/status/123456789",
            "likes":      random.randint(100, 50000),
            "retweets":   random.randint(10, 5000),
        }]

    # ── Yardımcı ───────────────────────────────────────────────────────────────

    @staticmethod
    def _parse_dt(s: Optional[str]) -> Optional[datetime]:
        if not s:
            return None
        formats = [
            "%a %b %d %H:%M:%S %z %Y",   # Twitter klasik format
            "%Y-%m-%dT%H:%M:%S%z",
            "%Y-%m-%dT%H:%M:%SZ",
        ]
        for fmt in formats:
            try:
                dt = datetime.strptime(s, fmt)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                return dt
            except ValueError:
                pass
        return None
