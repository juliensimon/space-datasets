"""Column cleaning helpers for DataFrames."""

from __future__ import annotations

import pandas as pd


def coerce_numeric(df: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    """Coerce columns to numeric, setting unparseable values to NaN.

    Skips columns not present in the DataFrame with a warning.

    Args:
        df: DataFrame to modify (in-place).
        columns: Column names to coerce.

    Returns:
        The same DataFrame (for chaining).
    """
    for col in columns:
        if col not in df.columns:
            print(f"  Warning: column '{col}' not in DataFrame, skipping coerce_numeric")
            continue
        df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


def coerce_int(df: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    """Coerce columns to nullable Int64, setting unparseable values to NA.

    Skips columns not present in the DataFrame with a warning.

    Args:
        df: DataFrame to modify (in-place).
        columns: Column names to coerce.

    Returns:
        The same DataFrame (for chaining).
    """
    for col in columns:
        if col not in df.columns:
            print(f"  Warning: column '{col}' not in DataFrame, skipping coerce_int")
            continue
        df[col] = pd.to_numeric(df[col], errors="coerce").astype("Int64")
    return df


def drop_mostly_null(df: pd.DataFrame, threshold: float = 0.95) -> pd.DataFrame:
    """Drop columns where the null fraction exceeds a threshold.

    Common for TAP/ADQL sources where wide schemas carry empty optional fields.

    Args:
        df: Input DataFrame.
        threshold: Drop columns with null fraction above this. Default: 0.95.

    Returns:
        A new DataFrame with high-null columns removed.
    """
    to_drop = [col for col in df.columns if df[col].isna().mean() > threshold]
    if to_drop:
        print(f"  Dropped {len(to_drop)} mostly-null columns: {to_drop}")
    return df.drop(columns=to_drop)


def clean_strings(df: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    """Strip whitespace and replace empty/sentinel strings with pd.NA.

    Handles: empty strings, whitespace-only strings, "nan", "None".

    Args:
        df: DataFrame to modify (in-place).
        columns: Column names to clean.

    Returns:
        The same DataFrame (for chaining).
    """
    for col in columns:
        if col not in df.columns:
            print(f"  Warning: column '{col}' not in DataFrame, skipping clean_strings")
            continue
        if pd.api.types.is_numeric_dtype(df[col]):
            print(f"  Warning: skipping clean_strings on numeric column '{col}'")
            continue
        # Preserve existing NAs before string conversion (astype(str) turns pd.NA → "<NA>")
        mask = df[col].isna()
        df[col] = df[col].astype(str).str.strip()
        df[col] = df[col].replace({"": pd.NA, "nan": pd.NA, "None": pd.NA, "none": pd.NA, "<NA>": pd.NA})
        df.loc[mask, col] = pd.NA
        df[col] = df[col].astype("string")
    return df
