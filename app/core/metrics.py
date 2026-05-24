from __future__ import annotations

import statistics
import threading
import time
from contextlib import contextmanager
from typing import Iterator


class MetricsRegistry:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._counters: dict[str, float] = {}
        self._timings: dict[str, list[float]] = {}
        self._gauges: dict[str, float] = {}

    def increment(self, name: str, value: float = 1.0) -> None:
        with self._lock:
            self._counters[name] = self._counters.get(name, 0.0) + value

    def gauge(self, name: str, value: float) -> None:
        with self._lock:
            self._gauges[name] = value

    def observe(self, name: str, value: float) -> None:
        with self._lock:
            bucket = self._timings.setdefault(name, [])
            bucket.append(value)
            if len(bucket) > 5000:
                del bucket[:1000]

    @contextmanager
    def timer(self, name: str) -> Iterator[None]:
        start = time.perf_counter()
        try:
            yield
        finally:
            self.observe(name, time.perf_counter() - start)

    def snapshot(self) -> dict:
        with self._lock:
            timings = {}
            for name, values in self._timings.items():
                if not values:
                    continue
                timings[name] = {
                    "count": len(values),
                    "avg": statistics.fmean(values),
                    "p50": statistics.median(values),
                    "p95": _percentile(values, 95),
                    "max": max(values),
                }
            payload = {
                "counters": dict(self._counters),
                "gauges": dict(self._gauges),
                "timings": timings,
            }
        payload["system"] = _system_snapshot()
        return payload

    def prometheus(self) -> str:
        snap = self.snapshot()
        lines = []
        for name, value in snap["counters"].items():
            lines.append(f"prc_{name}_total {value}")
        for name, value in snap["gauges"].items():
            lines.append(f"prc_{name} {value}")
        for name, stats in snap["timings"].items():
            safe = name.replace(".", "_")
            lines.append(f"prc_{safe}_seconds_count {stats['count']}")
            lines.append(f"prc_{safe}_seconds_avg {stats['avg']}")
            lines.append(f"prc_{safe}_seconds_p95 {stats['p95']}")
        for name, value in snap["system"].items():
            lines.append(f"prc_system_{name} {value}")
        return "\n".join(lines) + "\n"


def _percentile(values: list[float], percentile: int) -> float:
    ordered = sorted(values)
    if not ordered:
        return 0.0
    index = min(len(ordered) - 1, round((percentile / 100) * (len(ordered) - 1)))
    return ordered[index]


def _system_snapshot() -> dict[str, float]:
    try:
        import psutil

        process = psutil.Process()
        memory = process.memory_info()
        return {
            "rss_bytes": float(memory.rss),
            "cpu_percent": float(process.cpu_percent(interval=None)),
            "system_memory_percent": float(psutil.virtual_memory().percent),
        }
    except Exception:
        return {}


metrics = MetricsRegistry()

