"""
statistics.py
-------------
The "generate final statistics" step of the pipeline. Takes the merged
DataFrame produced by parallel_processor.run_parallel_analysis() and
computes every summary metric the dashboard needs.

This module deliberately does NOT touch multiprocessing at all. By the time
data reaches here, the expensive per-line work (regex parsing, timestamp
synthesis) is already done -- everything below is vectorized pandas, which
is fast regardless of how many workers were used upstream. Splitting the
pipeline this way keeps the "is multiprocessing worth it" story honest: the
part that gets faster with more workers is parsing, not summarizing.
"""

import pandas as pd

from config import TOP_N_DEFAULT, CRITICAL_STATUS_CODES


def classify_severity(status_code: int) -> str:
    """
    Map an HTTP status code to a log severity level.

    Convention (documented in config.py since it's a design decision, not
    something the raw data states):
        2xx / 3xx        -> INFO
        4xx              -> WARNING
        5xx (not below)  -> ERROR
        500 / 502        -> CRITICAL  (server crash-level)
    """
    if status_code in CRITICAL_STATUS_CODES:
        return "CRITICAL"
    if 500 <= status_code < 600:
        return "ERROR"
    if 400 <= status_code < 500:
        return "WARNING"
    return "INFO"


def compute_statistics(df: pd.DataFrame, pipeline_meta: dict, top_n: int = TOP_N_DEFAULT) -> dict:
    """
    Compute every summary statistic the dashboard displays.

    Args:
        df: The merged DataFrame from run_parallel_analysis()["dataframe"].
        pipeline_meta: The rest of run_parallel_analysis()'s return dict
            (workers_used, elapsed_seconds, chunks, parse_failures,
            total_lines) so processing metadata travels alongside the stats.
        top_n: How many entries to keep in "top" rankings (URLs, IPs, etc).

    Returns:
        A dict of every metric, chart-ready series, and pipeline metadata
        the dashboard needs. Returns sensible empty/zero values (never
        raises) if df is empty, so an all-malformed upload still renders
        a dashboard instead of crashing.
    """
    if df.empty:
        return _empty_statistics(pipeline_meta)

    severity = df["status"].apply(classify_severity)
    severity_counts = severity.value_counts().reindex(
        ["INFO", "WARNING", "ERROR", "CRITICAL"], fill_value=0
    ).to_dict()

    ip_counts = df["ip"].value_counts()
    most_active_ip = (ip_counts.index[0], int(ip_counts.iloc[0])) if not ip_counts.empty else (None, 0)

    top_urls = df["path"].value_counts().head(top_n)
    top_methods = df["method"].value_counts().to_dict()
    status_distribution = df["status"].value_counts().sort_index().to_dict()

    timestamps = df["synthetic_timestamp"]
    span_minutes = max((timestamps.max() - timestamps.min()).total_seconds() / 60, 1)
    avg_requests_per_minute = round(len(df) / span_minutes, 2)

    hourly_counts = timestamps.dt.hour.value_counts()
    peak_hour = int(hourly_counts.idxmax())
    peak_hour_count = int(hourly_counts.max())

    response_time_stats = {
        "mean_ms": round(df["response_time_ms"].mean(), 2),
        "median_ms": round(df["response_time_ms"].median(), 2),
        "p95_ms": round(df["response_time_ms"].quantile(0.95), 2),
        "max_ms": int(df["response_time_ms"].max()),
    }

    return {
        "total_logs": len(df),
        "severity_counts": severity_counts,
        "unique_ips": int(df["ip"].nunique()),
        "most_active_ip": most_active_ip,
        "top_urls": top_urls,
        "top_methods": top_methods,
        "status_distribution": status_distribution,
        "avg_requests_per_minute": avg_requests_per_minute,
        "peak_traffic_hour": peak_hour,
        "peak_traffic_hour_count": peak_hour_count,
        "response_time_stats": response_time_stats,
        # Pipeline metadata, passed through so the dashboard can show
        # "Processing Time" and "Workers Used" alongside the content stats.
        "processing_time_seconds": round(pipeline_meta.get("elapsed_seconds", 0), 2),
        "workers_used": pipeline_meta.get("workers_used"),
        "chunks": pipeline_meta.get("chunks"),
        "parse_failures": pipeline_meta.get("parse_failures", 0),
        "total_lines_read": pipeline_meta.get("total_lines", len(df)),
    }


def _empty_statistics(pipeline_meta: dict) -> dict:
    """Zeroed-out statistics shape returned when the DataFrame has no rows."""
    return {
        "total_logs": 0,
        "severity_counts": {"INFO": 0, "WARNING": 0, "ERROR": 0, "CRITICAL": 0},
        "unique_ips": 0,
        "most_active_ip": (None, 0),
        "top_urls": pd.Series(dtype=int),
        "top_methods": {},
        "status_distribution": {},
        "avg_requests_per_minute": 0.0,
        "peak_traffic_hour": None,
        "peak_traffic_hour_count": 0,
        "response_time_stats": {"mean_ms": 0, "median_ms": 0, "p95_ms": 0, "max_ms": 0},
        "processing_time_seconds": round(pipeline_meta.get("elapsed_seconds", 0), 2),
        "workers_used": pipeline_meta.get("workers_used"),
        "chunks": pipeline_meta.get("chunks"),
        "parse_failures": pipeline_meta.get("parse_failures", 0),
        "total_lines_read": pipeline_meta.get("total_lines", 0),
    }
