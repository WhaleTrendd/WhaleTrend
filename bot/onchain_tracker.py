"""
On-Chain Whale Tracker
======================
Tespit edilen bir ticker/token için elite whale cüzdanlarının
son büyük işlemlerini Etherscan ve BscScan API'larından çeker.

Senaryo A (EXIT WARNING):     Whale → Borsa deposit adresi
Senaryo B (INSIDER ACC.):     Bilinmeyen cüzdan → Token contract (büyük alım)
"""

import logging
import time
import requests
from dataclasses import dataclass, field
from typing import Optional

from config import (
    ETHERSCAN_API_KEY,
    BSCSCAN_API_KEY,
    ENABLED_CHAINS,
    WHALE_THRESHOLD_USD,
    EXCHANGE_ADDRESSES,
)

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────────────
# Veri Sınıfları
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class WhaleTransaction:
    tx_hash:         str
    chain:           str          # "ethereum" | "bsc"
    token_symbol:    str
    token_address:   str
    from_address:    str
    to_address:      str
    value_usd:       float
    tx_type:         str          # "DEPOSIT_TO_EXCHANGE" | "ACCUMULATION" | "TRANSFER"
    exchange_name:   Optional[str] = None
    block_number:    int = 0
    timestamp:       str = ""

    @property
    def is_exit_signal(self) -> bool:
        return self.tx_type == "DEPOSIT_TO_EXCHANGE"

    @property
    def is_accumulation(self) -> bool:
        return self.tx_type == "ACCUMULATION"


@dataclass
class WhaleAnalysis:
    ticker:          str
    chain:           str
    total_scanned:   int = 0
    exit_signals:    list[WhaleTransaction] = field(default_factory=list)
    accumulations:   list[WhaleTransaction] = field(default_factory=list)
    transfers:       list[WhaleTransaction] = field(default_factory=list)

    @property
    def verdict(self) -> str:
        """Genel yargı: EXIT_WARNING | INSIDER_ACCUMULATION | NEUTRAL"""
        if len(self.exit_signals) >= 2:
            return "EXIT_WARNING"
        if len(self.accumulations) >= 2:
            return "INSIDER_ACCUMULATION"
        if self.exit_signals:
            return "EXIT_WARNING"
        if self.accumulations:
            return "INSIDER_ACCUMULATION"
        return "NEUTRAL"

    @property
    def total_exit_usd(self) -> float:
        return sum(t.value_usd for t in self.exit_signals)

    @property
    def total_accum_usd(self) -> float:
        return sum(t.value_usd for t in self.accumulations)


# ──────────────────────────────────────────────────────────────────────────────
# Zincir Konfigürasyonları
# ──────────────────────────────────────────────────────────────────────────────

_CHAIN_CONFIG = {
    "ethereum": {
        "api_url":    "https://api.etherscan.io/api",
        "api_key":    ETHERSCAN_API_KEY,
        "explorer":   "https://etherscan.io/tx/",
        # Temel token adresleri (yaygın olanlar - tam liste için on-chain lookup gerekir)
        "known_tokens": {
            "ETH":   "0xEeeeeEeeeEeEeeEeEeEeeEEEeeeeEeeeeeeeEEeE",
            "USDT":  "0xdac17f958d2ee523a2206206994597c13d831ec7",
            "USDC":  "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48",
            "DAI":   "0x6b175474e89094c44da98b954eedeac495271d0f",
            "LINK":  "0x514910771af9ca656af840dff83e8264ecf986ca",
            "UNI":   "0x1f9840a85d5af5bf1d1762f925bdaddc4201f984",
            "AAVE":  "0x7fc66500c84a76ad7e9c93437bfc5ac33e2ddae9",
            "MKR":   "0x9f8f72aa9304c8b593d555f12ef6589cc3a579a2",
            "COMP":  "0xc00e94cb662c3520282e6f5717214004a7f26888",
            "SNX":   "0xc011a73ee8576fb46f5e1c5751ca3b9fe0af2a6f",
        },
    },
    "bsc": {
        "api_url":    "https://api.bscscan.com/api",
        "api_key":    BSCSCAN_API_KEY,
        "explorer":   "https://bscscan.com/tx/",
        "known_tokens": {
            "BNB":   "0xEeeeeEeeeEeEeeEeEeEeeEEEeeeeEeeeeeeeEEeE",
            "CAKE":  "0x0e09fabb73bd3ade0a17ecc321fd13a19e81ce82",
            "BUSD":  "0xe9e7cea3dedca5984780bafc599bd69add087d56",
            "USDT":  "0x55d398326f99059ff775485246999027b3197955",
        },
    },
}

# Yaklaşık token fiyatları (USD) – gerçek üretimde CoinGecko/CMC API kullanılır
_APPROX_PRICES_USD = {
    "ETH": 2500, "BTC": 65000, "BNB": 580, "SOL": 140,
    "USDT": 1, "USDC": 1, "DAI": 1,
    "LINK": 13, "UNI": 7, "AAVE": 90, "MKR": 2000,
    "DOGE": 0.15, "PEPE": 0.000012, "SHIB": 0.000023,
}

# Borsa adres haritası (ters arama: adres → borsa adı)
_EXCHANGE_ADDR_MAP: dict[str, str] = {}
for _name, _addrs in EXCHANGE_ADDRESSES.items():
    for _addr in _addrs:
        _EXCHANGE_ADDR_MAP[_addr.lower()] = _name


# ──────────────────────────────────────────────────────────────────────────────
# Ana Sınıf
# ──────────────────────────────────────────────────────────────────────────────

class OnChainTracker:
    """
    Bir ticker için Ethereum ve BSC üzerindeki büyük whale hareketlerini
    tarar, EXIT WARNING veya INSIDER ACCUMULATION sinyali üretir.
    """

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "WhaleAlert-Bot/1.0"})
        logger.info(f"OnChainTracker başlatıldı → zincirler: {ENABLED_CHAINS}")

    # ── Public API ─────────────────────────────────────────────────────────────

    def analyze_ticker(
        self,
        ticker: str,
        min_usd: float = None,
        lookback_blocks: int = 500,   # ≈son 1-2 saat (ETH ~12s/block)
    ) -> WhaleAnalysis:
        """
        Bir ticker için tüm etkin zincirlerde whale analizi yapar.
        """
        min_usd = min_usd or WHALE_THRESHOLD_USD
        ticker  = ticker.upper().lstrip("$")

        analysis = WhaleAnalysis(ticker=ticker, chain="multi")

        for chain in ENABLED_CHAINS:
            cfg = _CHAIN_CONFIG.get(chain)
            if not cfg:
                continue
            if not cfg["api_key"]:
                logger.warning(f"{chain} API anahtarı eksik, atlanıyor.")
                continue

            token_address = cfg["known_tokens"].get(ticker)
            if not token_address:
                # Bilinmeyen token → by-name arama (basit fallback)
                logger.debug(f"{ticker} {chain} üzerinde tanınmıyor, atlanıyor.")
                continue

            txs = self._fetch_large_transfers(
                chain, token_address, ticker, min_usd, lookback_blocks
            )
            analysis.total_scanned += len(txs)

            for tx in txs:
                if tx.is_exit_signal:
                    analysis.exit_signals.append(tx)
                elif tx.is_accumulation:
                    analysis.accumulations.append(tx)
                else:
                    analysis.transfers.append(tx)

            time.sleep(0.3)   # API rate-limit

        logger.info(
            f"{ticker}: {analysis.total_scanned} tx tarandı → "
            f"verdict={analysis.verdict} | "
            f"exit_usd=${analysis.total_exit_usd:,.0f} | "
            f"accum_usd=${analysis.total_accum_usd:,.0f}"
        )
        return analysis

    # ── Veri Çekme ─────────────────────────────────────────────────────────────

    def _fetch_large_transfers(
        self,
        chain: str,
        token_address: str,
        ticker: str,
        min_usd: float,
        lookback_blocks: int,
    ) -> list[WhaleTransaction]:
        """
        Etherscan/BscScan tokentx endpointini kullanarak büyük transfer işlemlerini çeker.
        """
        cfg     = _CHAIN_CONFIG[chain]
        api_url = cfg["api_url"]
        api_key = cfg["api_key"]
        explorer = cfg["explorer"]

        # Native coin (ETH/BNB) ise farklı endpoint
        is_native = token_address.lower().startswith("0xeeee")

        params = {
            "module":    "account",
            "action":    "txlist" if is_native else "tokentx",
            "apikey":    api_key,
            "sort":      "desc",
            "page":      1,
            "offset":    200,
        }
        if not is_native:
            params["contractaddress"] = token_address

        try:
            resp = self.session.get(api_url, params=params, timeout=20)
            resp.raise_for_status()
            data = resp.json()

            if data.get("status") != "1":
                msg = data.get("message", "")
                logger.warning(f"{chain}/{ticker} API yanıtı: {msg}")
                return []

            raw_txs = data.get("result", [])
        except Exception as e:
            logger.error(f"{chain}/{ticker} API hatası: {e}")
            return []

        results = []
        price = _APPROX_PRICES_USD.get(ticker, 0)

        for tx in raw_txs:
            try:
                value_raw = float(tx.get("value", 0))
                decimals  = int(tx.get("tokenDecimal") or 18)
                value_tok = value_raw / (10 ** decimals)
                value_usd = value_tok * price if price else 0

                # Eşiğin altındaki işlemleri geç
                if value_usd < min_usd:
                    continue

                from_addr = tx.get("from", "").lower()
                to_addr   = tx.get("to", "").lower()
                tx_hash   = tx.get("hash", "")
                block     = int(tx.get("blockNumber", 0))

                # İşlem tipi belirleme
                exchange_match = _EXCHANGE_ADDR_MAP.get(to_addr)
                if exchange_match:
                    tx_type = "DEPOSIT_TO_EXCHANGE"
                elif _EXCHANGE_ADDR_MAP.get(from_addr):
                    tx_type = "ACCUMULATION"   # borsadan çekim → birikim sinyali
                else:
                    tx_type = "TRANSFER"

                results.append(WhaleTransaction(
                    tx_hash       = tx_hash,
                    chain         = chain,
                    token_symbol  = ticker,
                    token_address = token_address,
                    from_address  = from_addr,
                    to_address    = to_addr,
                    value_usd     = round(value_usd, 2),
                    tx_type       = tx_type,
                    exchange_name = exchange_match,
                    block_number  = block,
                    timestamp     = tx.get("timeStamp", ""),
                ))
            except Exception as e:
                logger.debug(f"TX parse hatası: {e}")
                continue

        return results

    # ── Özet ───────────────────────────────────────────────────────────────────

    @staticmethod
    def format_analysis_summary(analysis: WhaleAnalysis) -> str:
        """İnsan okunabilir metin özeti üretir (Telegram mesajı için)."""
        lines = [f"🔍 On-Chain Analiz: ${analysis.ticker}"]
        lines.append(f"Taranan TX: {analysis.total_scanned}")

        if analysis.exit_signals:
            total = analysis.total_exit_usd
            lines.append(f"🔴 Borsa Deposit: {len(analysis.exit_signals)} işlem (${total:,.0f})")
            for tx in analysis.exit_signals[:3]:
                lines.append(
                    f"  └ {tx.exchange_name}: ${tx.value_usd:,.0f} "
                    f"[{tx.chain}] {tx.tx_hash[:10]}..."
                )

        if analysis.accumulations:
            total = analysis.total_accum_usd
            lines.append(f"🟢 Birikim: {len(analysis.accumulations)} işlem (${total:,.0f})")
            for tx in analysis.accumulations[:3]:
                lines.append(
                    f"  └ ${tx.value_usd:,.0f} [{tx.chain}] {tx.tx_hash[:10]}..."
                )

        if analysis.verdict == "NEUTRAL" and analysis.total_scanned == 0:
            lines.append("ℹ️ Bu token için on-chain veri bulunamadı")

        return "\n".join(lines)
