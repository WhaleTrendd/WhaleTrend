import sys
sys.path.insert(0, 'bot')

from database import Database
from wallet_tracker import WalletTracker
from alert_filter import AlertFilter
from nlp_analyzer import NLPAnalyzer

# ── Database ──────────────────────────────────────────────────────────────────
print("=== DATABASE ===")
db = Database()
stats = db.get_db_stats()
print(f"Tablolar olusturuldu: {stats}")

# ── Wallet Tracker ─────────────────────────────────────────────────────────────
print()
print("=== WALLET TRACKER ===")
wt = WalletTracker()
print(wt.summary())

vitalik = wt.get_wallet("0xab5801a7d398351b8be11c439e05c5b3259aec9b")
if vitalik:
    print(f"Bulunan: {vitalik.label} [{vitalik.category}] trust={vitalik.trust_score}")

# ── Alert Filter ───────────────────────────────────────────────────────────────
print()
print("=== ALERT FILTER ===")
analyzer = NLPAnalyzer()
filt     = AlertFilter()

test_tweets = [
    {
        "id": "t001", "author": "VitalikButerin",
        "text": "Massive $ETH ZK opportunity! Accumulate now. 100x incoming bullish.",
        "url": "https://x.com/t001", "likes": 50000, "retweets": 8000,
    },
    {
        "id": "t002", "author": "elonmusk",
        "text": "I love $DOGE. AI x crypto is massive narrative.",
        "url": "https://x.com/t002", "likes": 200000, "retweets": 40000,
    },
    {
        "id": "t002",   # duplicate
        "author": "elonmusk",
        "text": "duplicate tweet test",
        "url": "https://x.com/t002", "likes": 200000, "retweets": 40000,
    },
    {
        "id": "t003", "author": "randomuser",
        "text": "maybe btc goes up who knows",
        "url": "https://x.com/t003", "likes": 5, "retweets": 0,
    },
]

for tw in test_tweets:
    r = analyzer.analyze(tw)
    d = filt.should_alert(r, tw)
    status = "IZIN" if d.allowed else "RED"
    print(f"  [{status:4}] @{tw['author']:20} score={d.priority_score:5} | {d.reason}")

print(f"\n  Filtre Istatistikleri: {filt.get_stats()}")

# ── Report Generator ───────────────────────────────────────────────────────────
print()
print("=== REPORT GENERATOR ===")
from report_generator import ReportGenerator
gen = ReportGenerator(db)
print(gen.daily_summary()[:400])
print("  [...rapor devam ediyor...]")

print()
print("=== TUM MODULLER BASARIYLA YUKLENDI ===")
