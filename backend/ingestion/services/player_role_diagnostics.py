"""Small, dependency-free helpers for persisted role-run diagnostics."""

from __future__ import annotations

import resource
import sys
from time import monotonic


def resident_memory_mb() -> float:
    value = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    divisor = 1024 * 1024 if sys.platform == "darwin" else 1024
    return round(value / divisor, 2)


def sample_memory(diagnostics: dict | None, stage: str) -> None:
    if diagnostics is None:
        return
    samples = diagnostics.setdefault("rss_samples_mb", {})
    samples[stage] = resident_memory_mb()
    diagnostics["peak_rss_mb"] = max(samples.values())


def record_stage(diagnostics: dict | None, stage: str, started_at: float) -> None:
    if diagnostics is None:
        return
    diagnostics.setdefault("stage_timings_seconds", {})[stage] = round(
        monotonic() - started_at,
        3,
    )
    sample_memory(diagnostics, stage)


def add_rows(diagnostics: dict | None, **counts: int) -> None:
    if diagnostics is None:
        return
    rows = diagnostics.setdefault("rows_processed", {})
    for label, count in counts.items():
        rows[label] = int(rows.get(label, 0)) + int(count)
