"""
app.py
------
Streamlit entrypoint for the Parallel Log Analysis Dashboard.

Responsibilities:
- Render the sidebar: file upload, worker count selection, detected CPU cores
- Validate the uploaded file (config.py's rules, via utils.validate_log_file)
- Run the parallel processing pipeline with a live progress bar
- Cache results in st.session_state keyed by (file hash, worker count), so
  Streamlit's rerun-on-every-widget-interaction behavior does NOT silently
  re-trigger a full parallel analysis when the user just clicks something
  unrelated (e.g. a future filter widget) -- only a new file or a changed
  worker count triggers reprocessing
- Hand off to dashboard.py for rendering

The multiprocessing Pool lives inside parallel_processor.py, not here, but
the `if __name__ == "__main__":` guard below still matters: on platforms
that default to the "spawn" start method (Windows, macOS), worker processes
re-import this file as a module, and without the guard they would try to
re-run the whole Streamlit app inside each worker.
"""

import os

import streamlit as st

from config import WORKER_OPTIONS, DEFAULT_WORKERS, DEFAULT_FORMAT
from utils import get_cpu_core_count, validate_log_file, compute_file_hash
from parallel_processor import run_parallel_analysis
from log_statistics import compute_statistics
import dashboard

st.set_page_config(page_title="Parallel Log Analysis Dashboard", layout="wide", page_icon="📊")

UPLOAD_DIR = os.path.join(os.path.dirname(__file__), "logs")


def main():
    st.sidebar.title("⚙️ Controls")
    uploaded_file = st.sidebar.file_uploader("Upload a log file", type=["log", "txt"])

    cpu_cores = get_cpu_core_count()
    st.sidebar.caption(f"Detected CPU cores: **{cpu_cores}**")

    worker_count = st.sidebar.selectbox(
        "Number of workers",
        options=WORKER_OPTIONS,
        index=WORKER_OPTIONS.index(DEFAULT_WORKERS),
        help="1 worker = sequential baseline, useful for comparing against parallel runs.",
    )
    if worker_count > cpu_cores:
        st.sidebar.warning(
            f"{worker_count} workers selected but only {cpu_cores} CPU core(s) detected. "
            f"Extra workers may not speed things up and can add overhead."
        )

    st.title("📊 Parallel Log Analysis Dashboard")
    st.caption("A multiprocessing-powered log analysis engine for large server logs.")

    if uploaded_file is None:
        st.info("Upload a `.log` or `.txt` file from the sidebar to begin.")
        return

    temp_path = _persist_upload(uploaded_file)

    is_valid, error_message = validate_log_file(temp_path)
    if not is_valid:
        st.error(f"❌ {error_message}")
        return

    file_hash = compute_file_hash(temp_path)
    cache_key = f"{file_hash}_{worker_count}"

    if st.session_state.get("cache_key") != cache_key:
        _run_and_cache_analysis(temp_path, worker_count, uploaded_file.name, cache_key)

    dashboard.render(
        df=st.session_state["dataframe"],
        stats=st.session_state["stats"],
        filename=st.session_state["filename"],
        file_size_mb=st.session_state["file_size_mb"],
    )


def _run_and_cache_analysis(temp_path: str, worker_count: int, filename: str, cache_key: str):
    """Run the parallel pipeline once and store results in session_state."""
    progress_bar = st.progress(0.0, text="Starting parallel analysis...")

    def _update_progress(done: int, total: int):
        fraction = done / total if total else 1.0
        progress_bar.progress(fraction, text=f"Processed {done}/{total} chunks...")

    result = run_parallel_analysis(
        temp_path,
        num_workers=worker_count,
        log_format=DEFAULT_FORMAT,
        progress_callback=_update_progress,
    )
    progress_bar.empty()

    meta = {k: v for k, v in result.items() if k != "dataframe"}
    stats = compute_statistics(result["dataframe"], meta)

    st.session_state["cache_key"] = cache_key
    st.session_state["dataframe"] = result["dataframe"]
    st.session_state["stats"] = stats
    st.session_state["filename"] = filename
    st.session_state["file_size_mb"] = os.path.getsize(temp_path) / (1024 * 1024)


def _persist_upload(uploaded_file) -> str:
    """
    Save a Streamlit UploadedFile to disk so worker processes can seek/read
    their byte ranges directly, instead of holding the file in memory only
    on the main process.
    """
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    suffix = os.path.splitext(uploaded_file.name)[1] or ".log"
    safe_name = f"upload_{abs(hash(uploaded_file.name))}{suffix}"
    temp_path = os.path.join(UPLOAD_DIR, safe_name)
    with open(temp_path, "wb") as f:
        f.write(uploaded_file.getbuffer())
    return temp_path


if __name__ == "__main__":
    main()
