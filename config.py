"""
config.py
---------
Central configuration for the Parallel Log Analysis Dashboard.

Holds:
- Log format definitions (regex patterns + which fields each format provides)
- Defaults for chunking, worker options, and top-N result sizes
- Settings for synthetic timestamp generation

Keeping all of this in one file means a new log format, worker option, or
default can be added later without touching parser.py, parallel_processor.py,
or statistics.py.
"""

import re

# ---------------------------------------------------------------------------
# Log format registry
# ---------------------------------------------------------------------------
# Each entry defines:
#   - "regex": compiled pattern with named groups
#   - "timestamp_format": strptime format for the raw timestamp field
#   - "fields": which logical fields this format actually provides, so the
#     statistics/dashboard layers know which metrics to compute and display
LOG_FORMATS = {
    "apache_combined_ext": {
        "description": (
            "Apache Combined Log Format extended with a trailing "
            "response-time-in-ms field."
        ),
        "regex": re.compile(
            r'^(?P<ip>\S+) \S+ \S+ \[(?P<timestamp>[^\]]+)\] '
            r'"(?P<method>[A-Z]+) (?P<path>\S+) (?P<protocol>[^"]+)" '
            r'(?P<status>\d{3}) (?P<bytes>\d+|-) '
            r'"(?P<referrer>[^"]*)" "(?P<user_agent>[^"]*)" '
            r'(?P<response_time_ms>\d+)\s*$'
        ),
        "timestamp_format": "%d/%b/%Y:%H:%M:%S %z",
        "fields": {
            "ip", "timestamp", "method", "path", "protocol", "status",
            "bytes", "referrer", "user_agent", "response_time_ms",
        },
    },
}

DEFAULT_FORMAT = "apache_combined_ext"

# ---------------------------------------------------------------------------
# File upload validation
# ---------------------------------------------------------------------------
ALLOWED_EXTENSIONS = {".log", ".txt"}
MAX_FILE_SIZE_MB = 1024   # hard cap on uploaded file size

# ---------------------------------------------------------------------------
# Parallel processing defaults
# ---------------------------------------------------------------------------
WORKER_OPTIONS = [1, 2, 4, 8, 16]   # 1 = sequential baseline, used by benchmark mode
DEFAULT_WORKERS = 4
READ_BLOCK_SIZE = 8 * 1024 * 1024   # 8MB blocks used when scanning for chunk boundaries

# ---------------------------------------------------------------------------
# Statistics / dashboard defaults
# ---------------------------------------------------------------------------
TOP_N_DEFAULT = 10

# Apache logs carry no severity field, so severity is derived from the HTTP
# status code. 500/502 (server crash-level) count as CRITICAL; other 5xx as
# ERROR; 4xx as WARNING; 2xx/3xx as INFO. This convention is applied in
# statistics.py and disclosed in the README rather than assumed silently.
CRITICAL_STATUS_CODES = {500, 502}

# Username-based stats (Unique Users, Most Active User, Failed/Successful
# Logins) are disabled: this dataset's identuser/authuser fields are always
# empty, so there is no real username data to compute them from.
ENABLE_USER_STATS = False

# ---------------------------------------------------------------------------
# Synthetic timestamp settings
# ---------------------------------------------------------------------------
# The uploaded dataset has an IDENTICAL timestamp on every one of its
# 1,000,000 rows, which makes every time-based chart meaningless as-is.
# To demonstrate the time-series features, we deterministically synthesize
# a timestamp per row (seeded by line number, so results are identical
# regardless of how many workers process the file). This is clearly
# disclosed in the dashboard and README as synthetic, not real traffic data.
SYNTHETIC_TIME_ENABLED = True
SYNTHETIC_TIME_SPAN_DAYS = 7   # spread rows across a week

# Relative traffic weight per hour of day (index 0 = midnight), used so the
# synthesized traffic looks like a real site (busier during the day)
SYNTHETIC_HOURLY_WEIGHTS = [
    1, 1, 1, 1, 1, 2,     # 00:00 - 05:59  (quiet overnight)
    3, 5, 7, 8, 9, 9,     # 06:00 - 11:59  (ramping up)
    8, 8, 9, 9, 9, 8,     # 12:00 - 17:59  (steady daytime)
    7, 6, 5, 4, 3, 2,     # 18:00 - 23:59  (winding down)
]
