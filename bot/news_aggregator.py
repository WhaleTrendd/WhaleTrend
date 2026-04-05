"""
Crypto News Aggregator
=======================
RSS ve REST API üzerinden kripto haber kaynaklarını tarar.
Haber başlıklarından ticker ve tema çıkarır, NLP motoru ile entegre çalışır.

Haber Kaynakları (Ücretsiz):
  - CoinDesk       → https://www.coindesk.com/arc/outboundfeeds/rss/
  - Cointelegraph  → https://cointelegraph.com/rss
  - The Block      → https://www.theblock.co/rss.xml
  - Decrypt        → https://decrypt.co/feed
  - Bitcoin.com    → https://news.bitcoin.com/feed/
  - DL News        → https://dlnews.com/arc/outboundfeeds/rss/
  - CryptoSlate    → https://cryptoslate.com/feed/

Entegrasyon:
  Haberler tweet gibi işlenir → NLP analizi → Telegram alert
  KOL tweet'i + haber başlığı aynı tokenden bahsediyorsa → güçlü sinyal
"""

import logging
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Optional
import requests

from nlp_analyzer import NLPAnalyzer, AnalysisResult

logger = logging.getLogger(__name__)

# RSS Feed tanımları
NEWS_SOURCES: list[dict] = [
    {
        "name":        "CoinDesk",
        "url":         "https://www.coindesk.com/arc/outboundfeeds/rss/",
        "credibility": 9,
        "language":    "en",
    },
    {
        "name":        "Cointelegraph",
        "url":         "https://cointelegraph.com/rss",
        "credibility": 8,
        "language":    "en",
    },
    {
        "name":        "The Block",
        "url":         "https://www.theblock.co/rss.xml",
        "credibility": 9,
        "language":    "en",
    },
    {
        "name":        "Decrypt",
        "url":         "https://decrypt.co/feed",
        "credibility": 8,
        "language":    "en",
    },
    {
        "name":        "Bitcoin.com News",
        "url":         "https://news.bitcoin.com/feed/",
        "credibility": 7,
        "language":    "en",
    },
    {
        "name":        "DL News",
        "url":         "https://dlnews.com/arc/outboundfeeds/rss/",
        "credibility": 8,
        "language":    "en",
    },
    {
        "name":        "CryptoSlate",
        "url":         "https://cryptoslate.com/feed/",
        "credibility": 7,
        "language":    "en",
    },
    {
        "name":        "WuBlockchain",
        "url":         "https://wublock.substack.com/feed",
        "credibility": 8,
        "language":    "en",
        "asia_focus":  True,
    },
]

# Yüksek önem anahtar kelimeleri (bulk haber fitresi)
HIGH_IMPACT_KEYWORDS: set[str] = {
    "sec", "etf", "hack", "exploit", "listing", "delisting",
    "whale", "accumulation", "dump", "rug", "bankrupt", "shutdown",
    "partnership", "acquisition", "mainnet", "launch", "airdrop",
    "regulation", "ban", "approve", "reject", "lawsuit", "settlement",
    "billion", "million",
}


@dataclass
class NewsItem:
    title:        str
    summary:      str
    url:          str
    source:       str
    published_at: str
    credibility:  int    # 1-10

    # NLP sonuçları (analiz sonrası dolar)
    tickers:      list[str]  = field(default_factory=list)
    themes:       list[str]  = field(default_factory=list)
    sentiment:    str        = "NEUTRAL"
    impact_score: float      = 0.0    # 0-100

    @property
    def full_text(self) -> str:
        """Başlık + özet birleşimi (NLP için)."""
        return f"{self.title}. {self.summary}"

    @property
    def is_high_impact(self) -> bool:
        text = self.full_text.lower()
        return any(kw in text for kw in HIGH_IMPACT_KEYWORDS)

    def to_tweet_like(self) -> dict:
        """NLPAnalyzer ile uyumlu dict formatına çevirir."""
        return {
            "id":         hash(self.url) % (10**18),
            "author":     self.source,
            "text":       self.full_text[:500],
            "url":        self.url,
            "likes":      int(self.credibility * 1000),
            "retweets":   int(self.credibility * 200),
        }


class NewsAggregator:
    """
    Kripto haber RSS beslemelerini tarar, NLP analizi ile zenginleştirir.
    """

    def __init__(self, nlp: Optional[NLPAnalyzer] = None):
        self.nlp      = nlp or NLPAnalyzer()
        self._session = requests.Session()
        self._session.headers.update({
            "User-Agent": "WhaleAlert-Bot/1.0",
            "Accept":     "application/rss+xml, application/xml, text/xml",
        })
        self._seen_urls: set[str] = set()
        logger.info(f"NewsAggregator baslatildi ({len(NEWS_SOURCES)} kaynak)")

    # ── Public API ─────────────────────────────────────────────────────────────

    def fetch_latest(
        self,
        since_hours: int = 2,
        sources: list[str] = None,
    ) -> list[NewsItem]:
        """
        Tüm (veya seçili) kaynaklardan son haberleri çeker.
        NLP analizi uygular ve önem skorunu hesaplar.
        """
        target_sources = [
            s for s in NEWS_SOURCES
            if sources is None or s["name"] in sources
        ]

        all_news: list[NewsItem] = []
        since_dt = datetime.now(timezone.utc) - timedelta(hours=since_hours)

        for source in target_sources:
            try:
                items = self._fetch_rss(source, since_dt)
                all_news.extend(items)
                logger.debug(f"{source['name']}: {len(items)} haber")
                time.sleep(0.5)
            except Exception as e:
                logger.warning(f"Haber cekme hatasi ({source['name']}): {e}")

        # NLP analizi
        analyzed = self._analyze_news(all_news)

        # Önem skoruna göre sırala
        analyzed.sort(key=lambda n: n.impact_score, reverse=True)

        logger.info(
            f"NewsAggregator: {len(analyzed)} haber islendi, "
            f"{sum(1 for n in analyzed if n.is_high_impact)} yuksek etkili"
        )
        return analyzed

    def find_news_for_ticker(self, ticker: str, hours: int = 24) -> list[NewsItem]:
        """Belirli bir ticker hakkındaki haberleri çeker."""
        all_news = self.fetch_latest(since_hours=hours)
        ticker_clean = ticker.upper().lstrip("$")
        return [
            n for n in all_news
            if ticker_clean in n.tickers or ticker_clean.lower() in n.full_text.lower()
        ]

    def cross_reference_with_tweet(
        self,
        tweet_tickers: list[str],
        news_items: list[NewsItem],
    ) -> list[NewsItem]:
        """
        Tweet'te geçen ticker'lar için aynı konudaki haberleri eşleştirir.
        Tweet + haber aynı konudan bahsediyorsa sinyal gücü artar.
        """
        tweet_set = {t.upper().lstrip("$") for t in tweet_tickers}
        matches   = [n for n in news_items if any(t in tweet_set for t in n.tickers)]

        if matches:
            logger.info(
                f"Tweet-Haber eslesme: {len(matches)} haber "
                f"tweet ticker'lariyla ({tweet_tickers}) ortusuyor"
            )
        return matches

    # ── RSS Çekme ──────────────────────────────────────────────────────────────

    def _fetch_rss(self, source: dict, since_dt: datetime) -> list[NewsItem]:
        resp = self._session.get(source["url"], timeout=15)
        resp.raise_for_status()

        root  = ET.fromstring(resp.content)
        items: list[NewsItem] = []

        # RSS 2.0 ve Atom formatlarını destekle
        ns = {"atom": "http://www.w3.org/2005/Atom"}

        # İtem elemanlarını bul
        channel = root.find("channel")
        entries = (
            channel.findall("item") if channel is not None
            else root.findall("atom:entry", ns)
        )

        for entry in entries[:20]:   # En son 20 haber
            try:
                item = self._parse_entry(entry, source, since_dt, ns)
                if item and item.url not in self._seen_urls:
                    self._seen_urls.add(item.url)
                    items.append(item)
            except Exception as e:
                logger.debug(f"RSS entry parse hatasi: {e}")
                continue

        return items

    def _parse_entry(
        self,
        entry: ET.Element,
        source: dict,
        since_dt: datetime,
        ns: dict,
    ) -> Optional[NewsItem]:
        # Başlık
        title_el = entry.find("title")
        if title_el is None:
            return None
        title = (title_el.text or "").strip()

        # URL
        link_el = entry.find("link")
        url = (link_el.text or link_el.get("href", "")).strip() if link_el is not None else ""
        if not url:
            return None

        # Özet / Description
        desc_el = entry.find("description") or entry.find("{http://www.w3.org/2005/Atom}summary")
        summary = (desc_el.text or "").strip()[:500] if desc_el is not None else ""

        # Tarih filtresi
        pub_el  = (
            entry.find("pubDate") or
            entry.find("{http://www.w3.org/2005/Atom}published") or
            entry.find("{http://www.w3.org/2005/Atom}updated")
        )
        pub_str = pub_el.text.strip() if pub_el is not None and pub_el.text else ""

        return NewsItem(
            title        = title,
            summary      = summary,
            url          = url,
            source       = source["name"],
            published_at = pub_str,
            credibility  = source.get("credibility", 7),
        )

    # ── NLP Analizi ────────────────────────────────────────────────────────────

    def _analyze_news(self, news_list: list[NewsItem]) -> list[NewsItem]:
        for item in news_list:
            tweet_like = item.to_tweet_like()
            result: AnalysisResult = self.nlp.analyze(tweet_like)
            item.tickers  = result.tickers
            item.themes   = result.themes
            item.sentiment = result.sentiment_label
            item.impact_score = self._compute_impact(item, result)
        return news_list

    def _compute_impact_score(self, item: NewsItem, result: AnalysisResult) -> float:
        score = 0.0
        score += item.credibility * 4          # 0-40 puan
        score += abs(result.sentiment_score) * 20  # 0-20 puan
        score += len(result.tickers) * 5       # ticker başına 5 puan
        score += len(result.themes) * 4        # tema başına 4 puan
        if item.is_high_impact:
            score += 20                         # yüksek etki kelimesi bonusu
        return round(min(score, 100), 1)

    _compute_impact = _compute_impact_score   # alias

    # ── Özet ───────────────────────────────────────────────────────────────────

    def format_news_brief(self, news_list: list[NewsItem], limit: int = 5) -> str:
        """Top N haberi Telegram formatında özetler."""
        if not news_list:
            return "_Yeni haber bulunamadı._"

        lines = [f"*Son Kripto Haberleri* ({len(news_list)} haber)\n"]
        for i, item in enumerate(news_list[:limit], 1):
            tickers_str = " ".join(f"${t}" for t in item.tickers) if item.tickers else ""
            lines.append(
                f"{i}. [{item.title[:80]}...]({item.url})\n"
                f"   _{item.source}_ {tickers_str} | {item.sentiment}"
            )
        return "\n".join(lines)
