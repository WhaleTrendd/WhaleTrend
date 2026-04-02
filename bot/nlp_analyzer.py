"""
NLP Analyzer
============
Tweet metinlerinden ticker sembollerini, duygu (sentiment) skorunu
ve tematik kavramları çıkarır.

Araçlar:
  - Regex: ticker tespiti ($BTC, $ETH vb.)
  - Basit anahtar kelime sayımı: sentiment skoru
  - Tematik sözlük: "AI x Crypto", "ZK", "RWA" vb. konsept eşleştirme
  - opsiyonel: spaCy (NER için, kurulu ise kullanılır)
"""

import re
import logging
from dataclasses import dataclass, field
from typing import Optional

from config import (
    TICKER_PATTERN,
    BULLISH_KEYWORDS,
    BEARISH_KEYWORDS,
    THEMATIC_KEYWORDS,
    SENTIMENT_THRESHOLD,
)

logger = logging.getLogger(__name__)

# spaCy opsiyonel yükleme
try:
    import spacy
    _nlp = spacy.load("en_core_web_sm")
    SPACY_AVAILABLE = True
    logger.info("spaCy yüklendi → NER aktif")
except Exception:
    _nlp = None
    SPACY_AVAILABLE = False
    logger.info("spaCy bulunamadı → regex modunda çalışılıyor")


# ──────────────────────────────────────────────────────────────────────────────
# Veri Sınıfları
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class AnalysisResult:
    """Bir tweet için NLP analiz çıktısı."""
    tweet_id:       str
    author:         str
    text:           str
    tweet_url:      str

    # Tespit edilen ticker sembolleri
    tickers:        list[str] = field(default_factory=list)

    # Duygu: +1.0 (güçlü bullish) ↔ -1.0 (güçlü bearish)
    sentiment_score: float = 0.0
    sentiment_label: str  = "NEUTRAL"   # BULLISH | BEARISH | NEUTRAL

    # Tespit edilen tematik kavramlar
    themes:         list[str] = field(default_factory=list)

    # Öne çıkan anahtar kelimeler (debug/log için)
    matched_keywords: list[str] = field(default_factory=list)

    # Alert üretilmeli mi?
    should_alert:   bool = False

    @property
    def primary_ticker(self) -> Optional[str]:
        return self.tickers[0] if self.tickers else None


# ──────────────────────────────────────────────────────────────────────────────
# Ana Analizci
# ──────────────────────────────────────────────────────────────────────────────

class NLPAnalyzer:
    """
    Tweet metnini analiz eder, ticker + sentiment + tema çıkarır.
    """

    _TICKER_RE   = re.compile(TICKER_PATTERN)
    _CASHTAG_RE  = re.compile(r"(?<!\w)\$([A-Z]{2,10})(?!\w)")   # temiz yakalama
    _NUMBER_RE   = re.compile(r"\d+[xX]")                         # 100x, 10x vb.

    # Ticker olmayan yaygın dolar sembolü kısaltmaları → filtrele
    _TICKER_BLACKLIST = {"USD", "EUR", "GBP", "JPY", "AUD", "CEO", "CTO", "CEO", "NFT"}

    def analyze(self, tweet: dict) -> AnalysisResult:
        text = tweet.get("text", "")
        text_lower = text.lower()

        result = AnalysisResult(
            tweet_id  = tweet.get("id", ""),
            author    = tweet.get("author", ""),
            text      = text,
            tweet_url = tweet.get("url", ""),
        )

        # 1) Ticker tespiti
        result.tickers = self._extract_tickers(text)

        # 2) Sentiment skoru
        bullish_hits, bearish_hits = self._score_keywords(text_lower)
        result.matched_keywords = bullish_hits + bearish_hits
        result.sentiment_score  = self._compute_score(bullish_hits, bearish_hits)
        result.sentiment_label  = self._label(result.sentiment_score)

        # 3) Tematik kavram tespiti
        result.themes = self._detect_themes(text_lower)

        # 4) Alert eşiği kontrolü
        result.should_alert = (
            len(result.tickers) > 0 and
            abs(result.sentiment_score) >= SENTIMENT_THRESHOLD
        ) or len(result.themes) > 0

        if result.should_alert:
            logger.debug(
                f"Alert tetiklendi | @{result.author} | "
                f"tickers={result.tickers} | sentiment={result.sentiment_label} "
                f"({result.sentiment_score:.2f}) | themes={result.themes}"
            )

        return result

    def analyze_batch(self, tweets: list[dict]) -> list[AnalysisResult]:
        results = []
        for tweet in tweets:
            try:
                r = self.analyze(tweet)
                results.append(r)
            except Exception as e:
                logger.warning(f"Analiz hatası ({tweet.get('id')}): {e}")
        alert_count = sum(1 for r in results if r.should_alert)
        logger.info(f"{len(results)} tweet analiz edildi, {alert_count} alert tetiklendi")
        return results

    # ── Özel Metodlar ──────────────────────────────────────────────────────────

    def _extract_tickers(self, text: str) -> list[str]:
        """$BTC, $ETH gibi cashtag'leri çıkarır."""
        raw = self._CASHTAG_RE.findall(text)
        tickers = []
        seen = set()
        for t in raw:
            upper = t.upper()
            if upper not in self._TICKER_BLACKLIST and upper not in seen:
                tickers.append(upper)
                seen.add(upper)
        return tickers

    def _score_keywords(self, text_lower: str) -> tuple[list[str], list[str]]:
        """Bullish ve bearish anahtar kelime listelerini karşılaştırır."""
        bullish_hits = [kw for kw in BULLISH_KEYWORDS if kw.lower() in text_lower]
        bearish_hits = [kw for kw in BEARISH_KEYWORDS if kw.lower() in text_lower]

        # Sayısal çarpanlar (100x, 10x) bullish etkiyi artırır
        multipliers = self._NUMBER_RE.findall(text_lower)
        if multipliers:
            bullish_hits += multipliers

        return bullish_hits, bearish_hits

    @staticmethod
    def _compute_score(bullish: list[str], bearish: list[str]) -> float:
        """
        Basit ağırlıklı skor:
           score = (bullish_count - bearish_count) / (total + 1)
        Aralık: -1.0 ile +1.0
        """
        b = len(bullish)
        r = len(bearish)
        total = b + r
        if total == 0:
            return 0.0
        return round((b - r) / (total + 1), 3)

    @staticmethod
    def _label(score: float) -> str:
        if score >= 0.2:
            return "BULLISH"
        elif score <= -0.2:
            return "BEARISH"
        return "NEUTRAL"

    def _detect_themes(self, text_lower: str) -> list[str]:
        """Tematik sözlük üzerinden kavram tespiti yapar."""
        detected = []
        for theme, keywords in THEMATIC_KEYWORDS.items():
            if any(kw in text_lower for kw in keywords):
                detected.append(theme)
        return detected

    # ── spaCy NER (opsiyonel) ──────────────────────────────────────────────────

    def extract_entities(self, text: str) -> list[tuple[str, str]]:
        """
        spaCy ile adlandırılmış varlık tanıma.
        Döner: [(entity_text, entity_label), ...]
        Kurulu değilse boş liste döner.
        """
        if not SPACY_AVAILABLE or _nlp is None:
            return []
        doc = _nlp(text[:512])   # hız için truncate
        return [(ent.text, ent.label_) for ent in doc.ents]


# ──────────────────────────────────────────────────────────────────────────────
# Önizleme / Test
# ──────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import json

    test_tweets = [
        {
            "id": "001",
            "author": "VitalikButerin",
            "text": "ZK proofs are changing everything. $ETH layer2 scaling is incredible. Accumulate now.",
            "url": "https://twitter.com/test/001",
        },
        {
            "id": "002",
            "author": "elonmusk",
            "text": "Honestly, $DOGE is still my favorite. But AI x Crypto is something huge coming. 100x potential.",
            "url": "https://twitter.com/test/002",
        },
        {
            "id": "003",
            "author": "MMCrypto",
            "text": "Warning! $SOL whales just dumped 2M tokens. Exit signal, be careful with leverage.",
            "url": "https://twitter.com/test/003",
        },
        {
            "id": "004",
            "author": "saylor",
            "text": "Bitcoin $BTC is digital gold. Corporate treasury allocation is the future. Hodl strong.",
            "url": "https://twitter.com/test/004",
        },
    ]

    analyzer = NLPAnalyzer()
    for tweet in test_tweets:
        result = analyzer.analyze(tweet)
        print(f"\n{'='*60}")
        print(f"@{result.author}: {result.text[:80]}...")
        print(f"  Tickers:   {result.tickers}")
        print(f"  Sentiment: {result.sentiment_label} ({result.sentiment_score})")
        print(f"  Themes:    {result.themes}")
        print(f"  Keywords:  {result.matched_keywords}")
        print(f"  Alert:     {'[YES]' if result.should_alert else '[NO]'}")
