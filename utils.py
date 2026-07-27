"""
utils.py
--------
General-purpose helper functions shared across modules.

Home to: the synthetic timestamp generator, CPU-core detection, uploaded
file validation, and a fast file hash used as a session-state cache key
(so Streamlit reruns don't re-trigger a full parallel analysis unless the
file or worker count actually changed).
"""

import hashlib
import os
import random
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from config import (
    ALLOWED_EXTENSIONS,
    MAX_FILE_SIZE_MB,
    SYNTHETIC_TIME_ENABLED,
    SYNTHETIC_TIME_SPAN_DAYS,
    SYNTHETIC_HOURLY_WEIGHTS,
)


def get_cpu_core_count() -> int:
    """Return the number of logical CPU cores available on this machine."""
    return os.cpu_count() or 1


def validate_log_file(filepath: str) -> tuple[bool, str]:
    """
    Validate an uploaded log file before processing.

    Checks extension, existence, non-empty content, and a hard size cap.
    Never raises -- always returns a (is_valid, message) pair so the caller
    (app.py) can show a clean error instead of a stack trace.

    Args:
        filepath: Path to the uploaded file on disk.

    Returns:
        (True, "") if valid, otherwise (False, human_readable_reason).
    """
    path = Path(filepath)

    if not path.exists():
        return False, "File not found."

    if path.suffix.lower() not in ALLOWED_EXTENSIONS:
        allowed = ", ".join(sorted(ALLOWED_EXTENSIONS))
        return False, f"Unsupported file type '{path.suffix}'. Allowed: {allowed}."

    size_mb = path.stat().st_size / (1024 * 1024)
    if size_mb == 0:
        return False, "The uploaded file is empty."
    if size_mb > MAX_FILE_SIZE_MB:
        return False, f"File is {size_mb:.1f} MB, which exceeds the {MAX_FILE_SIZE_MB} MB limit."

    return True, ""


def compute_file_hash(filepath: str, sample_bytes: int = 4 * 1024 * 1024) -> str:
    """
    Compute a fast, stable identifier for a file to use as a cache key.

    Hashing the full file would be slow for very large logs, so this hashes
    the file size plus a sample from the start and end of the file. This is
    sufficient to detect "the user uploaded a different file" without paying
    the cost of a full-file hash on a multi-hundred-MB log.

    Args:
        filepath: Path to the file on disk.
        sample_bytes: How many bytes to sample from the start and end.

    Returns:
        A hex digest string suitable for use as part of a session-state key.
    """
    path = Path(filepath)
    size = path.stat().st_size
    hasher = hashlib.md5()
    hasher.update(str(size).encode())

    with open(filepath, "rb") as f:
        hasher.update(f.read(sample_bytes))
        if size > sample_bytes:
            f.seek(max(size - sample_bytes, 0))
            hasher.update(f.read(sample_bytes))

    return hasher.hexdigest()


def synthesize_timestamp(line_number: int, real_timestamp: Optional[datetime]) -> datetime:
    """
    Deterministically generate a realistic-looking timestamp for a log row.

    The source dataset has an identical timestamp on every row, which makes
    time-based analysis meaningless. This function spreads rows across a
    configurable window (default 7 days) with realistic hour-of-day
    weighting, seeded by the row's line number so the result is:
      - Reproducible across runs
      - Identical regardless of how many workers process the file (each
        worker only needs the line number, not any shared state)

    Args:
        line_number: 1-indexed position of the row in the source file.
        real_timestamp: The original (constant) timestamp from the log, used
            as the anchor date if parsing succeeded; falls back to "now" if
            the real timestamp couldn't be parsed.

    Returns:
        A synthetic datetime for use in all time-based statistics/charts.
    """
    if not SYNTHETIC_TIME_ENABLED:
        return real_timestamp or datetime.now()

    anchor = real_timestamp or datetime.now()
    rng = random.Random(line_number)  # seeded per-row -> deterministic, chunk-independent

    day_offset = rng.randint(0, SYNTHETIC_TIME_SPAN_DAYS - 1)
    hour = rng.choices(range(24), weights=SYNTHETIC_HOURLY_WEIGHTS, k=1)[0]
    minute = rng.randint(0, 59)
    second = rng.randint(0, 59)

    base_date = anchor.replace(hour=0, minute=0, second=0, microsecond=0)
    return base_date + timedelta(days=day_offset, hours=hour, minutes=minute, seconds=second)
