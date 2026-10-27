"""
perf_logger.py — Performance Logger untuk Analisis Beban Server

Mencatat metrik performa live stream ke file CSV setiap N detik.
Digunakan untuk kepentingan riset/analisis dalam skripsi.

Format file: logs/stream_perf_YYYYMMDD_HHMMSS.csv
Kolom: timestamp, source_url, fps_actual, inference_ms, preprocess_ms,
        cpu_percent, ram_mb, gpu_percent, gpu_mem_mb, frames_processed,
        detections_count, status

Cara pakai:
    logger = PerfLogger()
    logger.start(stream_url="rtsp://...")
    # otomatis log setiap interval_seconds
    logger.stop()
    path = logger.get_log_path()  # untuk download endpoint
"""

import os
import csv
import time
import threading
from datetime import datetime
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent
LOGS_DIR = BASE_DIR / "logs"
LOGS_DIR.mkdir(exist_ok=True)


class PerfLogger:
    """
    Logger performa stream yang menulis metrik ke CSV secara periodik.

    Thread-safe: bisa di-call dari thread manapun.
    """

    DEFAULT_INTERVAL = 1.0  # Detik antar pencatatan

    def __init__(self, interval_seconds: float = DEFAULT_INTERVAL):
        self.interval = interval_seconds
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._log_path: Path | None = None
        self._metrics_fn = None   # callable() → dict

    # ------------------------------------------------------------------
    # PUBLIC API
    # ------------------------------------------------------------------

    def start(self, metrics_fn) -> Path:
        """
        Mulai logging performa.

        Args:
            metrics_fn: callable tanpa argumen yang mengembalikan dict metrik
                        (biasanya stream_manager.get_metrics())

        Returns:
            Path ke file CSV yang sedang ditulis
        """
        if self._thread and self._thread.is_alive():
            self.stop()

        self._metrics_fn = metrics_fn
        self._stop_event.clear()

        timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
        self._log_path = LOGS_DIR / f"stream_perf_{timestamp_str}.csv"

        # Buat file dan tulis header
        with open(self._log_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=self._csv_fields())
            writer.writeheader()

        self._thread = threading.Thread(
            target=self._run, daemon=True, name="PerfLogger"
        )
        self._thread.start()
        print(f"[PerfLogger] Logging dimulai → {self._log_path}")
        return self._log_path

    def stop(self) -> None:
        """Hentikan logging."""
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5)
        print(f"[PerfLogger] Logging dihentikan. File: {self._log_path}")

    def get_log_path(self) -> Path | None:
        """Return path file CSV aktif (None jika belum dimulai)."""
        return self._log_path

    def list_logs(self) -> list[dict]:
        """
        Return list semua file log CSV yang tersedia.

        Returns:
            list of dict: [{filename, path, size_kb, created_at}]
        """
        result = []
        for f in sorted(LOGS_DIR.glob("stream_perf_*.csv"), reverse=True):
            stat = f.stat()
            result.append({
                "filename": f.name,
                "path": str(f),
                "size_kb": round(stat.st_size / 1024, 1),
                "created_at": datetime.fromtimestamp(stat.st_ctime).isoformat(),
            })
        return result

    # ------------------------------------------------------------------
    # PRIVATE
    # ------------------------------------------------------------------

    def _csv_fields(self) -> list[str]:
        return [
            "timestamp",
            "source_url",
            "status",
            "fps_actual",
            "inference_ms",
            "preprocess_ms",
            "cpu_percent",
            "ram_mb",
            "gpu_percent",
            "gpu_mem_mb",
            "frames_processed",
            "detections_count",
            "uptime_seconds",
        ]

    def _run(self) -> None:
        while not self._stop_event.is_set():
            self._stop_event.wait(timeout=self.interval)
            if self._stop_event.is_set():
                break
            try:
                self._write_row()
            except Exception as e:
                print(f"[PerfLogger] Error saat menulis log: {e}")

    def _write_row(self) -> None:
        if self._metrics_fn is None or self._log_path is None:
            return

        metrics = self._metrics_fn()

        row = {
            "timestamp":       datetime.now().isoformat(timespec="seconds"),
            "source_url":      metrics.get("source_url", ""),
            "status":          metrics.get("status", ""),
            "fps_actual":      metrics.get("fps_actual", 0.0),
            "inference_ms":    metrics.get("inference_ms", 0.0),
            "preprocess_ms":   metrics.get("preprocess_ms", 0.0),
            "cpu_percent":     metrics.get("cpu_percent", 0.0),
            "ram_mb":          metrics.get("ram_mb", 0.0),
            "gpu_percent":     metrics.get("gpu_percent", 0.0),
            "gpu_mem_mb":      metrics.get("gpu_mem_mb", 0.0),
            "frames_processed": metrics.get("frame_number", 0),
            "detections_count": metrics.get("detections_count", 0),
            "uptime_seconds":  metrics.get("uptime_seconds", 0),
        }

        with open(self._log_path, "a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=self._csv_fields())
            writer.writerow(row)
