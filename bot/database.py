"""
Database Manager
================
SQLite üzerinde tüm geçmişi saklar:
  - tweets          : taranan tweetler
  - alerts          : gönderilen Telegram alertleri
  - whale_txs       : tespit edilen whale işlemleri
  - token_signals   : ticker bazında özet sinyal geçmişi

Tekrar alert koruması, geçmiş sorgulama ve
Faz 2 rapor üretimi için temel altyapıyı sağlar.
"""

import sqlite3
import json
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path
from contextlib import contextmanager
from typing import Optional

logger = logging.getLogger(__name__)

DB_PATH = Path("data/whaletrend.db")


# ──────────────────────────────────────────────────────────────────────────────
# Schema
# ──────────────────────────────────────────────────────────────────────────────

SCHEMA_SQL = """
-- Taranan tweetler
CREATE TABLE IF NOT EXISTS tweets (
    id              TEXT PRIMARY KEY,
    author          TEXT NOT NULL,
    text            TEXT NOT NULL,
    url             TEXT,
    likes           INTEGER DEFAULT 0,
    retweets        INTEGER DEFAULT 0,
    created_at      TEXT,
    scraped_at      TEXT NOT NULL,
    sentiment       TEXT,
    sentiment_score REAL,
    tickers         TEXT,   -- JSON list
    themes          TEXT    -- JSON list
);

-- Gönderilen alertler
CREATE TABLE IF NOT EXISTS alerts (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    tweet_id        TEXT,
    author          TEXT,
    ticker          TEXT,
    alert_type      TEXT,   -- EXIT_WARNING | INSIDER_ACCUMULATION | NLP_SIGNAL
    sentiment       TEXT,
    onchain_verdict TEXT,
    message_preview TEXT,
    sent_at         TEXT NOT NULL,
    chat_ids        TEXT    -- JSON list
);

-- Whale işlemleri
CREATE TABLE IF NOT EXISTS whale_txs (
    tx_hash         TEXT PRIMARY KEY,
    chain           TEXT,
    token_symbol    TEXT,
    from_address    TEXT,
    to_address      TEXT,
    value_usd       REAL,
    tx_type         TEXT,
    exchange_name   TEXT,
    block_number    INTEGER,
    detected_at     TEXT NOT NULL
);

-- Token bazında özet sinyaller (zaman serisi)
CREATE TABLE IF NOT EXISTS token_signals (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker          TEXT NOT NULL,
    signal_type     TEXT NOT NULL,   -- BULLISH_MENTION | BEARISH_MENTION | EXIT | ACCUMULATION
    source_account  TEXT,
    value           REAL DEFAULT 1,
    recorded_at     TEXT NOT NULL
);

-- İndeksler
CREATE INDEX IF NOT EXISTS idx_tweets_author    ON tweets(author);
CREATE INDEX IF NOT EXISTS idx_tweets_scraped   ON tweets(scraped_at);
CREATE INDEX IF NOT EXISTS idx_alerts_ticker    ON alerts(ticker);
CREATE INDEX IF NOT EXISTS idx_alerts_sent      ON alerts(sent_at);
CREATE INDEX IF NOT EXISTS idx_whale_symbol     ON whale_txs(token_symbol);
CREATE INDEX IF NOT EXISTS idx_signals_ticker   ON token_signals(ticker);
CREATE INDEX IF NOT EXISTS idx_signals_type     ON token_signals(signal_type);
"""


# ──────────────────────────────────────────────────────────────────────────────
# Database Sınıfı
# ──────────────────────────────────────────────────────────────────────────────

class Database:
    """WhaleAlert SQLite veritabanı yöneticisi."""

    def __init__(self, db_path: Path = DB_PATH):
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()
        logger.info(f"Veritabani hazir: {self.db_path}")

    @contextmanager
    def _conn(self):
        conn = sqlite3.connect(self.db_path, timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _init_schema(self):
        with self._conn() as conn:
            conn.executescript(SCHEMA_SQL)

    # ── Tweet Metodlar ─────────────────────────────────────────────────────────

    def save_tweet(self, tweet: dict, nlp=None) -> bool:
        """Tweet kaydeder. Zaten varsa False döner."""
        now = datetime.now(timezone.utc).isoformat()
        try:
            with self._conn() as conn:
                conn.execute("""
                    INSERT OR IGNORE INTO tweets
                    (id, author, text, url, likes, retweets, created_at, scraped_at,
                     sentiment, sentiment_score, tickers, themes)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
                """, (
                    tweet.get("id", ""),
                    tweet.get("author", ""),
                    tweet.get("text", ""),
                    tweet.get("url", ""),
                    tweet.get("likes", 0),
                    tweet.get("retweets", 0),
                    tweet.get("created_at", ""),
                    now,
                    nlp.sentiment_label if nlp else None,
                    nlp.sentiment_score if nlp else None,
                    json.dumps(nlp.tickers) if nlp else "[]",
                    json.dumps(nlp.themes) if nlp else "[]",
                ))
                return conn.execute(
                    "SELECT changes()"
                ).fetchone()[0] > 0
        except Exception as e:
            logger.error(f"Tweet kayit hatasi: {e}")
            return False

    def tweet_exists(self, tweet_id: str) -> bool:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT 1 FROM tweets WHERE id=?", (tweet_id,)
            ).fetchone()
            return row is not None

    def get_recent_tweets(self, hours: int = 24, author: str = None) -> list[dict]:
        since = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
        with self._conn() as conn:
            if author:
                rows = conn.execute(
                    "SELECT * FROM tweets WHERE scraped_at>? AND author=? ORDER BY scraped_at DESC",
                    (since, author)
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM tweets WHERE scraped_at>? ORDER BY scraped_at DESC",
                    (since,)
                ).fetchall()
        return [dict(r) for r in rows]

    # ── Alert Metodlar ─────────────────────────────────────────────────────────

    def save_alert(
        self,
        tweet_id: str,
        author: str,
        ticker: str,
        alert_type: str,
        sentiment: str,
        onchain_verdict: str,
        message: str,
        chat_ids: list[str],
    ) -> int:
        """Alert kaydeder, oluşturulan id'yi döner."""
        now = datetime.now(timezone.utc).isoformat()
        with self._conn() as conn:
            cursor = conn.execute("""
                INSERT INTO alerts
                (tweet_id, author, ticker, alert_type, sentiment,
                 onchain_verdict, message_preview, sent_at, chat_ids)
                VALUES (?,?,?,?,?,?,?,?,?)
            """, (
                tweet_id, author, ticker, alert_type, sentiment,
                onchain_verdict, message[:300], now,
                json.dumps(chat_ids)
            ))
            return cursor.lastrowid

    def was_recently_alerted(self, ticker: str, hours: int = 2) -> bool:
        """Aynı ticker için son <hours> saatte alert gönderildiyse True."""
        since = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
        with self._conn() as conn:
            row = conn.execute(
                "SELECT 1 FROM alerts WHERE ticker=? AND sent_at>?",
                (ticker, since)
            ).fetchone()
            return row is not None

    def get_alert_stats(self, days: int = 7) -> dict:
        """Son N günün alert istatistiklerini döner."""
        since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        with self._conn() as conn:
            total = conn.execute(
                "SELECT COUNT(*) FROM alerts WHERE sent_at>?", (since,)
            ).fetchone()[0]
            by_type = conn.execute("""
                SELECT alert_type, COUNT(*) as cnt
                FROM alerts WHERE sent_at>?
                GROUP BY alert_type
            """, (since,)).fetchall()
            top_tickers = conn.execute("""
                SELECT ticker, COUNT(*) as cnt
                FROM alerts WHERE sent_at>?
                GROUP BY ticker ORDER BY cnt DESC LIMIT 10
            """, (since,)).fetchall()
        return {
            "total": total,
            "by_type": {r["alert_type"]: r["cnt"] for r in by_type},
            "top_tickers": [(r["ticker"], r["cnt"]) for r in top_tickers],
        }

    # ── Whale TX Metodlar ──────────────────────────────────────────────────────

    def save_whale_tx(self, tx) -> bool:
        """WhaleTransaction nesnesi kaydeder."""
        now = datetime.now(timezone.utc).isoformat()
        try:
            with self._conn() as conn:
                conn.execute("""
                    INSERT OR IGNORE INTO whale_txs
                    (tx_hash, chain, token_symbol, from_address, to_address,
                     value_usd, tx_type, exchange_name, block_number, detected_at)
                    VALUES (?,?,?,?,?,?,?,?,?,?)
                """, (
                    tx.tx_hash, tx.chain, tx.token_symbol,
                    tx.from_address, tx.to_address, tx.value_usd,
                    tx.tx_type, tx.exchange_name, tx.block_number, now
                ))
                return conn.execute("SELECT changes()").fetchone()[0] > 0
        except Exception as e:
            logger.error(f"Whale TX kayit hatasi: {e}")
            return False

    def get_recent_whale_txs(self, ticker: str, hours: int = 24) -> list[dict]:
        since = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
        with self._conn() as conn:
            rows = conn.execute("""
                SELECT * FROM whale_txs
                WHERE token_symbol=? AND detected_at>?
                ORDER BY value_usd DESC
            """, (ticker, since)).fetchall()
        return [dict(r) for r in rows]

    # ── Sinyal Metodlar ────────────────────────────────────────────────────────

    def record_signal(self, ticker: str, signal_type: str, source: str = None, value: float = 1.0):
        now = datetime.now(timezone.utc).isoformat()
        with self._conn() as conn:
            conn.execute("""
                INSERT INTO token_signals (ticker, signal_type, source_account, value, recorded_at)
                VALUES (?,?,?,?,?)
            """, (ticker, signal_type, source, value, now))

    def get_signal_score(self, ticker: str, hours: int = 48) -> dict:
        """Ticker için ağırlıklı sinyal skoru hesaplar."""
        since = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
        with self._conn() as conn:
            rows = conn.execute("""
                SELECT signal_type, SUM(value) as total
                FROM token_signals
                WHERE ticker=? AND recorded_at>?
                GROUP BY signal_type
            """, (ticker, since)).fetchall()
        scores = {r["signal_type"]: r["total"] for r in rows}
        bullish = scores.get("BULLISH_MENTION", 0) + scores.get("ACCUMULATION", 0)
        bearish = scores.get("BEARISH_MENTION", 0) + scores.get("EXIT", 0)
        return {
            "ticker": ticker,
            "bullish_score": round(bullish, 2),
            "bearish_score": round(bearish, 2),
            "net_score": round(bullish - bearish, 2),
            "details": scores,
        }

    # ── Genel ─────────────────────────────────────────────────────────────────

    def get_db_stats(self) -> dict:
        with self._conn() as conn:
            return {
                "tweets":    conn.execute("SELECT COUNT(*) FROM tweets").fetchone()[0],
                "alerts":    conn.execute("SELECT COUNT(*) FROM alerts").fetchone()[0],
                "whale_txs": conn.execute("SELECT COUNT(*) FROM whale_txs").fetchone()[0],
                "signals":   conn.execute("SELECT COUNT(*) FROM token_signals").fetchone()[0],
            }
