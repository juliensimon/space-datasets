#!/usr/bin/env python3
"""Shared helpers for NASA JPL SSD API endpoints."""

import time

import pandas as pd
import requests


JPL_BASE = "https://ssd-api.jpl.nasa.gov"


def jpl_query(endpoint: str, params: dict | None = None, timeout: int = 120) -> dict:
    """Query a JPL SSD API endpoint and return parsed JSON.

    Retries up to 3 times with exponential backoff on 5xx errors.
    """
    url = f"{JPL_BASE}/{endpoint}"
    for attempt in range(3):
        resp = requests.get(url, params=params, timeout=timeout)
        if resp.status_code < 500:
            resp.raise_for_status()
            return resp.json()
        if attempt < 2:
            wait = 5 * (2 ** attempt)  # 5s, 10s
            print(f"  JPL API returned {resp.status_code}, retrying in {wait}s (attempt {attempt + 1}/3)...")
            time.sleep(wait)
    resp.raise_for_status()
    return resp.json()


def jpl_fields_data_to_df(payload: dict) -> pd.DataFrame:
    """Convert JPL's {"fields": [...], "data": [[...]]} format to DataFrame."""
    return pd.DataFrame(payload["data"], columns=payload["fields"])
