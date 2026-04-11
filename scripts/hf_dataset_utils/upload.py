"""Parquet writing and Hugging Face upload."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pandas as pd


def write_parquet(
    df: pd.DataFrame,
    path: str | Path,
    compression: str = "zstd",
) -> Path:
    """Write a DataFrame to Parquet with sensible defaults.

    Args:
        df: DataFrame to write.
        path: Output file path.
        compression: Compression codec. Default: "zstd".

    Returns:
        The output path as a Path object.
    """
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
    """Upload a directory to a Hugging Face dataset repository.

    Requires the `hf` CLI to be installed and authenticated.

    Args:
        repo: HF repo ID (e.g., "user/dataset-name").
        local_dir: Local directory to upload.
        commit_message: Commit message for the upload.

    Raises:
        RuntimeError: If the `hf` CLI is not found on PATH.
        subprocess.CalledProcessError: If the upload fails.
    """
    if not shutil.which("hf"):
        raise RuntimeError(
            "The 'hf' CLI is not found on PATH. "
            "Install with: pip install 'hf-dataset-utils[hf]' "
            "or pip install huggingface_hub"
        )
    subprocess.run(
        [
            "hf", "upload", repo, str(local_dir), ".",
            "--repo-type", "dataset",
            "--commit-message", commit_message,
        ],
        check=True,
    )
