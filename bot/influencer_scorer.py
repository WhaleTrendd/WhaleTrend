"""
Influencer Scoring Engine
==========================
Her bir takip edilen X/Twitter hesabına dinamik etki puanı atar.

Puan Hesaplama Faktörleri:
  1. Geçmiş Doğruluk Oranı   — Bu hesabın önceki alertleri ne kadar doğru çıktı?
  2. Takipçi Ağırlığı        — Follower sayısına göre normalize edilmiş etki
  3. Etkileşim Oranı         — Likes + Retweets / Follower (gerçek etki ölçüsü)
  4. İçeriden Bilgi Tespiti  — Önceden doğru tahmin sayısı
  5. Manipülasyon Geçmişi    — Bilinen pump&dump teşviki (negatif puan)
  6. Hesap Yaşı & Otantiklik — Köklü hesaplar daha güvenilir

Kullanım:
  Her NLP analiz sonucunda hesabın ağırlıklı skoru alert önceliğini artırır.
  Yüksek skorlu hesap BULLISH dedi → alarm eşiği %30 düşürülür.
  Manipülatör hesap BULLISH dedi   → alarm eşiği %50 artırılır (ters filtre).
"""

import json
import logging
import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

SCORES_FILE = Path("data/influencer_scores.json")


# ──────────────────────────────────────────────────────────────────────────────
# Statik Temel Veriler (gerçekte Twitter API'den çekilir)
# ──────────────────────────────────────────────────────────────────────────────

INFLUENCER_METADATA: dict[str, dict] = {
    "VitalikButerin": {
        "followers":         6_200_000,
        "account_age_years": 13,
        "category":          "Founder",
        "verified":          True,
        "known_manipulator": False,
        "insider_calls":     18,      # Doğrulanmış erken bilgi paylaşımı
        "base_accuracy":     0.82,    # Geçmiş tahmin doğruluğu (~%82)
        "notes":             "Ethereum kurucusu. ZK ve L2 sinyalleri yüksek değer taşır.",
    },
    "saylor": {
        "followers":         4_100_000,
        "account_age_years": 14,
        "category":          "Macro/VC",
        "verified":          True,
        "known_manipulator": False,
        "insider_calls":     6,
        "base_accuracy":     0.71,
        "notes":             "MicroStrategy CEO. BTC kurumsal birikim sinyalleri.",
    },
    "elonmusk": {
        "followers":         196_000_000,
        "account_age_years": 17,
        "category":          "Celebrity",
        "verified":          True,
        "known_manipulator": True,    # DOGE tweet manipülasyonu geçmişi
        "insider_calls":     3,
        "base_accuracy":     0.48,    # Piyasa tahminlerinde düşük doğruluk
        "notes":             "Yüksek kitlesel etki, ancak manipülasyon geçmişi var. Ters sinyal potansiyeli.",
    },
    "brian_armstrong": {
        "followers":         1_700_000,
        "account_age_years": 13,
        "category":          "Founder",
        "verified":          True,
        "known_manipulator": False,
        "insider_calls":     9,       # Coinbase listing öncesi sinyaller
        "base_accuracy":     0.75,
        "notes":             "Coinbase CEO. Listing sinyalleri ve regülasyon verileri için öncelikli.",
    },
    "cz_binance": {
        "followers":         10_200_000,
        "account_age_years": 10,
        "category":          "Exchange",
        "verified":          True,
        "known_manipulator": False,
        "insider_calls":     12,
        "base_accuracy":     0.68,
        "notes":             "Binance CEO. BNB ekosistemi ve exchange listing sinyalleri.",
    },
    "APompliano": {
        "followers":         1_600_000,
        "account_age_years": 11,
        "category":          "Macro",
        "verified":          True,
        "known_manipulator": False,
        "insider_calls":     4,
        "base_accuracy":     0.64,
        "notes":             "Kurumsal BTC savunucusu. Makro ekonomi perspektifi.",
    },
    "cdixon": {
        "followers":         890_000,
        "account_age_years": 15,
        "category":          "VC",
        "verified":          True,
        "known_manipulator": False,
        "insider_calls":     14,      # A16z portföy şirketlerine erken değinme
        "base_accuracy":     0.77,
        "notes":             "A16z kripto partneri. Web3 ve DeFi yatırım sinyalleri.",
    },
    "BalajiS": {
        "followers":         1_050_000,
        "account_age_years": 14,
        "category":          "Founder/VC",
        "verified":          True,
        "known_manipulator": False,
        "insider_calls":     11,
        "base_accuracy":     0.79,
        "notes":             "Derin teknoloji ve makro gorus. Bitcoin price bet gecmisi.",
    },
    "ErikVoorhees": {
        "followers":         290_000,
        "account_age_years": 13,
        "category":          "Founder",
        "verified":          True,
        "known_manipulator": False,
        "insider_calls":     5,
        "base_accuracy":     0.70,
        "notes":             "ShapeShift kurucusu. DeFi ve özgürlük protokolleri.",
    },
    "MMCrypto": {
        "followers":         980_000,
        "account_age_years": 7,
        "category":          "Influencer",
        "verified":          True,
        "known_manipulator": True,    # Leverage tuzakları için kullanılıyor
        "insider_calls":     1,
        "base_accuracy":     0.44,
        "notes":             "Kaldiraç izci. Yüksek bullish sinyallerinde ters pozisyon al.",
    },
    "lookonchain": {
        "followers":         450_000,
        "account_age_years": 4,
        "category":          "DataAccount",
        "verified":          True,
        "known_manipulator": False,
        "insider_calls":     31,      # On-chain veriye dayalı gerçek insider tespiti
        "base_accuracy":     0.88,
        "notes":             "On-chain veritabanlı hesap. En yüksek dogruluk orani.",
    },
    "whale_alert": {
        "followers":         1_100_000,
        "account_age_years": 6,
        "category":          "DataAccount",
        "verified":          True,
        "known_manipulator": False,
        "insider_calls":     0,
        "base_accuracy":     0.95,   # Ham veri paylaşımı — yorum yok, doğruluk yüksek
        "notes":             "Otomatik whale transfer botu. Ham veri kaynagi olarak kullan.",
    },
}


# ──────────────────────────────────────────────────────────────────────────────
# Puan Sınıfı
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class InfluencerScore:
    account:          str
    composite_score:  float    # 0.0 – 10.0
    accuracy_score:   float
    influence_score:  float
    insider_score:    float
    manipulation_penalty: float
    category:         str
    known_manipulator: bool
    recommendation:   str      # "TRUST" | "CAUTION" | "INVERSE"

    def alert_threshold_modifier(self) -> float:
        """
        Sentiment eşiğini ne kadar değiştirmeli?
        0.5 → eşiği yarıya indir (çok güvenilir)
        2.0 → eşiği iki katına çıkar (manipülatör)
        1.0 → değişiklik yok
        """
        if self.known_manipulator:
            return 1.8
        if self.composite_score >= 8.0:
            return 0.6
        if self.composite_score >= 6.0:
            return 0.8
        if self.composite_score <= 3.0:
            return 1.4
        return 1.0


# ──────────────────────────────────────────────────────────────────────────────
# Puanlama Motoru
# ──────────────────────────────────────────────────────────────────────────────

class InfluencerScorer:
    """
    Takip edilen X/Twitter hesaplarını dinamik olarak puanlar.
    Puanlar her döngüde güncellenerek geçmiş doğruluk oranına göre evrilir.
    """

    def __init__(self):
        self._scores: dict[str, InfluencerScore] = {}
        self._alert_history: dict[str, list[dict]] = {}  # account → [{ticker, verdict, correct}]
        self._build_initial_scores()
        logger.info(f"InfluencerScorer: {len(self._scores)} hesap puanlandi")

    # ── İlk Yükleme ────────────────────────────────────────────────────────────

    def _build_initial_scores(self):
        for account, meta in INFLUENCER_METADATA.items():
            score = self._compute_score(account, meta)
            self._scores[account] = score

    def _compute_score(self, account: str, meta: dict) -> InfluencerScore:
        # 1. Doğruluk skoru (0-4 puan)
        accuracy = meta.get("base_accuracy", 0.5) * 4.0

        # 2. Etki skoru: log10(followers) normalized (0-3 puan)
        followers = meta.get("followers", 10_000)
        influence = min(math.log10(max(followers, 1)) / math.log10(200_000_000) * 3.0, 3.0)

        # 3. Insider skoru: doğrulanmış erken bilgi sayısı (0-2 puan)
        insider   = min(meta.get("insider_calls", 0) / 20.0 * 2.0, 2.0)

        # 4. Manipülasyon cezası (-0 ile -3 puan)
        manip_penalty = 3.0 if meta.get("known_manipulator") else 0.0

        # 5. Hesap yaşı (0-1 puan)
        age_bonus = min(meta.get("account_age_years", 0) / 15.0, 1.0)

        composite = max(0.0, accuracy + influence + insider - manip_penalty + age_bonus)
        composite = round(min(composite, 10.0), 2)

        # Öneri belirleme
        if meta.get("known_manipulator"):
            recommendation = "INVERSE"
        elif composite >= 7.0:
            recommendation = "TRUST"
        else:
            recommendation = "CAUTION"

        return InfluencerScore(
            account              = account,
            composite_score      = composite,
            accuracy_score       = round(accuracy, 2),
            influence_score      = round(influence, 2),
            insider_score        = round(insider, 2),
            manipulation_penalty = manip_penalty,
            category             = meta.get("category", "Unknown"),
            known_manipulator    = meta.get("known_manipulator", False),
            recommendation       = recommendation,
        )

    # ── Public API ─────────────────────────────────────────────────────────────

    def get_score(self, account: str) -> Optional[InfluencerScore]:
        return self._scores.get(account)

    def get_threshold_modifier(self, account: str) -> float:
        score = self.get_score(account)
        return score.alert_threshold_modifier() if score else 1.0

    def record_outcome(self, account: str, ticker: str, verdict: str, was_correct: bool):
        """
        Alert sonucunu kaydet (doğruluk güncelleme için).
        was_correct: Alert'in öngördüğü yön doğru çıktı mı?
        """
        if account not in self._alert_history:
            self._alert_history[account] = []
        self._alert_history[account].append({
            "ticker":     ticker,
            "verdict":    verdict,
            "correct":    was_correct,
            "recorded":   datetime.now(timezone.utc).isoformat(),
        })
        # Hesabın doğruluk skorunu dinamik güncelle
        self._update_accuracy(account)

    def _update_accuracy(self, account: str):
        """Geçmiş kayıtlara göre hesabın doğruluk skorunu yeniden hesaplar."""
        history = self._alert_history.get(account, [])
        if len(history) < 5:   # minimum 5 kayıt gerekli
            return
        correct    = sum(1 for h in history[-50:] if h["correct"])   # son 50 alert
        total      = min(len(history), 50)
        new_acc    = correct / total

        meta = INFLUENCER_METADATA.get(account, {})
        meta["base_accuracy"] = new_acc   # in-memory güncelleme
        score = self._compute_score(account, meta)
        self._scores[account] = score
        logger.info(
            f"Influencer skoru guncellendi: @{account} → "
            f"{score.composite_score} ({new_acc:.1%} dogr.)"
        )

    def top_accounts(self, n: int = 5, category: str = None) -> list[InfluencerScore]:
        """En yüksek skorlu N hesabı döner."""
        scores = list(self._scores.values())
        if category:
            scores = [s for s in scores if s.category == category]
        return sorted(scores, key=lambda s: s.composite_score, reverse=True)[:n]

    def leaderboard(self) -> str:
        """Tüm hesapların puan tablosunu döner."""
        lines = [f"{'Hesap':22} {'Skor':5} {'Dogruluk':8} {'Kategori':14} {'Oneri'}"]
        lines.append("-" * 65)
        for s in sorted(self._scores.values(), key=lambda x: x.composite_score, reverse=True):
            manip = " [MANIPULATOR]" if s.known_manipulator else ""
            lines.append(
                f"@{s.account:20} {s.composite_score:5.1f} "
                f"{s.accuracy_score:7.1f}  {s.category:14} "
                f"{s.recommendation}{manip}"
            )
        return "\n".join(lines)
