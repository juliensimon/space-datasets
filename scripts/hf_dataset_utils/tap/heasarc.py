"""HEASARC TAP client with format fallback chain."""

from __future__ import annotations

import io

import pandas as pd
import requests

TAP_URL = "https://heasarc.gsfc.nasa.gov/xamin/vo/tap/sync"


def _parse_text(text: str) -> pd.DataFrame | None:
    """Parse HEASARC pipe-delimited text format."""
    if text.strip().startswith("<?xml") or text.strip().startswith("<VOTABLE"):
        return None
    lines = [l for l in text.strip().split("\n") if l.strip()]
    if len(lines) < 2:
        return None

    # Strip leading/trailing pipes, then split — handles both "|ra|dec|" and "ra|dec"
    headers = [h.strip() for h in lines[0].strip().strip("|").split("|")]
    headers = [h for h in headers if h]  # remove phantom empty strings

    # Skip separator lines (lines that are only dashes, pipes, and spaces)
    data_lines = []
    for line in lines[1:]:
        stripped = line.strip().replace("|", "").replace("-", "").replace(" ", "")
        if not stripped:  # separator line — skip it
            continue
        values = [v.strip() for v in line.strip().strip("|").split("|")]
        values = values[:len(headers)]  # trim to header count
        if len(values) == len(headers):
            data_lines.append(values)

    if not data_lines:
        return None

    df = pd.DataFrame(data_lines, columns=headers)
    # Replace HEASARC's literal "null" strings with NaN
    df = df.replace({"null": pd.NA, "NULL": pd.NA})
    # Auto-detect numeric types to match pd.read_csv behavior
    for col in df.columns:
        try:
            converted = pd.to_numeric(df[col], errors="coerce")
            if not converted.isna().all():  # at least some values parsed
                if converted.isna().sum() == df[col].isna().sum():  # no new NaNs introduced
                    df[col] = converted
        except (ValueError, TypeError):
            pass
    return df


def _parse_csv(text: str) -> pd.DataFrame | None:
    """Parse CSV format, rejecting VOTable XML."""
    if text.strip().startswith("<?xml") or text.strip().startswith("<VOTABLE"):
        return None
    try:
        return pd.read_csv(io.StringIO(text))
    except Exception:
        return None


def _parse_json(text: str) -> pd.DataFrame | None:
    """Parse HEASARC JSON format."""
    import json
    try:
        data = json.loads(text)
        if "metadata" in data and "data" in data:
            columns = [m["name"] for m in data["metadata"]]
            return pd.DataFrame(data["data"], columns=columns)
        return pd.DataFrame(data)
    except Exception:
        return None


_PARSERS = {
    "text": _parse_text,
    "csv": _parse_csv,
    "json": _parse_json,
}


def heasarc_query(
    table: str,
    adql: str,
    formats: list[str] | None = None,
    timeout: int = 120,
) -> pd.DataFrame:
    """Query HEASARC TAP service with format fallback chain.

    HEASARC sometimes returns VOTable XML when you request CSV.
    This tries multiple formats in order until one succeeds.

    Raises RuntimeError if all formats fail.
    """
    formats = formats or ["text", "csv", "json"]
    errors = []
    for fmt in formats:
        parser = _PARSERS.get(fmt)
        if not parser:
            continue
        try:
            resp = requests.get(TAP_URL, params={
                "REQUEST": "doQuery", "LANG": "ADQL",
                "FORMAT": fmt, "QUERY": adql,
            }, timeout=timeout)
            resp.raise_for_status()
            df = parser(resp.text)
            if df is not None and len(df) > 0:
                print(f"  HEASARC ({table}): {len(df):,} rows via {fmt} format")
                return df
            errors.append(f"{fmt}: parsed but got empty/invalid result")
        except Exception as e:
            errors.append(f"{fmt}: {e}")
        print(f"  HEASARC: {fmt} format failed, trying next...")
    raise RuntimeError(
        f"All formats failed for HEASARC table {table}:\n"
        + "\n".join(f"  - {e}" for e in errors)
    )
