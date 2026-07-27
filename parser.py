"""
parser.py
---------
Parses individual raw log lines into structured Python dictionaries.

Responsibilities:
- Match a raw line against the configured log format regex
- Convert matched groups into the right types (int for status/bytes, etc.)
- Attach a deterministic synthetic timestamp (see config.py) alongside the
  real one, since the source dataset has a fixed timestamp on every row
- Return None (never raise) for lines that don't match, so a single
  malformed/corrupted/empty line never crashes a worker process

This module is intentionally free of any multiprocessing logic -- it's a
pure function library that worker.py calls once per line. Keeping it
decoupled means it can be unit tested directly and reused for the
sequential (1-worker) baseline used by the benchmark mode.
"""

from datetime import datetime
from typing import Optional

from config import LOG_FORMATS, DEFAULT_FORMAT
from utils import synthesize_timestamp


def parse_line(raw_line: str, line_number: int, log_format: str = DEFAULT_FORMAT) -> Optional[dict]:
    """
    Parse a single raw log line into a structured record.

    Args:
        raw_line: The raw text of one log line (may include trailing \\r\\n).
        line_number: 1-indexed position of this line in the original file.
            Used only to seed the synthetic timestamp deterministically.
        log_format: Key into config.LOG_FORMATS selecting which pattern to use.

    Returns:
        A dict of parsed fields on success, or None if the line does not
        match the configured format (malformed/corrupted/empty line).
    """
    line = raw_line.rstrip("\r\n")
    if not line.strip():
        return None

    pattern = LOG_FORMATS[log_format]["regex"]
    match = pattern.match(line)
    if match is None:
        return None

    groups = match.groupdict()

    try:
        real_timestamp = datetime.strptime(
            groups["timestamp"], LOG_FORMATS[log_format]["timestamp_format"]
        )
    except ValueError:
        real_timestamp = None

    return {
        "line_number": line_number,
        "ip": groups["ip"],
        "real_timestamp": real_timestamp,
        "synthetic_timestamp": synthesize_timestamp(line_number, real_timestamp),
        "method": groups["method"],
        "path": groups["path"],
        "protocol": groups["protocol"],
        "status": int(groups["status"]),
        "bytes": None if groups["bytes"] == "-" else int(groups["bytes"]),
        "referrer": groups["referrer"] if groups["referrer"] != "-" else None,
        "user_agent": groups["user_agent"],
        "response_time_ms": int(groups["response_time_ms"]),
    }
