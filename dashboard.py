"""
dashboard.py
------------
Renders the main dashboard page: header, metric cards, charts, and tables.

Kept separate from app.py so app.py stays focused on upload handling and
caching, while this module stays focused purely on presentation. All chart
figures come from visualization.py -- this file only arranges them into
the page layout.
"""

import pandas as pd
import streamlit as st

import visualization as viz


def render(df: pd.DataFrame, stats: dict, filename: str, file_size_mb: float):
    """Render the full dashboard for one processed log file."""
    _render_header(filename, file_size_mb, stats)

    if stats["total_logs"] == 0:
        st.warning("No records were successfully parsed from this file. "
                    "Check that it matches the configured log format.")
        return

    _render_metric_cards(stats)
    st.divider()
    _render_charts(df, stats)


def _render_header(filename: str, file_size_mb: float, stats: dict):
    st.subheader(f"📄 {filename}")
    cols = st.columns(4)
    cols[0].metric("File Size", f"{file_size_mb:.1f} MB")
    cols[1].metric("Total Records", f"{stats['total_lines_read']:,}")
    cols[2].metric("Parse Failures", f"{stats['parse_failures']:,}")
    cols[3].metric("Processing Time", f"{stats['processing_time_seconds']:.2f}s")
    st.caption(
        f"Processed with **{stats['workers_used']} worker(s)** across "
        f"**{stats['chunks']} chunk(s)**."
    )


def _render_metric_cards(stats: dict):
    st.markdown("### Overview")
    sev = stats["severity_counts"]

    row1 = st.columns(3)
    row1[0].metric("Total Logs", f"{stats['total_logs']:,}")
    row1[1].metric("Unique IPs", f"{stats['unique_ips']:,}")
    row1[2].metric("Avg Requests/Min", f"{stats['avg_requests_per_minute']:.1f}")

    row2 = st.columns(4)
    row2[0].metric("Info", f"{sev.get('INFO', 0):,}")
    row2[1].metric("Warning", f"{sev.get('WARNING', 0):,}")
    row2[2].metric("Error", f"{sev.get('ERROR', 0):,}")
    row2[3].metric("Critical", f"{sev.get('CRITICAL', 0):,}")

    row3 = st.columns(3)
    most_active_ip, most_active_count = stats["most_active_ip"]
    row3[0].metric("Most Active IP", most_active_ip or "N/A",
                    f"{most_active_count} requests" if most_active_ip else None)
    peak_hour = stats["peak_traffic_hour"]
    row3[1].metric(
        "Peak Traffic Hour",
        f"{peak_hour:02d}:00" if peak_hour is not None else "N/A",
        f"{stats['peak_traffic_hour_count']} requests" if peak_hour is not None else None,
    )
    row3[2].metric("Median Response Time", f"{stats['response_time_stats']['median_ms']:.0f} ms")

    st.caption(
        "⏱️ Time-based metrics and charts use **synthesized timestamps** -- "
        "the source dataset had an identical timestamp on every row. "
        "See README for details."
    )


def _render_charts(df: pd.DataFrame, stats: dict):
    st.markdown("### Charts")

    col1, col2 = st.columns(2)
    with col1:
        st.plotly_chart(viz.severity_pie(stats), use_container_width=True)
    with col2:
        st.plotly_chart(viz.status_codes_bar(stats), use_container_width=True)

    col3, col4 = st.columns(2)
    with col3:
        st.plotly_chart(viz.top_ips_bar(df), use_container_width=True)
    with col4:
        st.plotly_chart(viz.top_urls_bar(stats), use_container_width=True)

    col5, col6 = st.columns(2)
    with col5:
        st.plotly_chart(viz.http_methods_bar(stats), use_container_width=True)
    with col6:
        st.plotly_chart(viz.response_time_histogram(df), use_container_width=True)

    st.plotly_chart(viz.requests_per_hour_line(df), use_container_width=True)
    st.plotly_chart(viz.errors_over_time_line(df), use_container_width=True)
    st.plotly_chart(viz.traffic_heatmap(df), use_container_width=True)
