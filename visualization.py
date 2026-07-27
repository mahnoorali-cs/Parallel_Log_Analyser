"""
visualization.py
-----------------
Builds every Plotly chart the dashboard displays. Each function takes data
(the merged DataFrame and/or the stats dict from log_statistics.py) and
returns a plotly.graph_objects.Figure -- it never calls st.plotly_chart
directly. Keeping Streamlit calls out of this module means these functions
can be unit tested or reused (e.g. in exporter.py for the PDF report)
without needing a running Streamlit session.
"""

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

SEVERITY_COLORS = {
    "INFO": "#4C9AFF",
    "WARNING": "#FFAB00",
    "ERROR": "#FF5630",
    "CRITICAL": "#DE350B",
}


def severity_pie(stats: dict) -> go.Figure:
    """Pie chart: log severity distribution (INFO/WARNING/ERROR/CRITICAL)."""
    sev_df = pd.DataFrame({
        "severity": list(stats["severity_counts"].keys()),
        "count": list(stats["severity_counts"].values()),
    })
    fig = px.pie(
        sev_df, names="severity", values="count", title="Log Severity Distribution",
        color="severity", color_discrete_map=SEVERITY_COLORS, hole=0.35,
    )
    return fig


def top_ips_bar(df: pd.DataFrame, top_n: int = 10) -> go.Figure:
    """Horizontal bar chart: top N IP addresses by request count."""
    top_ips = df["ip"].value_counts().head(top_n).reset_index()
    top_ips.columns = ["ip", "count"]
    fig = px.bar(
        top_ips, x="count", y="ip", orientation="h",
        title=f"Top {top_n} IP Addresses",
    )
    fig.update_layout(yaxis={"categoryorder": "total ascending"})
    return fig


def top_urls_bar(stats: dict) -> go.Figure:
    """Horizontal bar chart: top requested URLs."""
    top_urls_df = stats["top_urls"].reset_index()
    top_urls_df.columns = ["url", "count"]
    fig = px.bar(
        top_urls_df, x="count", y="url", orientation="h",
        title="Top Requested URLs",
    )
    fig.update_layout(yaxis={"categoryorder": "total ascending"})
    return fig


def http_methods_bar(stats: dict) -> go.Figure:
    """Bar chart: request count per HTTP method."""
    methods_df = pd.DataFrame({
        "method": list(stats["top_methods"].keys()),
        "count": list(stats["top_methods"].values()),
    }).sort_values("count", ascending=False)
    fig = px.bar(methods_df, x="method", y="count", title="Top HTTP Methods")
    return fig


def status_codes_bar(stats: dict) -> go.Figure:
    """Bar chart: HTTP status code distribution."""
    status_df = pd.DataFrame({
        "status": [str(k) for k in stats["status_distribution"].keys()],
        "count": list(stats["status_distribution"].values()),
    })
    fig = px.bar(status_df, x="status", y="count", title="HTTP Status Code Distribution")
    # Without this, Plotly can infer a continuous numeric axis from digit-like
    # strings ("200", "404", ...) and render near-zero-width bars spread out
    # by their numeric value instead of evenly spaced categorical bars.
    fig.update_xaxes(type="category")
    fig.update_layout(bargap=0.3)
    return fig


def requests_per_hour_line(df: pd.DataFrame) -> go.Figure:
    """
    Line chart: request volume per hour across the synthesized time span.

    Uses synthetic_timestamp, not real_timestamp -- see config.py for why.
    """
    hourly = (
        df.set_index("synthetic_timestamp")
        .resample("1H").size()
        .reset_index(name="count")
    )
    fig = px.line(hourly, x="synthetic_timestamp", y="count", title="Requests Per Hour")
    fig.update_layout(xaxis_title="Time", yaxis_title="Requests")
    return fig


def errors_over_time_line(df: pd.DataFrame) -> go.Figure:
    """Line chart: error/critical-level request volume per hour over time."""
    error_mask = df["status"].astype(int) >= 400
    errors_df = df[error_mask]
    if errors_df.empty:
        return go.Figure().update_layout(title="Errors Over Time (no error records found)")

    hourly_errors = (
        errors_df.set_index("synthetic_timestamp")
        .resample("1H").size()
        .reset_index(name="count")
    )
    fig = px.line(hourly_errors, x="synthetic_timestamp", y="count", title="Errors Over Time")
    fig.update_traces(line_color="#DE350B")
    fig.update_layout(xaxis_title="Time", yaxis_title="Error Count")
    return fig


def traffic_heatmap(df: pd.DataFrame) -> go.Figure:
    """Heatmap: traffic volume by hour of day vs day of week."""
    working = df.copy()
    working["hour"] = working["synthetic_timestamp"].dt.hour
    working["weekday"] = working["synthetic_timestamp"].dt.day_name()

    weekday_order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    pivot = (
        working.groupby(["weekday", "hour"]).size()
        .unstack(fill_value=0)
        .reindex(weekday_order)
    )
    fig = px.imshow(
        pivot, aspect="auto", color_continuous_scale="Blues",
        labels={"x": "Hour of Day", "y": "Day of Week", "color": "Requests"},
        title="Traffic Heatmap (Hour vs Weekday)",
    )
    return fig


def response_time_histogram(df: pd.DataFrame) -> go.Figure:
    """Histogram: response time distribution in milliseconds."""
    fig = px.histogram(
        df, x="response_time_ms", nbins=50,
        title="Response Time Distribution (ms)",
    )
    fig.update_layout(xaxis_title="Response Time (ms)", yaxis_title="Count")
    return fig
