"""
Report Generator
================
Faz 2 Roadmap: Haftalık/günlük "autopsy" (otopsi) raporları.

Üretilen raporlar:
  1. Günlük Özet   — O günün en önemli sinyalleri, en aktif hesaplar
  2. Haftalık Otopsi — Geçen haftanın mismatch'larının doğruluğu analizi
  3. Token Raporu  — Belirli bir token için tüm geçmişin özeti
  4. Trend Raporu  — Hangi narratifler/temalar yükselişte?

Çıktı formatları:
  - Telegram Markdown (doğrudan gönderilebilir)
  - HTML (web dashboard için)
  - JSON  (API response için)
"""

import json
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

from database import Database

logger = logging.getLogger(__name__)

REPORTS_DIR = Path("data/reports")


# ──────────────────────────────────────────────────────────────────────────────
# Ana Rapor Üreteci
# ──────────────────────────────────────────────────────────────────────────────

class ReportGenerator:
    """Veritabanı verilerinden analitik raporlar üretir."""

    def __init__(self, db: Optional[Database] = None):
        self.db = db or Database()
        REPORTS_DIR.mkdir(parents=True, exist_ok=True)
        logger.info("ReportGenerator baslatildi")

    # ──────────────────────────────────────────────────────────────────────────
    # 1. Gunluk Ozet Raporu
    # ──────────────────────────────────────────────────────────────────────────

    def daily_summary(self, date: Optional[datetime] = None) -> str:
        """Belirli bir gün için özet rapor üretir (Telegram formatı)."""
        date = date or datetime.now(timezone.utc)
        stats = self.db.get_alert_stats(days=1)
        db_stats = self.db.get_db_stats()

        date_str = date.strftime("%d %B %Y")

        lines = [
            f"*WHALE TREND — Gunluk Rapor*",
            f"_{date_str}_",
            "",
            "--------------------",
            "*Bugunun Ozeti*",
            "--------------------",
            f"Taranan Tweet:    {db_stats['tweets']}",
            f"Gonderilen Alert: {stats['total']}",
            f"Whale TX:         {db_stats['whale_txs']}",
            "",
        ]

        # Alert tiplerine gore
        if stats["by_type"]:
            lines.append("*Alert Dagilimi:*")
            type_labels = {
                "EXIT_WARNING":        "Cikis Uyarisi",
                "INSIDER_ACCUMULATION":"Insider Birikimi",
                "NLP_SIGNAL":          "NLP Sinyali",
            }
            for atype, cnt in stats["by_type"].items():
                label = type_labels.get(atype, atype)
                bar   = "█" * min(cnt, 20) + "░" * max(0, 20 - cnt)
                lines.append(f"  {label[:18]:18} {cnt:3} {bar}")
            lines.append("")

        # En cok alert alan tokenler
        if stats["top_tickers"]:
            lines.append("*En Aktif Tokenler:*")
            for i, (ticker, cnt) in enumerate(stats["top_tickers"][:5], 1):
                lines.append(f"  {i}. ${ticker:8} — {cnt} alert")
            lines.append("")

        lines.append("_WhaleTrend Alpha Agent_")
        return "\n".join(lines)

    # ──────────────────────────────────────────────────────────────────────────
    # 2. Haftalik Otopsi Raporu
    # ──────────────────────────────────────────────────────────────────────────

    def weekly_autopsy(self) -> str:
        """Son 7 gunun mismatch analizinden otopsi raporu uretir."""
        stats = self.db.get_alert_stats(days=7)
        db_stats = self.db.get_db_stats()

        now  = datetime.now(timezone.utc)
        week = (now - timedelta(days=7)).strftime("%d %b")
        end  = now.strftime("%d %b %Y")

        lines = [
            "*WHALE TREND — Haftalik Otopsi*",
            f"_{week} – {end}_",
            "",
            "--------------------",
            "*7 Gunluk Performans*",
            "--------------------",
            f"Toplam Alert:     {stats['total']}",
            f"Taranan Tweet:    {db_stats['tweets']}",
            f"On-chain TX:      {db_stats['whale_txs']}",
            "",
        ]

        exit_cnt  = stats["by_type"].get("EXIT_WARNING", 0)
        accum_cnt = stats["by_type"].get("INSIDER_ACCUMULATION", 0)
        nlp_cnt   = stats["by_type"].get("NLP_SIGNAL", 0)

        lines += [
            "*Sinyal Kirilimi:*",
            f"  Cikis Uyarisi     : {exit_cnt:3} alert",
            f"  Insider Birikim   : {accum_cnt:3} alert",
            f"  Saf NLP Sinyali   : {nlp_cnt:3} alert",
            "",
        ]

        # En sık uyarılan tokenler
        if stats["top_tickers"]:
            lines.append("*En Cok Sinyal Uretilen Tokenler:*")
            for rank, (ticker, cnt) in enumerate(stats["top_tickers"][:10], 1):
                medal = ["", "ALTIN", "GUMUS", "BRONZ"][min(rank, 3)]
                suffix = f"  [{medal}]" if rank <= 3 else ""
                lines.append(f"  {rank:2}. ${ticker:8} — {cnt} sinyal{suffix}")
            lines.append("")

        lines += [
            "--------------------",
            "*Onemli Not:*",
            "_Bu rapor piyasa manipulasyonunu geri donuk analiz eder._",
            "_Yatirim tavsiyesi degildir. Kendi arastirmanizi yapin._",
            "",
            "_WhaleTrend Alpha Agent — Sadece $WHALE Hodler'larina_",
        ]

        return "\n".join(lines)

    # ──────────────────────────────────────────────────────────────────────────
    # 3. Token Analiz Raporu
    # ──────────────────────────────────────────────────────────────────────────

    def token_report(self, ticker: str, hours: int = 48) -> str:
        """Belirli bir token için kapsamlı analiz raporu uretir."""
        ticker = ticker.upper().lstrip("$")

        signal_score = self.db.get_signal_score(ticker, hours)
        recent_txs   = self.db.get_recent_whale_txs(ticker, hours)

        # Kararı belirle
        net = signal_score["net_score"]
        if net > 3:
            verdict = "GUCLU BULLISH"
            v_emoji = "🚀"
        elif net > 0:
            verdict = "HAFIF BULLISH"
            v_emoji = "📈"
        elif net < -3:
            verdict = "GUCLU BEARISH"
            v_emoji = "💥"
        elif net < 0:
            verdict = "HAFIF BEARISH"
            v_emoji = "📉"
        else:
            verdict = "NOTRAL"
            v_emoji = "➡️"

        lines = [
            f"*TOKEN RAPORU — ${ticker}*",
            f"_Son {hours} saat_",
            "",
            f"{v_emoji} *Genel Yargı: {verdict}*",
            "",
            "*Sinyal Skorlari:*",
            f"  Bullish : {signal_score['bullish_score']:+.1f}",
            f"  Bearish : {signal_score['bearish_score']:+.1f}",
            f"  Net     : {net:+.1f}",
            "",
        ]

        if recent_txs:
            exit_txs  = [t for t in recent_txs if t["tx_type"] == "DEPOSIT_TO_EXCHANGE"]
            accum_txs = [t for t in recent_txs if t["tx_type"] == "ACCUMULATION"]

            if exit_txs:
                total_exit = sum(t["value_usd"] for t in exit_txs)
                lines.append(f"*Borsa Depositlari:* {len(exit_txs)} islem — ${total_exit:,.0f}")
                for tx in exit_txs[:3]:
                    lines.append(
                        f"  └ {tx.get('exchange_name','?')} | "
                        f"${tx['value_usd']:,.0f} | "
                        f"{tx['chain']}"
                    )
                lines.append("")

            if accum_txs:
                total_accum = sum(t["value_usd"] for t in accum_txs)
                lines.append(f"*Birikim Islemleri:* {len(accum_txs)} islem — ${total_accum:,.0f}")
                for tx in accum_txs[:3]:
                    lines.append(
                        f"  └ ${tx['value_usd']:,.0f} | {tx['chain']}"
                    )
                lines.append("")
        else:
            lines.append("_On-chain veri bulunamadi_\n")

        return "\n".join(lines)

    # ──────────────────────────────────────────────────────────────────────────
    # 4. Trend / Narratif Raporu
    # ──────────────────────────────────────────────────────────────────────────

    def narrative_trend_report(self) -> str:
        """Son 48 saatte hangi narratiflerin (temaların) öne çıktığını raporlar."""
        from config import THEMATIC_KEYWORDS
        recent = self.db.get_recent_tweets(hours=48)

        theme_counts: dict[str, int] = {theme: 0 for theme in THEMATIC_KEYWORDS}

        for tweet in recent:
            themes_json = tweet.get("themes", "[]")
            try:
                themes = json.loads(themes_json)
            except Exception:
                continue
            for theme in themes:
                if theme in theme_counts:
                    theme_counts[theme] += 1

        sorted_themes = sorted(theme_counts.items(), key=lambda x: x[1], reverse=True)

        lines = [
            "*NARRATIF TREND RAPORU*",
            f"_Son 48 saat | {len(recent)} tweet analiz edildi_",
            "",
            "*One Cikan Narratifler:*",
        ]

        max_cnt = sorted_themes[0][1] if sorted_themes and sorted_themes[0][1] > 0 else 1
        for theme, cnt in sorted_themes:
            if cnt == 0:
                continue
            bar_len = int((cnt / max_cnt) * 20)
            bar = "█" * bar_len + "░" * (20 - bar_len)
            rank_emoji = "🔥" if cnt == max_cnt else ("📈" if cnt > max_cnt * 0.5 else "  ")
            lines.append(f"  {rank_emoji} {theme:20} {cnt:3} {bar}")

        lines += [
            "",
            "_Multi-haber akisina dikkat: yukselen narratifler_",
            "_genellikle sonraki 24-72 saatte fiyat hareketini onculer._",
            "",
            "_WhaleTrend Alpha Agent_",
        ]

        return "\n".join(lines)

    # ──────────────────────────────────────────────────────────────────────────
    # Dosyaya Kaydetme
    # ──────────────────────────────────────────────────────────────────────────

    def save_report(self, name: str, content: str, fmt: str = "md") -> Path:
        """Raporu dosyaya kaydeder."""
        now = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M")
        path = REPORTS_DIR / f"{now}_{name}.{fmt}"

        # Telegram markdown işaretlerini temizle (düz metin için)
        if fmt == "txt":
            for char in ["*", "_", "`"]:
                content = content.replace(char, "")

        path.write_text(content, encoding="utf-8")
        logger.info(f"Rapor kaydedildi: {path}")
        return path


# ──────────────────────────────────────────────────────────────────────────────
# Test
# ──────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    gen = ReportGenerator()

    print("=== GUNLUK RAPOR ===")
    print(gen.daily_summary())
    print()

    print("=== HAFTALIK OTOPSI ===")
    print(gen.weekly_autopsy())
    print()

    print("=== TOKEN RAPORU: ETH ===")
    print(gen.token_report("ETH"))
    print()

    print("=== NARRATIF TREND ===")
    print(gen.narrative_trend_report())
