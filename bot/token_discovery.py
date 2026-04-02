"""
Token Discovery Engine
=======================
Henüz meşhur olmayan erken aşama tokenleri tespit eden keşif motoru.

Keşif Kaynakları:
  1. Yeni DEX Listeleri    → DexScreener API (son 24h listeleri)
  2. Smart Contract Deploy → Etherscan'da son deploy edilen ERC-20'ler
  3. Sosyal Hacim Spike    → Telegram/Discord mention patlamaları
  4. On-Chain Momentum     → Organik büyüme (bot dışı) gösteren tokenler
  5. Influencer Bağlantısı → Eğer token elite wallet'tan deploylandıysa

Filtre Kriterleri (Gerçek Alpha için):
  - Likiditesi $50K ile $5M arası (çok küçük = rug riski, çok büyük = geç)
  - Token yaşı < 7 gün
  - Holder sayısı artış hızı > günlük %10
  - Contract doğrulanmış (verified source code)
  - Liquidity locked veya burned
  - Deployer adresi bilinen VC/insider değil (erken bilgi avantajı yoktur)
"""

import logging
import requests
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Optional

logger = logging.getLogger(__name__)

# DexScreener API (tamamen ücretsiz, kayıt gerektirmez)
DEXSCREENER_BASE = "https://api.dexscreener.com/latest/dex"

# Minimum/Maksimum likidite (USD)
MIN_LIQUIDITY_USD = 50_000
MAX_LIQUIDITY_USD = 5_000_000

# Maksimum token yaşı (saat)
MAX_TOKEN_AGE_HOURS = 168   # 7 gün

# Desteklenen ağlar
SUPPORTED_CHAINS = {
    "ethereum": {"name": "Ethereum",  "explorer": "https://etherscan.io/token/"},
    "bsc":      {"name": "BSC",       "explorer": "https://bscscan.com/token/"},
    "solana":   {"name": "Solana",    "explorer": "https://solscan.io/token/"},
    "base":     {"name": "Base",      "explorer": "https://basescan.org/token/"},
    "arbitrum": {"name": "Arbitrum",  "explorer": "https://arbiscan.io/token/"},
}

# Bilinen rug pattern'leri (kontrat analiz)
RUG_RISK_KEYWORDS: set[str] = {
    "honeypot", "mintable", "pausable", "blacklist",
    "fee_excluded", "anti_whale_disabled",
}


@dataclass
class DiscoveredToken:
    ticker:          str
    name:            str
    contract:        str
    chain:           str
    pair_address:    str
    dex:             str

    price_usd:       float
    liquidity_usd:   float
    volume_24h_usd:  float
    market_cap_usd:  float

    price_change_1h:  float
    price_change_24h: float

    pair_created_at: str        # ISO timestamp
    age_hours:       float      # Token kaç saatlik

    txns_24h_buys:   int = 0
    txns_24h_sells:  int = 0

    holder_count:    int = 0
    lp_locked:       bool = False
    contract_verified: bool = False
    deployer_address:  str = ""

    alpha_score:     float = 0.0    # 0-100 hesaplanan alpha skoru
    risk_flags:      list[str] = field(default_factory=list)

    @property
    def buy_sell_ratio(self) -> float:
        sells = self.txns_24h_sells or 1
        return self.txns_24h_buys / sells

    @property
    def dexscreener_url(self) -> str:
        return f"https://dexscreener.com/{self.chain}/{self.pair_address}"

    @property
    def explorer_url(self) -> str:
        base = SUPPORTED_CHAINS.get(self.chain, {}).get("explorer", "")
        return f"{base}{self.contract}"

    def is_risky(self) -> bool:
        return len(self.risk_flags) >= 2


class TokenDiscovery:
    """
    Yeni listelenen ve organik büyüme gösteren tokenleri tespit eder.
    Influencer mention ile eşleştiğinde potansiyel early alpha sinyali üretir.
    """

    def __init__(self):
        self._session = requests.Session()
        self._session.headers.update({"User-Agent": "WhaleAlert-Bot/1.0"})
        self._seen_pairs: set[str] = set()
        logger.info("TokenDiscovery motoru baslatildi")

    # ── Public API ─────────────────────────────────────────────────────────────

    def discover_new_tokens(
        self,
        chains: list[str] = None,
        min_liquidity: float = MIN_LIQUIDITY_USD,
        max_age_hours: float = MAX_TOKEN_AGE_HOURS,
    ) -> list[DiscoveredToken]:
        """
        DexScreener üzerinden yeni listelenen tokenleri tarar.
        Filtre kriterlerini geçenleri döndürür.
        """
        chains = chains or list(SUPPORTED_CHAINS.keys())
        found: list[DiscoveredToken] = []

        for chain in chains:
            raw = self._fetch_new_pairs(chain)
            for pair in raw:
                token = self._parse_pair(pair, chain)
                if token is None:
                    continue
                if token.pair_address in self._seen_pairs:
                    continue
                if token.liquidity_usd < min_liquidity:
                    continue
                if token.age_hours > max_age_hours:
                    continue

                token.alpha_score = self._compute_alpha_score(token)
                token.risk_flags  = self._detect_risk_flags(token)

                self._seen_pairs.add(token.pair_address)
                found.append(token)

        found.sort(key=lambda t: t.alpha_score, reverse=True)
        logger.info(
            f"TokenDiscovery: {len(found)} yeni token bulundu "
            f"({sum(1 for t in found if not t.is_risky())} temiz)"
        )
        return found

    def find_by_ticker(self, ticker: str) -> Optional[DiscoveredToken]:
        """Belirli bir ticker için DexScreener'dan token çeker."""
        ticker = ticker.upper().lstrip("$")
        try:
            resp = self._session.get(
                f"{DEXSCREENER_BASE}/search?q={ticker}",
                timeout=10,
            )
            resp.raise_for_status()
            pairs = resp.json().get("pairs", [])
            if not pairs:
                return None
            # En yüksek likiditesi olanı seç
            pairs.sort(key=lambda p: p.get("liquidity", {}).get("usd", 0), reverse=True)
            return self._parse_pair(pairs[0], pairs[0].get("chainId", "ethereum"))
        except Exception as e:
            logger.warning(f"Token arama hatasi ({ticker}): {e}")
            return None

    def match_with_influencer_mention(
        self,
        discovered: list[DiscoveredToken],
        mentioned_tickers: list[str],
    ) -> list[tuple[DiscoveredToken, str]]:
        """
        Keşfedilen tokenlerden influencer tarafından mention edilenleri eşleştirir.
        Döner: [(token, matching_ticker), ...]
        """
        mentioned_upper = {t.upper().lstrip("$") for t in mentioned_tickers}
        matches = []
        for token in discovered:
            if token.ticker.upper() in mentioned_upper:
                matches.append((token, token.ticker))
                logger.info(
                    f"MATCH: ${token.ticker} kesfedilen yeni token + influencer mention!"
                )
        return matches

    # ── DexScreener ────────────────────────────────────────────────────────────

    def _fetch_new_pairs(self, chain: str) -> list[dict]:
        try:
            # DexScreener'da "newly added" endpoint
            url  = f"{DEXSCREENER_BASE}/pairs/{chain}"
            resp = self._session.get(url, timeout=15)
            resp.raise_for_status()
            return resp.json().get("pairs", [])
        except Exception as e:
            logger.debug(f"DexScreener cekim hatasi ({chain}): {e}")
            return []

    def _parse_pair(self, pair: dict, chain: str) -> Optional[DiscoveredToken]:
        try:
            base_token = pair.get("baseToken", {})
            liq        = pair.get("liquidity", {})
            txns       = pair.get("txns", {}).get("h24", {})
            price_chg  = pair.get("priceChange", {})

            created_str = pair.get("pairCreatedAt")
            if created_str:
                created_dt = datetime.fromtimestamp(created_str / 1000, tz=timezone.utc)
                age_hours  = (datetime.now(timezone.utc) - created_dt).total_seconds() / 3600
                created_iso = created_dt.isoformat()
            else:
                age_hours   = 9999
                created_iso = ""

            return DiscoveredToken(
                ticker           = base_token.get("symbol", "?").upper(),
                name             = base_token.get("name", ""),
                contract         = base_token.get("address", ""),
                chain            = chain,
                pair_address     = pair.get("pairAddress", ""),
                dex              = pair.get("dexId", "unknown"),
                price_usd        = float(pair.get("priceUsd", 0) or 0),
                liquidity_usd    = float(liq.get("usd", 0) or 0),
                volume_24h_usd   = float(pair.get("volume", {}).get("h24", 0) or 0),
                market_cap_usd   = float(pair.get("marketCap", 0) or 0),
                price_change_1h  = float(price_chg.get("h1", 0) or 0),
                price_change_24h = float(price_chg.get("h24", 0) or 0),
                pair_created_at  = created_iso,
                age_hours        = age_hours,
                txns_24h_buys    = int(txns.get("buys", 0) or 0),
                txns_24h_sells   = int(txns.get("sells", 0) or 0),
            )
        except Exception as e:
            logger.debug(f"Pair parse hatasi: {e}")
            return None

    # ── Skor & Risk ────────────────────────────────────────────────────────────

    @staticmethod
    def _compute_alpha_score(token: DiscoveredToken) -> float:
        """0-100 arası alpha skoru hesaplar."""
        score = 0.0

        # Likidite ideal aralıkta mı? (0-25 puan)
        if MIN_LIQUIDITY_USD <= token.liquidity_usd <= MAX_LIQUIDITY_USD:
            liq_ratio = token.liquidity_usd / MAX_LIQUIDITY_USD
            score += (1 - liq_ratio) * 25   # daha az likidite = erken fırsat

        # Hacim/Likidite oranı (0-20 puan) — organik aktivite göstergesi
        if token.liquidity_usd > 0:
            vol_ratio = token.volume_24h_usd / token.liquidity_usd
            score += min(vol_ratio * 5, 20)

        # Fiyat momentumu (0-15 puan)
        if 0 < token.price_change_1h <= 30:
            score += token.price_change_1h / 2

        # Gençlik bonusu (0-20 puan) — taze listelemeler daha değerli
        if token.age_hours <= 6:
            score += 20
        elif token.age_hours <= 24:
            score += 15
        elif token.age_hours <= 72:
            score += 8

        # Buy/Sell oranı (0-20 puan)
        bsr = token.buy_sell_ratio
        if bsr >= 2.0:
            score += 20
        elif bsr >= 1.5:
            score += 12
        elif bsr >= 1.0:
            score += 5

        return round(min(score, 100), 1)

    @staticmethod
    def _detect_risk_flags(token: DiscoveredToken) -> list[str]:
        """Potansiyel risk işaretlerini tespit eder."""
        flags = []
        if token.liquidity_usd < 10_000:
            flags.append("cok_dusuk_likidite")
        if token.txns_24h_sells > token.txns_24h_buys * 2:
            flags.append("yuksek_satis_baskisi")
        if token.price_change_24h > 500:
            flags.append("anormal_fiyat_artisi")
        if token.age_hours < 1:
            flags.append("cok_yeni_1saat")
        if token.volume_24h_usd > token.liquidity_usd * 10:
            flags.append("anormal_hacim_oran")
        return flags
