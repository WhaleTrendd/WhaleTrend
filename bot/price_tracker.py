"""
Price Tracker
=============
CoinGecko ücretsiz API üzerinden gerçek zamanlı token fiyatlarını,
piyasa değerini ve 24h hacmini çeker.

Özellikler:
  - Ticker → CoinGecko ID eşlemesi
  - TTL cache (her token 60s'de bir güncellenir)
  - USD cinsinden fiyat, market cap, volume, 24h change
  - Whale işlem değerini USD'ye çevirmek için kullanılır
  - Alert mesajlarına fiyat bağlamı ekler
"""

import time
import logging
import requests
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)

# CoinGecko ücretsiz API — kayıt gerektirmez
COINGECKO_BASE = "https://api.coingecko.com/api/v3"

# Önbellek TTL (saniye)
CACHE_TTL = 60


# ──────────────────────────────────────────────────────────────────────────────
# Veri Sınıfı
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class TokenPrice:
    ticker:           str
    coingecko_id:     str
    price_usd:        float
    market_cap_usd:   float
    volume_24h_usd:   float
    change_24h_pct:   float
    fetched_at:       float = field(default_factory=time.time)

    @property
    def is_stale(self) -> bool:
        return (time.time() - self.fetched_at) > CACHE_TTL

    @property
    def trend_emoji(self) -> str:
        if self.change_24h_pct >= 5:
            return "🚀"
        elif self.change_24h_pct >= 1:
            return "📈"
        elif self.change_24h_pct <= -5:
            return "💥"
        elif self.change_24h_pct <= -1:
            return "📉"
        return "➡️"

    def summary(self) -> str:
        return (
            f"{self.trend_emoji} ${self.ticker} "
            f"${self.price_usd:,.4f} "
            f"({self.change_24h_pct:+.1f}% 24h) "
            f"| Vol: ${self.volume_24h_usd:,.0f}"
        )


# ──────────────────────────────────────────────────────────────────────────────
# Ticker → CoinGecko ID Haritası
# ──────────────────────────────────────────────────────────────────────────────

TICKER_TO_CG_ID: dict[str, str] = {
    "BTC":   "bitcoin",
    "ETH":   "ethereum",
    "BNB":   "binancecoin",
    "SOL":   "solana",
    "MATIC": "matic-network",
    "AVAX":  "avalanche-2",
    "ARB":   "arbitrum",
    "OP":    "optimism",
    "LINK":  "chainlink",
    "UNI":   "uniswap",
    "AAVE":  "aave",
    "MKR":   "maker",
    "COMP":  "compound-governance-token",
    "SNX":   "synthetix-network-token",
    "CRV":   "curve-dao-token",
    "BAL":   "balancer",
    "DOGE":  "dogecoin",
    "SHIB":  "shiba-inu",
    "PEPE":  "pepe",
    "FLOKI": "floki",
    "TURBO": "turbo",
    "WIF":   "dogwifcoin",
    "BONK":  "bonk",
    "POPCAT":"popcat",
    "GRASS": "grass",
    "ONDO":  "ondo-finance",
    "POLYX": "polymesh",
    "TRX":   "tron",
    "TON":   "the-open-network",
    "DOT":   "polkadot",
    "ADA":   "cardano",
    "XRP":   "ripple",
    "LTC":   "litecoin",
    "BCH":   "bitcoin-cash",
    "ETC":   "ethereum-classic",
    "FIL":   "filecoin",
    "INJ":   "injective-protocol",
    "SUI":   "sui",
    "APT":   "aptos",
    "SEI":   "sei-network",
    "TAO":   "bittensor",
    "FET":   "fetch-ai",
    "AGIX":  "singularitynet",
    "OCEAN": "ocean-protocol",
    "RENDER":"render-token",
    "GRT":   "the-graph",
    "IO":    "io-net",
    "NEAR":  "near",
    "ATOM":  "cosmos",
    "JUP":   "jupiter-exchange-solana",
    "PYTH":  "pyth-network",
    "W":     "wormhole",
    "ENA":   "ethena",
    "EIGEN": "eigenlayer",
}


# ──────────────────────────────────────────────────────────────────────────────
# Ana Sınıf
# ──────────────────────────────────────────────────────────────────────────────

class PriceTracker:
    """CoinGecko üzerinden token fiyatlarını çeker ve önbellekler."""

    def __init__(self):
        self._cache: dict[str, TokenPrice] = {}
        self._session = requests.Session()
        self._session.headers.update({
            "User-Agent": "WhaleAlert-Bot/1.0",
            "Accept": "application/json",
        })
        logger.info("PriceTracker baslatildi (CoinGecko)")

    def get_price(self, ticker: str) -> Optional[TokenPrice]:
        """
        Tek bir ticker için fiyat döner.
        Önbellekte varsa ve taze ise önbellekten, yoksa API'den çeker.
        """
        ticker = ticker.upper().lstrip("$")

        # Önbellekten kontrol
        cached = self._cache.get(ticker)
        if cached and not cached.is_stale:
            return cached

        cg_id = TICKER_TO_CG_ID.get(ticker)
        if not cg_id:
            logger.debug(f"CoinGecko ID bilinmiyor: {ticker}")
            return None

        return self._fetch_single(ticker, cg_id)

    def get_prices_bulk(self, tickers: list[str]) -> dict[str, Optional[TokenPrice]]:
        """
        Birden fazla ticker için fiyatları tek API çağrısıyla çeker.
        Döner: {ticker: TokenPrice | None}
        """
        tickers   = [t.upper().lstrip("$") for t in tickers]
        to_fetch  = {}   # cg_id → ticker
        result    = {}

        for ticker in tickers:
            cached = self._cache.get(ticker)
            if cached and not cached.is_stale:
                result[ticker] = cached
                continue
            cg_id = TICKER_TO_CG_ID.get(ticker)
            if cg_id:
                to_fetch[cg_id] = ticker
            else:
                result[ticker] = None

        if to_fetch:
            fetched = self._fetch_bulk(list(to_fetch.keys()))
            for cg_id, price_data in fetched.items():
                ticker = to_fetch[cg_id]
                self._cache[ticker] = price_data
                result[ticker] = price_data

        return result

    def format_price_context(self, ticker: str) -> str:
        """Alert mesajlarına eklenecek fiyat bağlamı metni üretir."""
        price = self.get_price(ticker)
        if not price:
            return f"${ticker}: fiyat verisi yok"
        return price.summary()

    def token_to_usd(self, ticker: str, amount: float) -> float:
        """Token miktarını USD'ye çevirir."""
        price = self.get_price(ticker)
        if price:
            return amount * price.price_usd
        return 0.0

    # ── API Çağrıları ──────────────────────────────────────────────────────────

    def _fetch_single(self, ticker: str, cg_id: str) -> Optional[TokenPrice]:
        try:
            url = f"{COINGECKO_BASE}/simple/price"
            params = {
                "ids":            cg_id,
                "vs_currencies":  "usd",
                "include_market_cap": "true",
                "include_24hr_vol":   "true",
                "include_24hr_change":"true",
            }
            resp = self._session.get(url, params=params, timeout=10)
            resp.raise_for_status()
            data = resp.json().get(cg_id, {})

            if not data:
                return None

            price = TokenPrice(
                ticker         = ticker,
                coingecko_id   = cg_id,
                price_usd      = data.get("usd", 0),
                market_cap_usd = data.get("usd_market_cap", 0),
                volume_24h_usd = data.get("usd_24h_vol", 0),
                change_24h_pct = data.get("usd_24h_change", 0),
            )
            self._cache[ticker] = price
            logger.debug(f"Fiyat guncellendi: {price.summary()}")
            return price

        except Exception as e:
            logger.warning(f"Fiyat cekme hatasi ({ticker}): {e}")
            return None

    def _fetch_bulk(self, cg_ids: list[str]) -> dict[str, TokenPrice]:
        """Tek API çağrısıyla birden fazla token fiyatı çeker."""
        result: dict[str, TokenPrice] = {}
        try:
            url = f"{COINGECKO_BASE}/simple/price"
            params = {
                "ids":            ",".join(cg_ids),
                "vs_currencies":  "usd",
                "include_market_cap": "true",
                "include_24hr_vol":   "true",
                "include_24hr_change":"true",
            }
            resp = self._session.get(url, params=params, timeout=15)
            resp.raise_for_status()
            data = resp.json()

            # Ters harita: cg_id → ticker
            cg_to_ticker = {v: k for k, v in TICKER_TO_CG_ID.items()}

            for cg_id, values in data.items():
                ticker = cg_to_ticker.get(cg_id, cg_id.upper())
                result[cg_id] = TokenPrice(
                    ticker         = ticker,
                    coingecko_id   = cg_id,
                    price_usd      = values.get("usd", 0),
                    market_cap_usd = values.get("usd_market_cap", 0),
                    volume_24h_usd = values.get("usd_24h_vol", 0),
                    change_24h_pct = values.get("usd_24h_change", 0),
                )

        except Exception as e:
            logger.warning(f"Toplu fiyat cekme hatasi: {e}")

        return result

    # ── Trending ────────────────────────────────────────────────────────────────

    def get_trending_tokens(self, limit: int = 10) -> list[dict]:
        """CoinGecko trending token listesini döner."""
        try:
            resp = self._session.get(
                f"{COINGECKO_BASE}/search/trending", timeout=10
            )
            resp.raise_for_status()
            coins = resp.json().get("coins", [])[:limit]
            return [{
                "rank":   i + 1,
                "ticker": c["item"]["symbol"].upper(),
                "name":   c["item"]["name"],
                "sparkline": c["item"].get("data", {}).get("price_change_percentage_24h", {}).get("usd", 0),
            } for i, c in enumerate(coins)]
        except Exception as e:
            logger.warning(f"Trending cekme hatasi: {e}")
            return []


# ──────────────────────────────────────────────────────────────────────────────
# Test
# ──────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    tracker = PriceTracker()

    print("\n=== Tekli Fiyat Testi ===")
    for sym in ["BTC", "ETH", "SOL", "PEPE"]:
        p = tracker.get_price(sym)
        if p:
            print(f"  {p.summary()}")
        else:
            print(f"  {sym}: veri yok")

    print("\n=== Trending Tokenler ===")
    for t in tracker.get_trending_tokens(5):
        print(f"  #{t['rank']} {t['ticker']} — {t['name']}")
