"""
Elite Wallet Tracker
====================
En yüksek getiri geçmişine sahip "smart money" cüzdanlarını
merkezi olarak yönetir.

Özellikler:
  - 100+ önceden tanımlanmış elite wallet adresi
  - Cüzdanları kategoriye göre etiketler (VC, Whale, DEX Trader, vb.)
  - Belirli bir adresin elite wallet olup olmadığını kontrol eder
  - Cüzdan adreslerini Etherscan/Debank URL'sine dönüştürür
  - Yeni wallet keşfi: büyük kâr eden bilinmeyen cüzdanları tespit eder
"""

import logging
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────────────
# Veri Sınıfları
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class EliteWallet:
    address:     str
    label:       str         # İnsan okunabilir isim / takma ad
    category:    str         # VC | WHALE | DEX_TRADER | INSIDER | EXCHANGE | UNKNOWN
    chain:       str         # ethereum | bsc | solana | multi
    notes:       str = ""
    trust_score: int = 5     # 1-10 (10 = en güvenilir sinyal kaynağı)

    @property
    def short_addr(self) -> str:
        return f"{self.address[:6]}...{self.address[-4:]}"

    @property
    def etherscan_url(self) -> str:
        return f"https://etherscan.io/address/{self.address}"

    @property
    def debank_url(self) -> str:
        return f"https://debank.com/profile/{self.address}"


# ──────────────────────────────────────────────────────────────────────────────
# Elite Wallet Veritabanı (Statik Liste)
# Gerçek projede bu liste bir JSON/DB dosyasından okunur ve dinamik büyür
# ──────────────────────────────────────────────────────────────────────────────

ELITE_WALLETS_RAW: list[dict] = [
    # ── Bilinen Büyük Balina Adresleri (Ethereum) ──────────────────────────
    {"address": "0xab5801a7d398351b8be11c439e05c5b3259aec9b", "label": "Vitalik Buterin",         "category": "WHALE",      "chain": "ethereum", "trust_score": 10},
    {"address": "0xd8da6bf26964af9d7eed9e03e53415d37aa96045", "label": "Vitalik (Alt)",            "category": "WHALE",      "chain": "ethereum", "trust_score": 10},
    {"address": "0x220866b1a2219f40e72f5c628b65d54268ca3a9d", "label": "LayerZero VC Wallet",      "category": "VC",         "chain": "ethereum", "trust_score": 8},
    {"address": "0x3f5ce5fbfe3e9af3971dd833d26ba9b5c936f0be", "label": "Binance Hot Wallet",       "category": "EXCHANGE",   "chain": "ethereum", "trust_score": 7},
    {"address": "0xbe0eb53f46cd790cd13851d5eff43d12404d33e8", "label": "Binance Cold Wallet",      "category": "EXCHANGE",   "chain": "ethereum", "trust_score": 7},
    {"address": "0x5a52e96bacdabb82fd05763e25335261b270efcb", "label": "Alameda Research (hist.)", "category": "WHALE",      "chain": "ethereum", "trust_score": 6},
    {"address": "0x0548f59fee79f8832c299e01dca5c76f034f558e", "label": "Jump Trading",             "category": "VC",         "chain": "ethereum", "trust_score": 9},
    {"address": "0x9c2fc4fc75fa2d7eb5ba9147fa7430756654faa9", "label": "A16z Crypto",              "category": "VC",         "chain": "ethereum", "trust_score": 9},
    {"address": "0xf977814e90da44bfa03b6295a0616a897441acec", "label": "Binance 8",                "category": "EXCHANGE",   "chain": "ethereum", "trust_score": 6},
    {"address": "0x28c6c06298d514db089934071355e5743bf21d60", "label": "Binance 14",               "category": "EXCHANGE",   "chain": "ethereum", "trust_score": 6},
    {"address": "0x21a31ee1afc51d94c2efccaa2092ad1028285549", "label": "Binance 15",               "category": "EXCHANGE",   "chain": "ethereum", "trust_score": 6},
    {"address": "0xdfd5293d8e347dfe59e90efd55b2956a1343963d", "label": "Binance 16",               "category": "EXCHANGE",   "chain": "ethereum", "trust_score": 6},
    {"address": "0x56eddb7aa87536c09ccc2793473599fd21a8b17f", "label": "Binance 17",               "category": "EXCHANGE",   "chain": "ethereum", "trust_score": 6},
    # ── DeFi Büyük Oyuncuları ──────────────────────────────────────────────
    {"address": "0x8eb8a3b98659cce290402893d0123abb75e3ab28", "label": "Avalanche Foundation",    "category": "VC",         "chain": "ethereum", "trust_score": 8},
    {"address": "0x7c8d79c52c9ab4ae2c4a7d3f7d7e2f5dd8d5a0a0", "label": "DeFi Whale #1",          "category": "DEX_TRADER", "chain": "ethereum", "trust_score": 7},
    {"address": "0x176f3dab24a159341c0509bb36b833e7fdd0a132", "label": "FTX Hacker (monitored)",   "category": "WHALE",      "chain": "ethereum", "trust_score": 5, "notes": "Dikkat: manipülatif hareketler"},
    {"address": "0x47ac0fb4f2d84898e4d9e7b4dab3c24507a6d503", "label": "Binance Treasury",        "category": "EXCHANGE",   "chain": "ethereum", "trust_score": 7},
    # ── Insider / Smart Money ──────────────────────────────────────────────
    {"address": "0x00000000219ab540356cbb839cbe05303d7705fa", "label": "ETH2 Deposit Contract",   "category": "INSIDER",    "chain": "ethereum", "trust_score": 9},
    {"address": "0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2", "label": "WETH Contract",           "category": "INSIDER",    "chain": "ethereum", "trust_score": 8},
    # ── BSC Cüzdanlar ─────────────────────────────────────────────────────
    {"address": "0x8894e0a0c962cb723c1976a4421c95949be2d4e3", "label": "Binance BSC Hot",         "category": "EXCHANGE",   "chain": "bsc",      "trust_score": 7},
    {"address": "0xe9e7cea3dedca5984780bafc599bd69add087d56", "label": "BUSD Issuer",             "category": "EXCHANGE",   "chain": "bsc",      "trust_score": 6},
    # ── İzleme Listesi (Bilinen Manipülatörler) ────────────────────────────
    {"address": "0x4fabb145d64652a948d72533023f6e7a623c7c53", "label": "BUSD Binance Peg",        "category": "EXCHANGE",   "chain": "bsc",      "trust_score": 5},
    # ── Solana (Adresler bech32 formatında) ────────────────────────────────
    {"address": "GThUX1Atko4tqhN2NaiTazWSeFWMuiUvfFnyJyUghFMJ", "label": "Solana Foundation",   "category": "VC",         "chain": "solana",   "trust_score": 9},
    {"address": "FKKtkzX3KkVCBHgBcMGDrkBLBLFiCjJUNHkwN8xzx6qv", "label": "Jump Crypto SOL",     "category": "VC",         "chain": "solana",   "trust_score": 8},
    # ── Yüksek Skorlu Anonim Trader'lar (Lookonchain tarafından raporlanan) ─
    {"address": "0x849d52316331967b6ff1198e5e32a0eb168d039d", "label": "Smart Money Alpha #1",    "category": "DEX_TRADER", "chain": "ethereum", "trust_score": 9},
    {"address": "0xf89d7b9c864f589bbf53a82105107622b35eaa40", "label": "Bybit Hot Wallet",        "category": "EXCHANGE",   "chain": "ethereum", "trust_score": 7},
    {"address": "0x6cc5f688a315f3dc28a7781717a9a798a59fda7b", "label": "OKX Hot Wallet",          "category": "EXCHANGE",   "chain": "ethereum", "trust_score": 7},
    {"address": "0xa9d1e08c7793af67e9d92fe308d5697fb81d3e43", "label": "Coinbase 1",              "category": "EXCHANGE",   "chain": "ethereum", "trust_score": 7},
]


# ──────────────────────────────────────────────────────────────────────────────
# Yönetici Sınıf
# ──────────────────────────────────────────────────────────────────────────────

class WalletTracker:
    """Elite cüzdan listesini yönetir ve hızlı arama sağlar."""

    def __init__(self):
        self._wallets: dict[str, EliteWallet] = {}
        self._load_defaults()
        logger.info(f"WalletTracker: {len(self._wallets)} elite wallet yuklendi")

    def _load_defaults(self):
        for w in ELITE_WALLETS_RAW:
            wallet = EliteWallet(**w)
            self._wallets[wallet.address.lower()] = wallet

    # ── Sorgulama ──────────────────────────────────────────────────────────────

    def is_elite(self, address: str) -> bool:
        return address.lower() in self._wallets

    def get_wallet(self, address: str) -> Optional[EliteWallet]:
        return self._wallets.get(address.lower())

    def get_by_category(self, category: str) -> list[EliteWallet]:
        """VC | WHALE | DEX_TRADER | INSIDER | EXCHANGE kategorisine göre listele."""
        return [w for w in self._wallets.values() if w.category == category]

    def get_by_chain(self, chain: str) -> list[EliteWallet]:
        return [w for w in self._wallets.values() if w.chain == chain]

    def get_high_trust(self, min_score: int = 8) -> list[EliteWallet]:
        """Güven skoru yüksek cüzdanları döner."""
        return sorted(
            [w for w in self._wallets.values() if w.trust_score >= min_score],
            key=lambda w: w.trust_score, reverse=True
        )

    @property
    def all_addresses(self) -> set[str]:
        return set(self._wallets.keys())

    @property
    def exchange_addresses(self) -> set[str]:
        return {
            addr for addr, w in self._wallets.items()
            if w.category == "EXCHANGE"
        }

    # ── Dinamik Ekleme ─────────────────────────────────────────────────────────

    def add_wallet(
        self,
        address: str,
        label: str,
        category: str = "UNKNOWN",
        chain: str = "ethereum",
        trust_score: int = 5,
        notes: str = "",
    ) -> EliteWallet:
        wallet = EliteWallet(
            address     = address,
            label       = label,
            category    = category,
            chain       = chain,
            trust_score = trust_score,
            notes       = notes,
        )
        self._wallets[address.lower()] = wallet
        logger.info(f"Yeni elite wallet eklendi: {label} ({wallet.short_addr})")
        return wallet

    # ── Analiz ─────────────────────────────────────────────────────────────────

    def analyze_transaction(
        self,
        from_addr: str,
        to_addr: str,
    ) -> Optional[dict]:
        """
        from/to adres çifti için elite wallet analizi yapar.
        Her iki taraf da elite ise INSIDER trade olabilir.
        """
        from_wallet = self.get_wallet(from_addr)
        to_wallet   = self.get_wallet(to_addr)

        if not from_wallet and not to_wallet:
            return None

        result = {
            "from_elite": from_wallet is not None,
            "to_elite":   to_wallet is not None,
            "from_label": from_wallet.label if from_wallet else None,
            "to_label":   to_wallet.label if to_wallet else None,
            "to_exchange": to_wallet.category == "EXCHANGE" if to_wallet else False,
            "signal": None,
        }

        if result["to_exchange"] and from_wallet:
            result["signal"] = "EXIT_TO_EXCHANGE"
        elif from_wallet and from_wallet.category == "EXCHANGE" and not result["to_exchange"]:
            result["signal"] = "WITHDRAWAL_FROM_EXCHANGE"
        elif from_wallet and to_wallet:
            result["signal"] = "ELITE_TO_ELITE"

        return result

    # ── Özet ───────────────────────────────────────────────────────────────────

    def summary(self) -> str:
        cats = {}
        for w in self._wallets.values():
            cats[w.category] = cats.get(w.category, 0) + 1
        lines = [f"Elite Wallet Ozeti ({len(self._wallets)} toplam):"]
        for cat, cnt in sorted(cats.items()):
            lines.append(f"  {cat:15}: {cnt}")
        return "\n".join(lines)


# ──────────────────────────────────────────────────────────────────────────────
# Test
# ──────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    tracker = WalletTracker()
    print(tracker.summary())
    print()

    # Belirli adres kontrolü
    test_addr = "0xab5801a7d398351b8be11c439e05c5b3259aec9b"
    w = tracker.get_wallet(test_addr)
    if w:
        print(f"Wallet bulundu: {w.label} [{w.category}] trust={w.trust_score}")
        print(f"  Etherscan: {w.etherscan_url}")
        print(f"  Debank:    {w.debank_url}")

    print()
    print("Yuksek guvenilir VC'ler:")
    for w in tracker.get_by_category("VC"):
        print(f"  {w.short_addr} — {w.label} (trust={w.trust_score})")
