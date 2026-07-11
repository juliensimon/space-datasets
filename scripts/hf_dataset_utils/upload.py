"""Parquet writing and Hugging Face upload."""

from __future__ import annotations

import os
import time
from pathlib import Path

import pandas as pd
from huggingface_hub import HfApi
from huggingface_hub.errors import HfHubHTTPError


def _hf_call_with_retry(fn, *args, max_attempts=10, base_delay=10, max_delay=300, **kwargs):
    """Call an HF API function, retrying on 429/5xx with capped exponential backoff."""
    for attempt in range(max_attempts):
        try:
            return fn(*args, **kwargs)
        except HfHubHTTPError as e:
            err = str(e)
            is_rate_limit = "429" in err
            is_server_error = any(code in err for code in ("500", "502", "503", "504"))
            if not (is_rate_limit or is_server_error) or attempt == max_attempts - 1:
                raise
            delay = min(base_delay * (2 ** attempt), max_delay)
            reason = "rate limit (429)" if is_rate_limit else "server error (5xx)"
            print(f"  HF {reason}, retrying in {delay}s (attempt {attempt + 1}/{max_attempts})...")
            time.sleep(delay)


def write_parquet(
    df: pd.DataFrame,
    path: str | Path,
    compression: str = "zstd",
) -> Path:
    """Write a DataFrame to Parquet with sensible defaults."""
    path = Path(path)
    df.to_parquet(path, index=False, engine="pyarrow", compression=compression)
    size_mb = path.stat().st_size / (1024 * 1024)
    print(f"  Wrote {path.name}: {len(df):,} rows, {size_mb:.1f} MB")
    return path


def upload_to_hf(
    repo: str,
    local_dir: str | Path,
    commit_message: str = "Update dataset",
) -> None:
    """Upload a directory to a Hugging Face dataset repository via Python API."""
    token = os.environ.get("HF_TOKEN")
    api = HfApi(token=token)
    _hf_call_with_retry(api.create_repo, repo, repo_type="dataset", exist_ok=True)
    _hf_call_with_retry(
        api.upload_folder,
        repo_id=repo,
        folder_path=str(local_dir),
        repo_type="dataset",
        commit_message=commit_message,
    )
