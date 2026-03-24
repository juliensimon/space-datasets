#!/usr/bin/env python3
"""Shared helpers for NASA JPL SSD API endpoints."""

import pandas as pd
import requests


JPL_BASE = "https://ssd-api.jpl.nasa.gov"


def jpl_query(endpoint: str, params: dict | None = None, timeout: int = 120) -> dict:
    """Query a JPL SSD API endpoint and return parsed JSON."""
    url = f"{JPL_BASE}/{endpoint}"
    resp = requests.get(url, params=params, timeout=timeout)
    resp.raise_for_status()
    return resp.json()


def jpl_fields_data_to_df(payload: dict) -> pd.DataFrame:
    """Convert JPL's {"fields": [...], "data": [[...]]} format to DataFrame."""
    return pd.DataFrame(payload["data"], columns=payload["fields"])
