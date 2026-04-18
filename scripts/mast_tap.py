#!/usr/bin/env python3
"""Shared helpers for the MAST (Mikulski Archive for Space Telescopes) VO TAP service.

Used by update-jwst.py, update-hst.py, update-kepler-obs.py, update-galex.py,
and any future MAST mission datasets.

Key constraints learned from 4 missions:
- Sync TAP caps at 100K rows per request
- `dbo.caomplane` is wider and hits 504 at 100K — use 50K for it
- JOIN between caomobservation and caomplane times out server-side; aggregate client-side
- Keyset pagination on the primary-key `id` is much faster than composite ORDER BY
"""

from __future__ import annotations

import os
import re
import time
from pathlib import Path

import pandas as pd
import requests

MAST_TAP_URL = "https://mast.stsci.edu/vo-tap/api/v0.1/caom/sync"
DEFAULT_PAGE_SIZE = 100_000  # MAST sync cap
DEFAULT_PAGE_SLEEP = 0.5
DEFAULT_HTTP_TIMEOUT = 600

_TR_RE = re.compile(r"<TR>(.*?)</TR>", re.S)
_TD_RE = re.compile(r"<TD>(.*?)</TD>", re.S)
_FIELD_RE = re.compile(r'<FIELD\s+name="([^"]+)"', re.S)


def _parse_votable(text: str) -> pd.DataFrame:
    """Parse a MAST VOTable XML response into a DataFrame.

    Hand-rolled regex — ~10× faster than astropy.io.votable for the wide,
    string-heavy rows MAST returns, and avoids the astropy dependency.
    """
    fields = _FIELD_RE.findall(text)
    if not fields:
        return pd.DataFrame()
    rows = []
    for tr in _TR_RE.findall(text):
        cells = _TD_RE.findall(tr)
        if len(cells) == len(fields):
            rows.append(cells)
    df = pd.DataFrame(rows, columns=fields)
    df.replace({"": pd.NA}, inplace=True)
    return df


def tap_query(adql: str, tries: int = 3, timeout: int = DEFAULT_HTTP_TIMEOUT) -> pd.DataFrame:
    """Run a synchronous TAP query against MAST and return a DataFrame.

    Retries on network errors and non-200 responses. Raises RuntimeError
    (with the HTTP status in the message) if all retries fail — callers
    can catch the "504" substring to trigger adaptive page-size halving.
    """
    last_err = None
    for attempt in range(tries):
        try:
            r = requests.post(
                MAST_TAP_URL,
                data={"QUERY": adql, "REQUEST": "doQuery", "LANG": "ADQL"},
                timeout=timeout,
            )
            if r.status_code == 200:
                return _parse_votable(r.text)
            last_err = f"HTTP {r.status_code}: {r.text[:200]}"
        except requests.RequestException as e:
            last_err = str(e)
        wait = 5 * (attempt + 1)
        print(f"    TAP error ({last_err}); retry in {wait}s")
        time.sleep(wait)
    raise RuntimeError(f"TAP query failed after {tries} attempts: {last_err}")


def fetch_paginated(
    select: str,
    table: str,
    where: str,
    order_col: str,
    page_size: int = DEFAULT_PAGE_SIZE,
    sleep_between: float = DEFAULT_PAGE_SLEEP,
) -> pd.DataFrame:
    """Keyset-paginate a large MAST TAP query.

    Uses `ORDER BY order_col ASC` and `order_col > '<last_value>'` to seek
    past each page. On a 504, halves the page size down to 5,000 and retries;
    does not ramp back up (bouncing between 50K and 25K wastes pages to 504s).

    Args:
        select: Column list (no leading SELECT).
        table: Fully-qualified table name (e.g. "dbo.caomobservation").
        where: WHERE clause (no leading WHERE).
        order_col: Column used for keyset pagination. Must be uniquely
            sortable — primary keys work well.
        page_size: Starting TOP limit. MAST sync caps at 100,000.
        sleep_between: Pause between pages to avoid hammering the service.
    """
    chunks: list[pd.DataFrame] = []
    last_key = None
    total = 0
    current_size = page_size
    while True:
        clause = where if last_key is None else f"{where} AND {order_col} > '{last_key}'"
        q = f"SELECT TOP {current_size} {select} FROM {table} WHERE {clause} ORDER BY {order_col}"
        try:
            df = tap_query(q)
        except RuntimeError as e:
            if "504" in str(e) and current_size > 5_000:
                current_size = max(current_size // 2, 5_000)
                print(f"    504 on {table}: halving page size to {current_size:,}")
                time.sleep(10)
                continue
            raise
        if df.empty:
            break
        chunks.append(df)
        total += len(df)
        last_key = df[order_col].iloc[-1]
        print(f"    {table}: {total:,} rows (last {order_col}={str(last_key)[:40]}...)")
        if len(df) < current_size:
            break
        time.sleep(sleep_between)
    if not chunks:
        return pd.DataFrame()
    return pd.concat(chunks, ignore_index=True)


def load_checkpoint(path: str | os.PathLike | None) -> pd.DataFrame | None:
    """Load a cached parquet dataframe from disk. Returns None if missing or unreadable."""
    if not path:
        return None
    p = Path(path)
    if not p.exists():
        return None
    try:
        df = pd.read_parquet(p)
        print(f"  Loaded checkpoint from {p}: {len(df):,} rows")
        return df
    except Exception as e:
        print(f"  Checkpoint load failed: {e}")
        return None


def save_checkpoint(path: str | os.PathLike | None, df: pd.DataFrame) -> None:
    """Save a dataframe to disk as zstd parquet for future re-runs."""
    if not path:
        return
    try:
        df.to_parquet(path, compression="zstd")
        print(f"  Saved checkpoint to {path}")
    except Exception as e:
        print(f"  Checkpoint save failed (non-fatal): {e}")


def fetch_observations(
    collection: str,
    columns: str = "observationid, obstype, intent, prpid, prppi, prptitle, prpproject, prpkeywords, trgname, trgposra, trgposdec, trgmoving, insname, id",
    order_col: str = "observationid",
    page_size: int = DEFAULT_PAGE_SIZE,
) -> pd.DataFrame:
    """Fetch every CAOM observation row for a MAST collection (JWST, HST, KEPLER, GALEX, …).

    Default columns cover the common observation-level fields used by the
    per-mission scripts. Override `columns` to fetch a narrower or wider set.
    """
    return fetch_paginated(
        columns,
        "dbo.caomobservation",
        f"collection = '{collection}'",
        order_col,
        page_size=page_size,
    )


def fetch_planes(
    collection: str,
    columns: str = "observationuuid, timmin, timmax, timexposure, enrmin, enrmax, enrbandpassname, dataproducttype, calibrationlevel, releasedate, id",
    page_size: int = 50_000,
) -> pd.DataFrame:
    """Fetch every CAOM plane row for a collection. Planes are wider, so default
    page_size is 50K — 100K reliably hits 504 on this table.
    """
    return fetch_paginated(
        columns,
        "dbo.caomplane",
        f"collection = '{collection}'",
        "id",
        page_size=page_size,
    )
