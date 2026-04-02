#!/usr/bin/env python3
"""VizieR TAP client with automatic pagination for large catalogs."""

import io
import sys
import time

import pandas as pd
import requests


TAP_URL = "https://tapvizier.cds.unistra.fr/TAPVizieR/tap/sync"
PAGE_SIZE = 500_000


def vizier_query(adql: str, max_rows: int | None = None, timeout: int = 300) -> pd.DataFrame:
    """Run an ADQL query against VizieR TAP, paginating if needed.

    For large catalogs (>500K rows), paginates using recno filtering
    since VizieR TAP does not support OFFSET.
    """
    print(f"  VizieR TAP: {adql.strip()[:80]}...")
    df = _fetch_page(adql, timeout)

    if len(df) < PAGE_SIZE and max_rows is None:
        return df

    if max_rows and len(df) >= max_rows:
        return df.head(max_rows)

    # Need pagination — use recno cursor
    if "recno" not in df.columns:
        print(f"  WARNING: no recno column for pagination, returning {len(df):,} rows")
        return df

    print(f"  Got {len(df):,} rows, paginating via recno...")
    all_dfs = [df]

    while True:
        max_recno = int(df["recno"].max())
        # Build paginated query by adding recno filter
        paged = _add_recno_filter(adql, max_recno)
        df = _fetch_page(paged, timeout)
        if len(df) == 0:
            break
        all_dfs.append(df)
        total = sum(len(d) for d in all_dfs)
        print(f"  ... {total:,} rows fetched")
        time.sleep(1)

        if max_rows and total >= max_rows:
            break

    result = pd.concat(all_dfs, ignore_index=True)
    if max_rows:
        result = result.head(max_rows)
    print(f"  VizieR total: {len(result):,} rows")
    return result


def _add_recno_filter(adql: str, min_recno: int) -> str:
    """Add 'WHERE recno > N' or 'AND recno > N' to an ADQL query."""
    q = adql.strip().rstrip(";")
    upper = q.upper()
    if "WHERE" in upper:
        # Insert before ORDER BY if present, else at end
        if "ORDER BY" in upper:
            idx = upper.index("ORDER BY")
            return q[:idx] + f" AND recno > {min_recno} " + q[idx:]
        return q + f" AND recno > {min_recno}"
    else:
        if "ORDER BY" in upper:
            idx = upper.index("ORDER BY")
            return q[:idx] + f" WHERE recno > {min_recno} " + q[idx:]
        return q + f" WHERE recno > {min_recno}"


def _fetch_page(adql: str, timeout: int, retries: int = 3) -> pd.DataFrame:
    """Fetch a single page from VizieR TAP as CSV with retries."""
    import time as _time
    for attempt in range(retries):
        try:
            resp = requests.post(TAP_URL, data={
                "REQUEST": "doQuery",
                "LANG": "ADQL",
                "FORMAT": "csv",
                "QUERY": adql,
            }, timeout=timeout)
            resp.raise_for_status()
            break
        except Exception as e:
            if attempt < retries - 1:
                wait = 10 * (2 ** attempt)
                print(f"  VizieR request failed ({e}), retrying in {wait}s...")
                _time.sleep(wait)
            else:
                raise

    text = resp.text.strip()
    if text.startswith("<?xml") or text.startswith("<VOTABLE"):
        print("::error::VizieR returned VOTable instead of CSV")
        sys.exit(1)

    try:
        return pd.read_csv(io.StringIO(resp.text))
    except Exception as e:
        print(f"::error::Failed to parse VizieR CSV: {e}")
        sys.exit(1)
