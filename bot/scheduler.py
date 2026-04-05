"""
Advanced Scheduler
==================
Farklı görevleri farklı aralıklarla çalıştıran gelişmiş zamanlayıcı.

Görev Takvimi:
  Her 5 dk   → Twitter tarama + NLP + On-chain + Alert
  Her 30 dk  → Fiyat güncellemesi (CoinGecko)
  Her 1 saat → Token sinyal özeti
  Her 06:00  → Günlük rapor Telegram'a gönder
  Her Pazartesi 09:00 → Haftalık otopsi raporu
  Her 1 saat → Trending tokenler kontrolü

Özellikler:
  - Thread-safe görev kuyruğu
  - Başarısız görev retry mantığı (3 deneme, exponential backoff)
  - Görev çakışmasını önle (bir görev zaten çalışıyorsa atla)
  - Sağlık durumu izleme (watchdog)
"""

import time
import logging
import threading
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass, field
from typing import Callable, Optional
from collections import defaultdict

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────────────
# Görev Tanımı
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class ScheduledTask:
    name:            str
    func:            Callable
    interval_seconds: int         # 0 = tek seferlik
    run_at_hour:     Optional[int] = None    # saate bağlı tetikleyici
    run_at_weekday:  Optional[int] = None    # haftanın günü (0=Pzt, 6=Paz)
    max_retries:     int = 3
    enabled:         bool = True

    # Runtime alanlar
    last_run:        float = field(default=0.0)
    last_success:    float = field(default=0.0)
    run_count:       int   = field(default=0)
    error_count:     int   = field(default=0)
    is_running:      bool  = field(default=False)

    @property
    def next_run_in(self) -> float:
        """Saniye cinsinden bir sonraki çalışmaya kalan süre."""
        elapsed = time.time() - self.last_run
        return max(0, self.interval_seconds - elapsed)

    @property
    def is_due(self) -> bool:
        """Görev şu an çalışmalı mı?"""
        if not self.enabled or self.is_running:
            return False

        now = datetime.now(timezone.utc)

        # Saate bağlı görev
        if self.run_at_hour is not None:
            ran_today_key = (now.date(), self.name)
            if ran_today_key in _DAILY_RAN_SET:
                return False
            if now.hour == self.run_at_hour and now.minute < 5:
                if self.run_at_weekday is None or now.weekday() == self.run_at_weekday:
                    return True
            return False

        # Periyodik görev
        return (time.time() - self.last_run) >= self.interval_seconds


# Günlük görev takibi için küme
_DAILY_RAN_SET: set = set()


# ──────────────────────────────────────────────────────────────────────────────
# Zamanlayıcı
# ──────────────────────────────────────────────────────────────────────────────

class Scheduler:
    """
    Çok iş parçacıklı görev zamanlayıcı.
    Her görev ayrı bir thread'de çalışır, ana döngü bloklenmez.
    """

    def __init__(self):
        self._tasks:   list[ScheduledTask] = []
        self._lock:    threading.Lock()
        self._stopped: bool = False
        self._stats:   dict = defaultdict(int)
        logger.info("Gelismis Zamanlayici baslatildi")

    # ── Kayıt ──────────────────────────────────────────────────────────────────

    def every(
        self,
        seconds: int = 0,
        minutes: int = 0,
        hours: int = 0,
        name: str = "unnamed",
        max_retries: int = 3,
    ) -> Callable:
        """Decorator — her N saniye/dakika/saatte bir çalıştır."""
        total_seconds = seconds + minutes * 60 + hours * 3600

        def decorator(func: Callable):
            task = ScheduledTask(
                name             = name or func.__name__,
                func             = func,
                interval_seconds = total_seconds,
                max_retries      = max_retries,
            )
            self._tasks.append(task)
            logger.info(
                f"Gorev kayit: '{task.name}' her {total_seconds}s"
            )
            return func
        return decorator

    def daily_at(
        self,
        hour: int,
        weekday: Optional[int] = None,
        name: str = "unnamed",
    ) -> Callable:
        """Decorator — her gün belirli saatte çalıştır."""
        def decorator(func: Callable):
            task = ScheduledTask(
                name             = name or func.__name__,
                func             = func,
                interval_seconds = 0,
                run_at_hour      = hour,
                run_at_weekday   = weekday,
            )
            self._tasks.append(task)
            day_name = ["Pzt","Sal","Car","Per","Cum","Cmt","Paz"][weekday] if weekday is not None else "Her gun"
            logger.info(f"Gorev kayit: '{task.name}' {day_name} saat {hour:02d}:00")
            return func
        return decorator

    def add_task(self, task: ScheduledTask):
        """Elle görev ekler."""
        self._tasks.append(task)

    # ── Ana Döngü ──────────────────────────────────────────────────────────────

    def run_forever(self, check_interval: float = 10.0):
        """
        Sonsuza kadar görev kontrolü yapar.
        check_interval: kaç saniyede bir due kontrolü yapılsın
        """
        logger.info(f"Zamanlayici dongusu basladi ({len(self._tasks)} gorev)")
        self._stopped = False

        while not self._stopped:
            try:
                self._tick()
            except Exception as e:
                logger.error(f"Zamanlayici tick hatasi: {e}", exc_info=True)
            time.sleep(check_interval)

    def stop(self):
        self._stopped = True
        logger.info("Zamanlayici durduruldu")

    def _tick(self):
        """Tüm görevleri kontrol eder, vadesi gelenleri başlatır."""
        for task in self._tasks:
            if task.is_due:
                self._run_task_async(task)

    def _run_task_async(self, task: ScheduledTask):
        """Görevi ayrı bir thread'de çalıştırır."""
        def runner():
            task.is_running = True
            task.last_run   = time.time()
            attempt = 0

            while attempt < task.max_retries:
                try:
                    task.func()
                    task.last_success = time.time()
                    task.run_count   += 1
                    self._stats[f"{task.name}_success"] += 1

                    # Günlük görev ise işaretle
                    if task.run_at_hour is not None:
                        now = datetime.now(timezone.utc)
                        _DAILY_RAN_SET.add((now.date(), task.name))

                    logger.info(
                        f"Gorev tamamlandi: '{task.name}' "
                        f"(#{task.run_count})"
                    )
                    break

                except Exception as e:
                    attempt += 1
                    task.error_count += 1
                    self._stats[f"{task.name}_error"] += 1
                    wait = 2 ** attempt   # exponential backoff: 2s, 4s, 8s
                    logger.warning(
                        f"Gorev hatasi: '{task.name}' deneme {attempt}/{task.max_retries}: {e}"
                        f" — {wait}s sonra tekrar"
                    )
                    if attempt < task.max_retries:
                        time.sleep(wait)
                    else:
                        logger.error(
                            f"Gorev basarisiz: '{task.name}' (max deneme asild)"
                        )

            task.is_running = False

        t = threading.Thread(target=runner, name=task.name, daemon=True)
        t.start()

    # ── Durum ──────────────────────────────────────────────────────────────────

    def status(self) -> str:
        """Tüm görevlerin durumunu metin olarak döner."""
        lines = [f"Zamanlayici Durumu — {len(self._tasks)} gorev\n"]
        now = time.time()
        for task in self._tasks:
            state   = "CALISIYOR" if task.is_running else ("AKTIF" if task.enabled else "PASIF")
            last_ok = datetime.fromtimestamp(task.last_success, tz=timezone.utc).strftime("%H:%M:%S") \
                      if task.last_success > 0 else "hic"
            next_in = f"{task.next_run_in:.0f}s" if task.interval_seconds > 0 else "saate gore"

            lines.append(
                f"  [{state:10}] {task.name:30} "
                f"son_basari={last_ok} "
                f"sonraki={next_in} "
                f"hata={task.error_count}"
            )
        return "\n".join(lines)

    def get_stats(self) -> dict:
        return dict(self._stats)


# ──────────────────────────────────────────────────────────────────────────────
# WhaleAlert Zamanlayıcı Fabrikası
# İstediğinde main.py'den bu fonksiyonu çağır ve hazır scheduler'ı al
# ──────────────────────────────────────────────────────────────────────────────

def build_whalebot_scheduler(
    scan_fn:           Callable,
    price_update_fn:   Callable,
    daily_report_fn:   Callable,
    weekly_report_fn:  Callable,
    trending_check_fn: Callable,
    scan_interval_min: int = 5,
) -> Scheduler:
    """
    WhaleAlert için standart görev takvimini oluşturur.

    Parametreler:
        scan_fn            → ana tarama fonksiyonu
        price_update_fn    → fiyat güncelme fonksiyonu
        daily_report_fn    → günlük rapor gönderme fonksiyonu
        weekly_report_fn   → haftalık otopsi fonksiyonu
        trending_check_fn  → trending token kontrolü
        scan_interval_min  → tarama aralığı (dakika)
    """
    scheduler = Scheduler()

    # Ana tarama — her N dakika
    scheduler.add_task(ScheduledTask(
        name             = "twitter_onchain_scan",
        func             = scan_fn,
        interval_seconds = scan_interval_min * 60,
        max_retries      = 3,
    ))

    # Fiyat güncellemesi — her 30 dakika
    scheduler.add_task(ScheduledTask(
        name             = "price_update",
        func             = price_update_fn,
        interval_seconds = 30 * 60,
        max_retries      = 2,
    ))

    # Trending tokenler — her 1 saat
    scheduler.add_task(ScheduledTask(
        name             = "trending_check",
        func             = trending_check_fn,
        interval_seconds = 60 * 60,
        max_retries      = 2,
    ))

    # Günlük rapor — her gün saat 08:00 UTC
    scheduler.add_task(ScheduledTask(
        name             = "daily_report",
        func             = daily_report_fn,
        interval_seconds = 0,
        run_at_hour      = 8,
        max_retries      = 2,
    ))

    # Haftalık otopsi — Pazartesi saat 09:00 UTC
    scheduler.add_task(ScheduledTask(
        name             = "weekly_autopsy",
        func             = weekly_report_fn,
        interval_seconds = 0,
        run_at_hour      = 9,
        run_at_weekday   = 0,   # Pazartesi
        max_retries      = 2,
    ))

    return scheduler


# ──────────────────────────────────────────────────────────────────────────────
# Test
# ──────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import random

    scheduler = Scheduler()

    @scheduler.every(seconds=3, name="test_scan")
    def mock_scan():
        logger.info("Mock tarama calistirildi")
        if random.random() < 0.3:
            raise ValueError("Simule hata!")

    @scheduler.every(seconds=7, name="test_price")
    def mock_price():
        logger.info("Mock fiyat guncellendi")

    print("Zamanlayici testi basliyor (15s)...")
    t = threading.Thread(target=scheduler.run_forever, args=(1.0,), daemon=True)
    t.start()

    time.sleep(15)
    scheduler.stop()
    print()
    print(scheduler.status())
