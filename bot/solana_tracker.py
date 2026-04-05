"""
Solana On-Chain Tracker
========================
Ethereum/BSC'ye ek olarak Solana ağındaki whale hareketlerini takip eder.

API Kaynakları:
  - Helius RPC (ücretsiz tier: 100k req/gün) → https://helius.dev
  - Solscan Public API                       → https://public-api.solscan.io
  - Jupiter Price API (token fiyatları)      → https://price.jup.ag

Takip Edilen Olaylar:
  - Büyük SOL transferleri (>10,000 SOL ~= $1.4M)
  - SPL token transferleri (>$100k USD)
  - Jupiter DEX'te büyük swap'lar
  - Raydium LP pozisyon değişiklikleri
  - Pump.fun yeni token launch'ları (influencer bağlantılı)

Solana Token Kontrat Adresleri:
  SOL   → So11111111111111111111111111111111111111112
  USDC  → EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v
  BONK  → DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263
  WIF   → EKpQGSJtjMFqKZ9KQanSqYXRcF8fBopzLHYxdM65zcjm
  JUP   → JUPyiwrYJFskUPiHa7hkeR8VUtAeFoSYbKedZNsDvCN
"""

import logging
import requests
from dataclasses import dataclass, field
from typing import Optional
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# API Endpointler
HELIUS_RPC_URL   = "https://mainnet.helius-rpc.com/?api-key={api_key}"
SOLSCAN_BASE     = "https://public-api.solscan.io"
JUPITER_PRICE    = "https://price.jup.ag/v6/price"

# Solana büyük işlem eşiği (SOL cinsinden)
SOL_WHALE_THRESHOLD = 10_000      # ~$1.4M

# Bilinen Solana borsa hot wallet'ları (exit signal için)
SOLANA_EXCHANGE_WALLETS: dict[str, str] = {
    "Binance":  "9WzDXwBbmkg8ZTbNMqUxvQRAyrZzDsGYdLVL9zYtAWWM",
    "OKX":      "FWznbcNXWQuHTawe9RxvQ2LdCENssh12dsznf4RiouN5",
    "Bybit":    "2AQdpHJ2JpcEgPiATUXjQxA8QmafFegfQwSLWSprPicm",
    "Kucoin":   "HVh6wHNBAsZx8PHfXMuJHRhfBaB8yfFT1siAgBPAWUvg",
}

# Bilinen akıllı Solana cüzdanları (lookonchain verileri)
SOLANA_SMART_WALLETS: set[str] = {
    "7cVfgArCheMR6FG7oSFNBCWrKJj7NhFVEMzGXzGf3QRt",
    "GThUX1Atko4tqhN2NaiTazWSeFWMuiUvfFnyJyUghFMJ",
    "5Q544fKrFoe6tsEbD7S8EmxGTJYAKtTVhAW5Q5pge4j1",
    "AC5RDfQFmDS1deWZos921JfqscXdByf8BKHs5ACWjtW2",
    "FKKtkzX3KkVCBHgBcMGDrkBLBLFiCjJUNHkwN8xzx6qv",  # Jump Crypto
    "3HYhQC6ne7SAVVY5DYB5PnHoThXFBMVH6ZNzBgcwbBad",
}


@dataclass
class SolanaWhaleEvent:
    signature:      str
    event_type:     str      # "SOL_TRANSFER" | "SPL_TRANSFER" | "DEX_SWAP" | "LP_CHANGE"
    from_wallet:    str
    to_wallet:      str
    token_symbol:   str
    amount_raw:     float
    amount_usd:     float
    program:        str      # "Jupiter" | "Raydium" | "System" | "Unknown"
    is_exit_signal: bool = False
    exchange_name:  Optional[str] = None
    detected_at:    str      = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    @property
    def short_sig(self) -> str:
        return f"{self.signature[:8]}...{self.signature[-4:]}"

    @property
    def solscan_url(self) -> str:
        return f"https://solscan.io/tx/{self.signature}"


class SolanaTracker:
    """Solana ağındaki whale olaylarını Helius + Solscan üzerinden takip eder."""

    def __init__(self, helius_api_key: str = "", solscan_api_key: str = ""):
        self.helius_key   = helius_api_key
        self.solscan_key  = solscan_api_key
        self._session     = requests.Session()
        self._session.headers.update({"User-Agent": "WhaleAlert-Bot/1.0"})
        self._price_cache: dict[str, float] = {}
        logger.info("SolanaTracker baslatildi")

    # ── Public API ─────────────────────────────────────────────────────────────

    def fetch_large_sol_transfers(
        self,
        limit: int = 50,
        min_sol: float = SOL_WHALE_THRESHOLD,
    ) -> list[SolanaWhaleEvent]:
        """
        Solscan üzerinden büyük SOL transferlerini çeker.
        Minimum SOL eşiğinin üzerindeki transferler döndürülür.
        """
        events = []
        try:
            url    = f"{SOLSCAN_BASE}/v2.0/transfer/sol"
            params = {
                "limit":   limit,
                "offset":  0,
                "exclude_vote": "true",
            }
            if self.solscan_key:
                self._session.headers["token"] = self.solscan_key

            resp = self._session.get(url, params=params, timeout=15)
            resp.raise_for_status()
            transfers = resp.json().get("data", [])

            sol_price = self._get_sol_price()

            for tx in transfers:
                lamports  = float(tx.get("lamport", 0))
                sol_amt   = lamports / 1e9
                usd_value = sol_amt * sol_price

                if sol_amt < min_sol:
                    continue

                from_addr  = tx.get("src_owner") or tx.get("from_address", "")
                to_addr    = tx.get("dst_owner")  or tx.get("to_address", "")
                sig        = tx.get("trans_id") or tx.get("signature", "")

                exchange_match = SOLANA_EXCHANGE_WALLETS.get(to_addr)

                events.append(SolanaWhaleEvent(
                    signature     = sig,
                    event_type    = "SOL_TRANSFER",
                    from_wallet   = from_addr,
                    to_wallet     = to_addr,
                    token_symbol  = "SOL",
                    amount_raw    = sol_amt,
                    amount_usd    = usd_value,
                    program       = "System",
                    is_exit_signal= exchange_match is not None,
                    exchange_name = exchange_match,
                ))

        except Exception as e:
            logger.error(f"Solana SOL transfer cekim hatasi: {e}")

        return events

    def fetch_token_whale_swaps(self, token_mint: str, ticker: str) -> list[SolanaWhaleEvent]:
        """
        Jupiter üzerinden belirli bir token için büyük swap işlemlerini çeker.
        Helius webhook veya Solscan DEX endpoint kullanılır.
        """
        events = []
        try:
            url    = f"{SOLSCAN_BASE}/v2.0/token/defi/activities"
            params = {"address": token_mint, "limit": 50}
            resp   = self._session.get(url, params=params, timeout=15)
            resp.raise_for_status()
            activities = resp.json().get("data", [])

            token_price = self._get_token_price(token_mint)

            for act in activities:
                amount    = float(act.get("amount", 0)) / (10 ** act.get("decimals", 9))
                usd_value = amount * token_price

                if usd_value < 50_000:   # 50k$ altını atla
                    continue

                events.append(SolanaWhaleEvent(
                    signature    = act.get("trans_id", ""),
                    event_type   = "DEX_SWAP",
                    from_wallet  = act.get("from_address", ""),
                    to_wallet    = act.get("to_address", ""),
                    token_symbol = ticker,
                    amount_raw   = amount,
                    amount_usd   = usd_value,
                    program      = act.get("platform", "Unknown"),
                ))

        except Exception as e:
            logger.error(f"Jupiter swap cekim hatasi ({ticker}): {e}")

        return events

    def is_smart_wallet(self, address: str) -> bool:
        """Adres bilinen akıllı Solana cüzdanlarından biri mi?"""
        return address in SOLANA_SMART_WALLETS

    # ── Fiyat Yardımcıları ─────────────────────────────────────────────────────

    def _get_sol_price(self) -> float:
        cached = self._price_cache.get("SOL")
        if cached:
            return cached
        try:
            resp = self._session.get(
                JUPITER_PRICE,
                params={"ids": "So11111111111111111111111111111111111111112"},
                timeout=8,
            )
            data  = resp.json().get("data", {})
            price = data.get("So11111111111111111111111111111111111111112", {}).get("price", 140)
            self._price_cache["SOL"] = price
            return price
        except Exception:
            return 140.0   # fallback

    def _get_token_price(self, mint: str) -> float:
        cached = self._price_cache.get(mint)
        if cached:
            return cached
        try:
            resp  = self._session.get(JUPITER_PRICE, params={"ids": mint}, timeout=8)
            price = resp.json().get("data", {}).get(mint, {}).get("price", 0)
            self._price_cache[mint] = price
            return price
        except Exception:
            return 0.0

    # ── Özet ───────────────────────────────────────────────────────────────────

    def analyze_events(self, events: list[SolanaWhaleEvent]) -> dict:
        """
        Olay listesini analiz eder, exit/accumulation sinyallerini gruplar.
        """
        exit_events  = [e for e in events if e.is_exit_signal]
        accum_events = [
            e for e in events
            if not e.is_exit_signal and self.is_smart_wallet(e.from_wallet)
        ]
        total_exit_usd  = sum(e.amount_usd for e in exit_events)
        total_accum_usd = sum(e.amount_usd for e in accum_events)

        verdict = "NEUTRAL"
        if len(exit_events) >= 2 or total_exit_usd > 500_000:
            verdict = "EXIT_WARNING"
        elif len(accum_events) >= 1:
            verdict = "INSIDER_ACCUMULATION"

        return {
            "verdict":         verdict,
            "total_events":    len(events),
            "exit_count":      len(exit_events),
            "accum_count":     len(accum_events),
            "total_exit_usd":  total_exit_usd,
            "total_accum_usd": total_accum_usd,
            "top_events":      events[:5],
        }
