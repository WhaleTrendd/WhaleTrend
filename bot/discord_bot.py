"""
Discord Webhook Bot
===================
Whale Trend alert'lerini Discord kanallarına webhook üzerinden iletir.

Özellikler:
  - Rich Embed formatında renkli mesajlar
  - Senaryo A/B için farklı renk şemaları (kırmızı/yeşil)
  - Birden fazla Discord webhook URL desteği
  - Thumbnail olarak token logosu ekleme (CoinGecko CDN)
  - @here / @everyone mention desteği (kritik alert'ler için)
  - Rate limiting: Discord 30 mesaj/dakika limiti
  - Retry on 429 (Too Many Requests)
"""

import time
import logging
import requests
from datetime import datetime, timezone
from typing import Optional

from config import SENTINEL_CONFIG_PLACEHOLDER as _  # noqa — henuz entegre edilmedi

logger = logging.getLogger(__name__)

# ── Discord Webhook URL'leri (.env'den okunacak) ──────────────────────────────
DISCORD_WEBHOOKS: list[str] = []   # örn: ["https://discord.com/api/webhooks/xxx/yyy"]
DISCORD_RATE_LIMIT_DELAY = 2.1     # saniye (güvenli aralık)

# Embed renk kodları (Discord decimal color)
COLOR_EXIT_WARNING        = 0xFF4444   # kırmızı
COLOR_INSIDER_ACCUM       = 0x00FF88   # yeşil
COLOR_NLP_BULLISH         = 0x44AAFF   # mavi
COLOR_NLP_BEARISH         = 0xFF8800   # turuncu
COLOR_NEUTRAL             = 0x888888   # gri

# CoinGecko token logo URL şablonu
TOKEN_LOGO_URL = "https://assets.coingecko.com/coins/images/{cg_id}/small/{slug}.png"


class DiscordAlertBot:
    """
    Discord Webhook üzerinden Whale Trend alert'leri gönderir.
    """

    def __init__(self, webhook_urls: list[str] = None):
        self.webhooks = webhook_urls or DISCORD_WEBHOOKS
        self.session  = requests.Session()
        self._last_sent: float = 0.0
        logger.info(f"DiscordBot baslatildi → {len(self.webhooks)} webhook")

    # ── Public API ─────────────────────────────────────────────────────────────

    def send_mismatch_alert(
        self,
        author: str,
        ticker: str,
        sentiment: str,
        verdict: str,
        tweet_text: str,
        tweet_url: str,
        exit_usd: float = 0,
        accum_usd: float = 0,
        themes: list[str] = None,
    ) -> bool:
        """Senaryo A/B embed mesajı gönderir."""
        color   = self._verdict_color(verdict)
        title   = self._verdict_title(verdict)
        mention = "@here " if verdict == "EXIT_WARNING" else ""

        embed = {
            "title":       f"{title} — ${ticker}",
            "description": f"{mention}**@{author}** tarafından tespit edildi",
            "color":       color,
            "timestamp":   datetime.now(timezone.utc).isoformat(),
            "fields": [
                {"name": "Sentiment",    "value": sentiment,                         "inline": True},
                {"name": "Ticker",       "value": f"`${ticker}`",                    "inline": True},
                {"name": "Temalar",      "value": ", ".join(themes) if themes else "—", "inline": True},
                {"name": "Tweet",        "value": f"[Goruntule]({tweet_url})\n_{tweet_text[:200]}_", "inline": False},
            ],
            "footer": {"text": "WhaleTrend Alpha Agent • Sadece $WHALE Hodler'larina"},
        }

        if verdict == "EXIT_WARNING" and exit_usd:
            embed["fields"].append({
                "name": "Borsa Deposit",
                "value": f"${exit_usd:,.0f}",
                "inline": True,
            })
        if verdict == "INSIDER_ACCUMULATION" and accum_usd:
            embed["fields"].append({
                "name": "Birikim Toplami",
                "value": f"${accum_usd:,.0f}",
                "inline": True,
            })

        return self._broadcast({"embeds": [embed]})

    def send_daily_summary(self, stats: dict) -> bool:
        """Günlük özet embed'i gönderir."""
        embed = {
            "title":       "Whale Trend — Gunluk Ozet",
            "description": f"Bugunun sinyal raporu",
            "color":       COLOR_NLP_BULLISH,
            "timestamp":   datetime.now(timezone.utc).isoformat(),
            "fields": [
                {"name": "Toplam Alert",     "value": str(stats.get("total", 0)),          "inline": True},
                {"name": "Exit Warning",     "value": str(stats.get("exit_count", 0)),     "inline": True},
                {"name": "Insider Birikim",  "value": str(stats.get("accum_count", 0)),    "inline": True},
                {"name": "En Aktif Token",   "value": stats.get("top_ticker", "—"),        "inline": True},
            ],
            "footer": {"text": "WhaleTrend Alpha Agent"},
        }
        return self._broadcast({"embeds": [embed]})

    # ── Internal ───────────────────────────────────────────────────────────────

    def _broadcast(self, payload: dict) -> bool:
        success = True
        for url in self.webhooks:
            try:
                self._rate_limit_wait()
                resp = self.session.post(url, json=payload, timeout=10)
                if resp.status_code == 429:
                    retry_after = resp.json().get("retry_after", 5)
                    logger.warning(f"Discord rate limit → {retry_after}s bekleniyor")
                    time.sleep(retry_after)
                    resp = self.session.post(url, json=payload, timeout=10)
                resp.raise_for_status()
                self._last_sent = time.time()
                logger.debug(f"Discord mesaj gonderildi → {url[:40]}...")
            except Exception as e:
                logger.error(f"Discord webhook hatasi: {e}")
                success = False
        return success

    def _rate_limit_wait(self):
        elapsed = time.time() - self._last_sent
        if elapsed < DISCORD_RATE_LIMIT_DELAY:
            time.sleep(DISCORD_RATE_LIMIT_DELAY - elapsed)

    @staticmethod
    def _verdict_color(verdict: str) -> int:
        return {
            "EXIT_WARNING":        COLOR_EXIT_WARNING,
            "INSIDER_ACCUMULATION":COLOR_INSIDER_ACCUM,
            "NEUTRAL":             COLOR_NEUTRAL,
        }.get(verdict, COLOR_NEUTRAL)

    @staticmethod
    def _verdict_title(verdict: str) -> str:
        return {
            "EXIT_WARNING":        "CIKIS UYARISI",
            "INSIDER_ACCUMULATION":"INSIDER BIRIKIMI",
        }.get(verdict, "SINYAL")
