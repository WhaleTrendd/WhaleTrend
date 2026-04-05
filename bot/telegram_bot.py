"""
Telegram Alert Bot
==================
Webhook veya polling modunda çalışan Telegram botu.
Whale Trend analizlerini formatlanmış mesajlar halinde
kanallara ve özel mesajlara iletir.
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional

from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import TelegramError
from telegram.constants import ParseMode

from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_IDS
from nlp_analyzer import AnalysisResult
from onchain_tracker import WhaleAnalysis

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────────────
# Mesaj Formatlayıcı
# ──────────────────────────────────────────────────────────────────────────────

class AlertFormatter:
    """Analiz sonuçlarını Telegram Markdown formatına çevirir."""

    # Emoji haritası
    _SENTIMENT_EMOJI = {"BULLISH": "🟢", "BEARISH": "🔴", "NEUTRAL": "⚪"}
    _VERDICT_EMOJI   = {
        "EXIT_WARNING":        "🚨",
        "INSIDER_ACCUMULATION":"💎",
        "NEUTRAL":             "📊",
    }

    @classmethod
    def format_mismatch_alert(
        cls,
        nlp: AnalysisResult,
        onchain: WhaleAnalysis,
    ) -> str:
        """
        Senaryo A veya B için tam uyarı mesajı oluşturur.
        """
        now   = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        v_emo = cls._VERDICT_EMOJI.get(onchain.verdict, "📊")
        s_emo = cls._SENTIMENT_EMOJI.get(nlp.sentiment_label, "⚪")

        tickers_str = " ".join(f"${t}" for t in nlp.tickers) if nlp.tickers else "—"
        themes_str  = ", ".join(nlp.themes) if nlp.themes else "—"

        lines = [
            f"{v_emo} *WHALE TREND ALERT*",
            f"`{now}`",
            "",
        ]

        # Senaryo belirleme
        if onchain.verdict == "EXIT_WARNING":
            lines += [
                "━━━━━━━━━━━━━━━━━━━━━━━",
                "🚨 *SCENARIO A — EXIT WARNING*",
                "━━━━━━━━━━━━━━━━━━━━━━━",
                f"KOL **@{nlp.author}** bullish tweet attı,",
                f"ama elit whale'ler **borsaya para gönderiyor!**",
                "",
            ]
        elif onchain.verdict == "INSIDER_ACCUMULATION":
            lines += [
                "━━━━━━━━━━━━━━━━━━━━━━━",
                "💎 *SCENARIO B — INSIDER ACCUMULATION*",
                "━━━━━━━━━━━━━━━━━━━━━━━",
                f"**@{nlp.author}** yeni bir konsept paylaştı,",
                f"smart money **sessizce biriktiriyor!**",
                "",
            ]
        else:
            lines += [
                "━━━━━━━━━━━━━━━━━━━━━━━",
                f"📊 *SIGNAL DETECTED*",
                "━━━━━━━━━━━━━━━━━━━━━━━",
                "",
            ]

        lines += [
            f"👤 *Kaynak:* @{nlp.author}",
            f"🏷️ *Ticker(lar):* {tickers_str}",
            f"{s_emo} *Sentiment:* {nlp.sentiment_label} ({nlp.sentiment_score:+.2f})",
            f"🎯 *Temalar:* {themes_str}",
            "",
            f"💬 *Tweet:*",
            f'_{cls._escape(nlp.text[:280])}_',
            f"[Tweeti Gör]({nlp.tweet_url})",
            "",
        ]

        # On-chain özet
        lines.append("🔗 *On-Chain Özet:*")
        if onchain.exit_signals:
            lines.append(f"  🔴 Borsa Deposit: {len(onchain.exit_signals)} işlem — ${onchain.total_exit_usd:,.0f}")
            for tx in onchain.exit_signals[:2]:
                lines.append(f"    └ {tx.exchange_name} / {tx.chain} / `{tx.tx_hash[:12]}...`")
        if onchain.accumulations:
            lines.append(f"  🟢 Birikim: {len(onchain.accumulations)} işlem — ${onchain.total_accum_usd:,.0f}")
            for tx in onchain.accumulations[:2]:
                lines.append(f"    └ {tx.chain} / `{tx.tx_hash[:12]}...`")
        if onchain.total_scanned == 0:
            lines.append("  ℹ️ On-chain veri bulunamadı")

        lines += [
            "",
            f"⚡ _WhaleTrend Alpha Agent • Sadece $WHALE hodler'larına_",
        ]

        return "\n".join(lines)

    @classmethod
    def format_simple_alert(cls, nlp: AnalysisResult) -> str:
        """
        On-chain verisi olmadan yalnızca NLP sonucunu ileten kısa mesaj.
        """
        s_emo = cls._SENTIMENT_EMOJI.get(nlp.sentiment_label, "⚪")
        tickers_str = " ".join(f"${t}" for t in nlp.tickers)
        themes_str  = ", ".join(nlp.themes) if nlp.themes else ""
        now = datetime.now(timezone.utc).strftime("%H:%M UTC")

        text = (
            f"{s_emo} *@{nlp.author}* — `{now}`\n"
            f"🏷️ {tickers_str}"
            + (f" | 🎯 {themes_str}" if themes_str else "") + "\n"
            f"_{cls._escape(nlp.text[:200])}_\n"
            f"[→ Tweet]({nlp.tweet_url})"
        )
        return text

    @staticmethod
    def _escape(text: str) -> str:
        """Telegram Markdown v1 için özel karakterleri escape eder."""
        for char in ["_", "*", "`", "["]:
            text = text.replace(char, "\\" + char)
        return text


# ──────────────────────────────────────────────────────────────────────────────
# Telegram Bot Sınıfı
# ──────────────────────────────────────────────────────────────────────────────

class TelegramAlertBot:
    """Analiz sonuçlarını Telegram'a ileten bot."""

    def __init__(self):
        if not TELEGRAM_BOT_TOKEN:
            raise ValueError("TELEGRAM_BOT_TOKEN eksik! .env dosyanızı kontrol edin.")
        self.bot       = Bot(token=TELEGRAM_BOT_TOKEN)
        self.chat_ids  = [cid.strip() for cid in TELEGRAM_CHAT_IDS if cid.strip()]
        self.formatter = AlertFormatter()
        logger.info(f"TelegramBot başlatıldı → {len(self.chat_ids)} kanal/kullanıcı")

    async def send_mismatch_alert(
        self,
        nlp: AnalysisResult,
        onchain: WhaleAnalysis,
    ) -> None:
        """Senaryo A/B için tam uyarı mesajı gönderir."""
        text = AlertFormatter.format_mismatch_alert(nlp, onchain)
        buttons = self._build_keyboard(nlp)
        await self._broadcast(text, reply_markup=buttons)

    async def send_simple_alert(self, nlp: AnalysisResult) -> None:
        """On-chain verisi olmadan sadece NLP alert'i gönderir."""
        text = AlertFormatter.format_simple_alert(nlp)
        await self._broadcast(text)

    async def send_text(self, message: str) -> None:
        """Ham metin mesajı gönderir (sistem bildirimleri için)."""
        await self._broadcast(message, parse_mode=None)

    async def send_startup_message(self) -> None:
        """Bot başlangıcında bilgilendirme mesajı gönderir."""
        msg = (
            "🐋 *WHALE TREND BOT BAŞLATILDI*\n\n"
            "✅ Twitter tarama aktif\n"
            "✅ NLP motoru hazır\n"
            "✅ On-chain tracker bağlandı\n"
            "✅ Telegram bildirimleri etkin\n\n"
            "_Mismatch sinyalleri gerçek zamanlı iletilecek..._"
        )
        await self._broadcast(msg)

    # ── İç Metodlar ────────────────────────────────────────────────────────────

    async def _broadcast(
        self,
        text: str,
        parse_mode: Optional[str] = ParseMode.MARKDOWN,
        reply_markup=None,
    ) -> None:
        """Tüm kayıtlı chat_id'lere mesaj gönderir."""
        for chat_id in self.chat_ids:
            try:
                await self.bot.send_message(
                    chat_id    = chat_id,
                    text       = text,
                    parse_mode = parse_mode,
                    reply_markup = reply_markup,
                    disable_web_page_preview = False,
                )
                logger.debug(f"Mesaj gönderildi → {chat_id}")
            except TelegramError as e:
                logger.error(f"Telegram hatası ({chat_id}): {e}")
            except Exception as e:
                logger.error(f"Beklenmedik hata ({chat_id}): {e}")

    @staticmethod
    def _build_keyboard(nlp: AnalysisResult) -> Optional[InlineKeyboardMarkup]:
        """Tweet ve Etherscan için inline butonlar oluşturur."""
        buttons = [[
            InlineKeyboardButton("🐦 Tweet", url=nlp.tweet_url),
        ]]
        if nlp.primary_ticker:
            dex_url = f"https://dexscreener.com/search?q={nlp.primary_ticker}"
            buttons[0].append(
                InlineKeyboardButton(f"📈 DEX Chart", url=dex_url)
            )
        return InlineKeyboardMarkup(buttons)

    # ── Senkron wrapper (main.py kolaylığı için) ───────────────────────────────

    def send_mismatch_alert_sync(self, nlp: AnalysisResult, onchain: WhaleAnalysis):
        asyncio.run(self.send_mismatch_alert(nlp, onchain))

    def send_simple_alert_sync(self, nlp: AnalysisResult):
        asyncio.run(self.send_simple_alert(nlp))

    def send_startup_sync(self):
        asyncio.run(self.send_startup_message())
