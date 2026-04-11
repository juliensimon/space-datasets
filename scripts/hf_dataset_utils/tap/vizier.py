"""VizieR TAP client with recno-based cursor pagination."""

from __future__ import annotations

import io
import re
import sys
import time

import pandas as pd
import requests

TAP_URL = "https://tapvizier.cds.unistra.fr/TAPVizieR/tap/sync"
PAGE_SIZE = 500_000


def _add_recno_filter(adql: str, last_recno: int) -> str:
    """Inject a recno > N filter into an ADQL query."""
    filter_clause = f"recno > {last_recno}"
    order_match = re.search(r"\bORDER\s+BY\b", adql, re.IGNORECASE)
    if order_match:
        insert_pos = order_match.start()
        before = adql[:insert_pos].rstrip()
        after = adql[insert_pos:]
    else:
        before = adql.rstrip()
        after = ""
    if re.search(r"\bWHERE\b", before, re.IGNORECASE):
        before = f"{before} AND {filter_clause}"
    else:
        before = f"{before} WHERE {filter_clause}"
    return f"{before} {after}".strip() if after else before


def _fetch_page(adql: str, timeout: int, retries: int = 3) -> pd.DataFrame:
    """Fetch a single TAP query page with retry logic."""
    for attempt in range(retries):
        try:
            resp = requests.post(TAP_URL, data={
                "REQUEST": "doQuery", "LANG": "ADQL",
                "FORMAT": "csv", "QUERY": adql,
            }, timeout=timeout)
            resp.raise_for_status()
            break
        except Exception as e:
            if attempt < retries - 1:
                wait = 10 * (2 ** attempt)
                print(f"  VizieR retry {attempt + 1}/{retries} in {wait}s: {e}")
                time.sleep(wait)
            else:
                raise
    text = resp.text.strip()
    if text.startswith("<?xml") or text.startswith("<VOTABLE"):
        print(f"::error::VizieR returned VOTable error:\n{text[:500]}")
        sys.exit(1)
    return pd.read_csv(io.StringIO(text))


def vizier_query(
    adql: str,
    max_rows: int | None = None,
    page_size: int = PAGE_SIZE,
    timeout: int = 300,
) -> pd.DataFrame:
    """Query VizieR TAP service with automatic recno-based pagination.

    VizieR TAP does not support OFFSET, so pagination uses the recno
    pseudo-column as a cursor.
    """
    df = _fetch_page(adql, timeout)
    print(f"  VizieR: fetched {len(df):,} rows (page 1)")
    if len(df) < page_size or (max_rows and len(df) >= max_rows):
        return df.head(max_rows) if max_rows else df
    if "recno" not in df.columns:
        print("  Warning: no recno column, cannot paginate — returning partial results")
        return df
    all_dfs = [df]
    total = len(df)
    while True:
        last_recno = int(df["recno"].max())
        paged_adql = _add_recno_filter(adql, last_recno)
        time.sleep(1)
        df = _fetch_page(paged_adql, timeout)
        if len(df) == 0:
            break
        all_dfs.append(df)
        total += len(df)
        print(f"  VizieR: fetched {len(df):,} rows (total: {total:,})")
        if len(df) < page_size:
            break
        if max_rows and total >= max_rows:
            break
    result = pd.concat(all_dfs, ignore_index=True)
    return result.head(max_rows) if max_rows else result
