"""
worker.py
---------
The function that actually runs inside each worker process.

Each worker is handed a byte range of the log file (never the whole file,
and never pre-loaded lines from the main process) and reads that slice
directly off disk. This keeps memory usage per worker proportional to its
own chunk, not the whole file, and avoids paying pickling cost to ship raw
lines across the process boundary.

Design note: a worker's "analysis" step is building a pandas DataFrame from
its own parsed records. This is deliberate -- the expensive, embarrassingly
parallel part of this pipeline is per-line regex matching + type conversion
+ synthetic timestamp generation done in parser.py. Once records are
structured, merging (pd.concat) and final statistics (vectorized pandas ops)
are cheap regardless of worker count, so they belong in the main process
(see parallel_processor.py and statistics.py) rather than being duplicated
per worker.
"""

import pandas as pd

from parser import parse_line


def process_chunk(filepath: str, start_byte: int, end_byte: int,
                   start_line_number: int, log_format: str) -> dict:
    """
    Parse one byte-range slice of the log file in a single worker process.

    Args:
        filepath: Path to the full log file on disk (each worker opens it
            independently and seeks to its own range).
        start_byte: First byte this worker is responsible for (inclusive).
        end_byte: Last byte this worker is responsible for (exclusive).
            Boundaries are guaranteed line-safe by parallel_processor.py --
            no line is ever split between two workers.
        start_line_number: 1-indexed line number of the first line in this
            chunk, used to keep synthetic timestamps consistent regardless
            of how the file was split (see utils.synthesize_timestamp).
        log_format: Key into config.LOG_FORMATS to use for parsing.

    Returns:
        A dict with:
            "dataframe": pandas DataFrame of successfully parsed records
                (empty DataFrame if the chunk had zero valid lines)
            "lines_read": total lines seen in this chunk
            "parse_failures": lines that didn't match the format (malformed,
                empty, or corrupted records -- never raises, just skipped)
    """
    records = []
    parse_failures = 0
    line_number = start_line_number

    with open(filepath, "rb") as f:
        f.seek(start_byte)
        remaining = end_byte - start_byte
        raw = f.read(remaining).decode("utf-8", errors="replace")

    lines_read = 0
    for raw_line in raw.splitlines():
        lines_read += 1
        record = parse_line(raw_line, line_number, log_format)
        if record is None:
            parse_failures += 1
        else:
            records.append(record)
        line_number += 1

    dataframe = pd.DataFrame.from_records(records) if records else pd.DataFrame()

    return {
        "dataframe": dataframe,
        "lines_read": lines_read,
        "parse_failures": parse_failures,
    }


def _process_chunk_star(args: tuple) -> dict:
    """
    Unpacks a single argument tuple and calls process_chunk.

    multiprocessing.Pool.imap_unordered requires a function that takes one
    argument (so results can be paired back with progress tracking as they
    complete). This thin wrapper lets process_chunk keep a readable,
    multi-argument signature while still being imap-compatible.
    """
    return process_chunk(*args)
