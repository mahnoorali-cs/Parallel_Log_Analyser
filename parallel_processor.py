"""
parallel_processor.py
----------------------
The core parallel processing engine. This is the most important module in
the project -- it is responsible for:

1. Splitting the log file into line-safe byte-range chunks (never loading
   the whole file into memory in the main process)
2. Dispatching chunks to a multiprocessing.Pool of worker processes
3. Reporting progress as chunks complete
4. Merging each worker's partial DataFrame into one final DataFrame

Kept deliberately free of any Streamlit or statistics logic, so the same
function powers both the normal dashboard run and benchmark.py's repeated
runs at different worker counts.
"""

import multiprocessing
import time
from typing import Callable, Optional

import pandas as pd

from config import DEFAULT_FORMAT, READ_BLOCK_SIZE
from worker import _process_chunk_star


def compute_chunk_boundaries(filepath: str, num_workers: int) -> list[dict]:
    """
    Scan the file once to find line-safe byte boundaries for N chunks.

    Splitting by a naive `file_size / num_workers` byte offset can cut a
    log line in half, corrupting the record at each chunk boundary. This
    function does a single sequential pass over the file (in fixed-size
    binary blocks, never loading the whole file at once) and only cuts a
    chunk at a newline, so every chunk starts and ends on a full line.

    It also tracks the starting line number of each chunk so synthetic
    timestamps stay reproducible regardless of how the file is split
    (see utils.synthesize_timestamp).

    Args:
        filepath: Path to the log file on disk.
        num_workers: How many chunks to split the file into.

    Returns:
        A list of dicts, one per chunk, each with:
            "start_byte", "end_byte", "start_line_number"
    """
    file_size = _file_size(filepath)
    target_chunk_size = max(file_size // num_workers, 1)

    boundaries = []
    current_start_byte = 0
    current_start_line = 1
    line_count = 0
    bytes_scanned = 0

    with open(filepath, "rb") as f:
        while len(boundaries) < num_workers - 1:
            block = f.read(READ_BLOCK_SIZE)
            if not block:
                break

            block_start_pos = bytes_scanned
            newline_positions = []
            search_from = 0
            while True:
                pos = block.find(b"\n", search_from)
                if pos == -1:
                    break
                newline_positions.append(pos)
                search_from = pos + 1

            target_pos = current_start_byte + target_chunk_size
            cut_made = False
            for pos in newline_positions:
                absolute_pos = block_start_pos + pos
                line_count += 1
                if absolute_pos >= target_pos and absolute_pos > current_start_byte:
                    end_byte = absolute_pos + 1  # include the newline itself
                    boundaries.append({
                        "start_byte": current_start_byte,
                        "end_byte": end_byte,
                        "start_line_number": current_start_line,
                    })
                    current_start_byte = end_byte
                    current_start_line += line_count
                    line_count = 0
                    cut_made = True
                    break

            bytes_scanned += len(block)
            if cut_made:
                # Re-seek so the next block read starts exactly where we cut
                f.seek(current_start_byte)
                bytes_scanned = current_start_byte

    # Final chunk always runs to true end of file
    boundaries.append({
        "start_byte": current_start_byte,
        "end_byte": file_size,
        "start_line_number": current_start_line,
    })

    return boundaries


def run_parallel_analysis(
    filepath: str,
    num_workers: int,
    log_format: str = DEFAULT_FORMAT,
    progress_callback: Optional[Callable[[int, int], None]] = None,
) -> dict:
    """
    Run the full split -> dispatch -> merge pipeline.

    Args:
        filepath: Path to the log file on disk.
        num_workers: Number of worker processes to use. 1 means a true
            sequential run (still goes through this same function, so
            benchmark.py's baseline measurement uses identical code paths).
        log_format: Key into config.LOG_FORMATS.
        progress_callback: Optional callable(completed_chunks, total_chunks)
            invoked as each chunk finishes, for a Streamlit progress bar.

    Returns:
        A dict with:
            "dataframe": merged pandas DataFrame of all parsed records
            "total_lines": total lines read across all chunks
            "parse_failures": total unparsed lines across all chunks
            "workers_used": num_workers
            "chunks": number of chunks the file was split into
            "elapsed_seconds": wall-clock time for split + parse + merge
    """
    start_time = time.perf_counter()

    boundaries = compute_chunk_boundaries(filepath, num_workers)
    args = [
        (filepath, b["start_byte"], b["end_byte"], b["start_line_number"], log_format)
        for b in boundaries
    ]

    chunk_results = []
    total_chunks = len(args)

    if num_workers == 1:
        # True sequential path -- no Pool overhead at all, used as the
        # honest baseline for the benchmark tab's speedup calculation.
        for i, arg in enumerate(args, start=1):
            chunk_results.append(_process_chunk_star(arg))
            if progress_callback:
                progress_callback(i, total_chunks)
    else:
        with multiprocessing.Pool(processes=num_workers) as pool:
            for i, result in enumerate(pool.imap_unordered(_process_chunk_star, args), start=1):
                chunk_results.append(result)
                if progress_callback:
                    progress_callback(i, total_chunks)

    dataframes = [r["dataframe"] for r in chunk_results if not r["dataframe"].empty]
    merged_df = pd.concat(dataframes, ignore_index=True) if dataframes else pd.DataFrame()

    elapsed = time.perf_counter() - start_time

    return {
        "dataframe": merged_df,
        "total_lines": sum(r["lines_read"] for r in chunk_results),
        "parse_failures": sum(r["parse_failures"] for r in chunk_results),
        "workers_used": num_workers,
        "chunks": total_chunks,
        "elapsed_seconds": elapsed,
    }


def _file_size(filepath: str) -> int:
    """Return file size in bytes."""
    import os
    return os.path.getsize(filepath)
