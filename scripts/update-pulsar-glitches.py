#!/usr/bin/env python3
"""Fetch Jodrell Bank Pulsar Glitch Catalogue and upload to HF.

Source: Jodrell Bank Centre for Astrophysics, University of Manchester.
https://www.jb.man.ac.uk/pulsar/glitches.html
"""

import re
import sys
import time

import pandas as pd
import requests
from bs4 import BeautifulSoup

from hf_dataset_utils import Pipeline

HF_REPO = "juliensimon/pulsar-glitch-catalog"
GLITCH_TABLE_URL = "https://www.jb.man.ac.uk/pulsar/glitches/gTable.html"
GLITCH_FALLBACK_URL = "https://www.jb.man.ac.uk/pulsar/glitches.html"

# ── Column descriptions for README schema table ─────────────────────
COLUMN_DESCRIPTIONS = {
    "jname": "Pulsar J2000 designation (e.g. J0534+2200 = Crab, J0835-4510 = Vela); format encodes position in right ascension and declination",
    "bname": "Pulsar B1950 designation (e.g. B0531+21 = Crab, B0833-45 = Vela); older naming convention, not all pulsars have a B-name",
    "n_glitches": "Total number of glitches recorded from this pulsar in the catalog; Vela-like pulsars glitch most frequently (~every 2-3 years)",
    "epoch_mjd": "Glitch epoch in Modified Julian Date (MJD = JD - 2400000.5); MJD 40000 ~ 1968, MJD 60000 ~ 2023",
    "epoch_mjd_err": "1-sigma uncertainty on glitch epoch in days; typically days to weeks depending on timing cadence",
    "epoch_datetime": "Glitch epoch as UTC datetime, derived from epoch_mjd; provided for convenience",
    "delta_nu_nu": "Fractional spin-up magnitude delta-nu/nu (dimensionless); typical range 1e-9 to 1e-5; large (Vela-class) glitches: ~1e-6; converted from catalog units of 1e-9",
    "delta_nu_nu_err": "1-sigma uncertainty on delta_nu_nu (dimensionless)",
    "delta_nudot_nudot": "Fractional change in spin-down rate delta-nudot/nudot (dimensionless) after the glitch; typically negative (spin-down rate increases); converted from catalog units of 1e-3",
    "delta_nudot_nudot_err": "1-sigma uncertainty on delta_nudot_nudot (dimensionless)",
    "is_large_glitch": "True if delta_nu_nu > 1e-6 (giant/Vela-class glitch involving large angular momentum transfer from the superfluid interior); False for smaller glitches; null if delta_nu_nu is unmeasured",
    "references": "Bibliographic references for this glitch event; may cite multiple papers if the glitch was reported or reanalysed in multiple studies",
}

# ── Dataset description ──────────────────────────────────────────────
DESCRIPTION = """\
Comprehensive catalog of pulsar glitch events from the Jodrell Bank Centre for \
Astrophysics. Pulsar glitches are sudden spin-up events in neutron stars, thought \
to arise from angular momentum transfer between the superfluid interior and the \
solid crust.

During a glitch, the rotation frequency of the pulsar increases abruptly, typically \
by a fractional amount delta_nu/nu ranging from ~1e-11 to ~1e-5. The largest \
glitches (delta_nu/nu > 1e-6) are called "giant glitches" and are characteristic \
of young pulsars like the Vela pulsar, which glitches roughly every 2-3 years.

The physics of pulsar glitches provides a unique window into neutron star interior \
structure. The leading model invokes a reservoir of angular momentum stored in \
quantised vortices pinned to the inner crust lattice. As the star spins down \
electromagnetically, a rotational lag develops between the superfluid and the crust. \
When the Magnus force on pinned vortices exceeds the pinning force, vortices unpin \
catastrophically and transfer angular momentum outward, producing the observed \
spin-up. The cumulative glitch activity constrains the fractional moment of inertia \
of the superfluid component, which in turn constrains the neutron star equation of \
state.
"""


def fetch_html(url: str, retries: int = 3) -> str:
    """Fetch HTML page with retries and exponential backoff."""
    for attempt in range(1, retries + 1):
        try:
            print(f"  Fetching {url} (attempt {attempt})...")
            resp = requests.get(url, timeout=60)
            resp.raise_for_status()
            return resp.text
        except requests.RequestException as e:
            print(f"  Attempt {attempt} failed: {e}")
            if attempt < retries:
                time.sleep(2 ** attempt)
    print(f"::error::Failed to fetch {url} after {retries} attempts")
    sys.exit(1)


def parse_glitch_table(html: str) -> pd.DataFrame:
    """Parse the HTML glitch table from Jodrell Bank.

    The table has an unusual structure:
    - Row 0-2: metadata (title, counts, citation note)
    - Row 3: column names (Pulsar name, J-name, No., MJD, +/-, dF/F, +/-, dF1/F1, +/-, References)
    - Row 4: units row (PSR, Glt's, days, days, 1e-9, 1e-9, 1e-3, 1e-3, ...)
    - Row 5+: data rows
    """
    soup = BeautifulSoup(html, "lxml")

    tables = soup.find_all("table")
    if not tables:
        return pd.DataFrame()

    # Pick the largest table
    best_table = max(tables, key=lambda t: len(t.find_all("tr")))
    all_rows = best_table.find_all("tr")

    if len(all_rows) < 10:
        return pd.DataFrame()

    # Find the header row -- it's the one containing "MJD" or "Pulsar"
    header_idx = None
    for i, tr in enumerate(all_rows[:10]):
        cells = [c.get_text(strip=True) for c in tr.find_all(["td", "th"])]
        if any("MJD" in c for c in cells):
            header_idx = i
            break

    if header_idx is None:
        header_idx = 3

    header_cells = [c.get_text(strip=True) for c in all_rows[header_idx].find_all(["td", "th"])]

    # Assign meaningful names based on the known structure
    col_names = []
    for i, h in enumerate(header_cells):
        if "pulsar" in h.lower() and "name" in h.lower():
            col_names.append("bname")
        elif h.lower() in ("j-name", "jname"):
            col_names.append("jname")
        elif h.lower() in ("no.", "no", "glt"):
            col_names.append("n_glitches")
        elif h == "MJD":
            col_names.append("epoch_mjd")
        elif h in ("dF/F", "df/f"):
            col_names.append("delta_nu_nu")
        elif h in ("dF1/F1", "df1/f1"):
            col_names.append("delta_nudot_nudot")
        elif h.lower() in ("ref", "refs", "reference", "references"):
            col_names.append("references")
        elif h == "+/-" or h == "\u00b1":
            if col_names and col_names[-1] == "epoch_mjd":
                col_names.append("epoch_mjd_err")
            elif col_names and col_names[-1] == "delta_nu_nu":
                col_names.append("delta_nu_nu_err")
            elif col_names and col_names[-1] == "delta_nudot_nudot":
                col_names.append("delta_nudot_nudot_err")
            else:
                col_names.append(f"err_{i}")
        elif h == "":
            col_names.append(f"_empty_{i}")
        else:
            col_names.append(re.sub(r"[^a-zA-Z0-9]+", "_", h).strip("_").lower())

    n_cols = len(col_names)

    # Parse data rows (skip header + units row)
    data_start = header_idx + 2
    data_rows = []
    for tr in all_rows[data_start:]:
        cells = [c.get_text(strip=True) for c in tr.find_all(["td", "th"])]
        if len(cells) != n_cols:
            continue
        if not any(c.strip() for c in cells[1:6]):
            continue
        data_rows.append(cells)

    if not data_rows:
        return pd.DataFrame()

    df = pd.DataFrame(data_rows, columns=col_names)

    # Drop empty placeholder columns
    df = df.loc[:, ~df.columns.str.startswith("_empty_")]

    print(f"  Parsed {len(df):,} rows, {len(df.columns)} columns from HTML table")
    return df


def normalise_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Normalise column names to snake_case and standardise known fields."""
    rename_map = {}
    for col in df.columns:
        lower = col.strip().lower()
        if lower in ("jname", "j-name", "psr jname", "psr j-name", "pulsar jname"):
            rename_map[col] = "jname"
        elif lower in ("bname", "b-name", "psr bname", "psr b-name", "pulsar bname", "name"):
            rename_map[col] = "bname"
        elif "epoch" in lower or lower in ("mjd", "glitch epoch", "glitch epoch (mjd)"):
            rename_map[col] = "epoch_mjd"
        elif "nu/nu" in lower.replace(" ", "") or "delta_nu/nu" in lower.replace(" ", "") \
                or "dnu/nu" in lower.replace(" ", "") or "deltanu/nu" in lower.replace(" ", ""):
            if "dot" not in lower:
                rename_map[col] = "delta_nu_nu"
            else:
                rename_map[col] = "delta_nudot_nudot"
        elif "nudot" in lower.replace(" ", "") or "nu_dot" in lower:
            rename_map[col] = "delta_nudot_nudot"
        elif lower in ("ref", "refs", "reference", "references"):
            rename_map[col] = "references"

    df = df.rename(columns=rename_map)

    clean = {}
    for col in df.columns:
        if col in rename_map.values():
            clean[col] = col
        else:
            s = re.sub(r"[^a-zA-Z0-9]+", "_", col.strip()).strip("_").lower()
            clean[col] = s if s else col
    df = df.rename(columns=clean)

    return df


def fetch_catalog() -> pd.DataFrame:
    """Fetch and parse the Jodrell Bank Pulsar Glitch Catalogue."""
    print("Fetching Jodrell Bank Glitch Catalogue (gTable.html)...")
    html = fetch_html(GLITCH_TABLE_URL)
    df = parse_glitch_table(html)

    if len(df) >= 100:
        return df

    print("Primary table too small or failed, trying fallback page...")
    html = fetch_html(GLITCH_FALLBACK_URL)
    df = parse_glitch_table(html)

    if len(df) >= 100:
        return df

    print(f"::error::Could not parse enough glitch data (got {len(df)} rows)")
    sys.exit(1)


def main():
    df = fetch_catalog()

    # Normalise if needed
    if "epoch_mjd" not in df.columns:
        df = normalise_columns(df)

    # Clean string columns
    for col in df.columns:
        if df[col].dtype == object:
            df[col] = df[col].astype(str).str.strip().replace(
                {"": pd.NA, "None": pd.NA, "nan": pd.NA, "null": pd.NA,
                 "-": pd.NA, "--": pd.NA, "---": pd.NA}
            )

    # Numeric coercion
    numeric_cols = ["epoch_mjd", "epoch_mjd_err", "delta_nu_nu", "delta_nu_nu_err",
                    "delta_nudot_nudot", "delta_nudot_nudot_err", "n_glitches"]
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # Scale: table values are in units of 1e-9 (dF/F) and 1e-3 (dF1/F1)
    for col in ["delta_nu_nu", "delta_nu_nu_err"]:
        if col in df.columns:
            df[col] = df[col] * 1e-9
    for col in ["delta_nudot_nudot", "delta_nudot_nudot_err"]:
        if col in df.columns:
            df[col] = df[col] * 1e-3

    # Convert MJD epoch to datetime
    if "epoch_mjd" in df.columns:
        mjd_epoch = pd.Timestamp("1858-11-17")
        df["epoch_datetime"] = mjd_epoch + pd.to_timedelta(df["epoch_mjd"], unit="D")

    # Derived column: is_large_glitch (giant glitches typical of Vela-like pulsars)
    if "delta_nu_nu" in df.columns:
        df["is_large_glitch"] = df["delta_nu_nu"].apply(
            lambda x: True if pd.notna(x) and x > 1e-6 else (False if pd.notna(x) else None)
        )

    # Sort by epoch descending
    if "epoch_mjd" in df.columns:
        df = df.sort_values("epoch_mjd", ascending=False).reset_index(drop=True)

    # Keep only described columns
    df = df[[c for c in df.columns if c in COLUMN_DESCRIPTIONS]]

    # ── Domain-specific stats for README ─────────────────────────────
    n_total = len(df)
    name_col = "jname" if "jname" in df.columns else "bname" if "bname" in df.columns else None
    n_pulsars = df[name_col].nunique() if name_col else 0
    n_large = int(df["is_large_glitch"].sum()) if "is_large_glitch" in df.columns else 0

    # Largest glitch
    if "delta_nu_nu" in df.columns:
        largest_idx = df["delta_nu_nu"].idxmax()
        largest_size = df.loc[largest_idx, "delta_nu_nu"] if pd.notna(largest_idx) else 0
        largest_pulsar = df.loc[largest_idx, name_col] if name_col and pd.notna(largest_idx) else "N/A"
    else:
        largest_size = 0
        largest_pulsar = "N/A"

    # Most frequently glitching pulsar
    if name_col:
        glitch_counts = df[name_col].value_counts()
        most_active = glitch_counts.index[0] if len(glitch_counts) > 0 else "N/A"
        most_active_count = int(glitch_counts.iloc[0]) if len(glitch_counts) > 0 else 0
    else:
        most_active = "N/A"
        most_active_count = 0

    quick_stats = f"""\
- **{n_total:,}** glitch events
- **{n_pulsars:,}** unique pulsars
- **{n_large:,}** large/giant glitches (delta_nu/nu > 1e-6)
- Largest glitch: **{largest_pulsar}** (delta_nu/nu = {largest_size:.2e})
- Most frequently glitching pulsar: **{most_active}** ({most_active_count} glitches)"""

    usage = f"""\
```python
from datasets import load_dataset

ds = load_dataset("juliensimon/pulsar-glitch-catalog", split="train")
df = ds.to_pandas()

# Glitch size distribution
import matplotlib.pyplot as plt
sizes = df["delta_nu_nu"].dropna()
sizes[sizes > 0].hist(bins=50, log=True)
plt.xlabel("delta_nu/nu")
plt.ylabel("Count")
plt.title("Pulsar Glitch Size Distribution")
plt.show()

# Most glitching pulsars
top = df.groupby("{name_col or 'jname'}").size().sort_values(ascending=False).head(10)
print(top)

# Giant glitches only
giants = df[df["is_large_glitch"] == True]
print(f"{{len(giants):,}} giant glitches")
```"""

    # Build expected/critical columns
    expected = []
    if name_col:
        expected.append(name_col)
    for c in ["epoch_mjd", "delta_nu_nu"]:
        if c in df.columns:
            expected.append(c)
    critical = [c for c in [name_col, "epoch_mjd"] if c and c in df.columns]

    with Pipeline(
        repo=HF_REPO,
        pretty_name="Jodrell Bank Pulsar Glitch Catalogue",
        description=DESCRIPTION,
        tags=["space", "pulsar", "glitch", "neutron-star", "astronomy",
              "jodrell-bank", "radio", "open-data", "tabular-data", "parquet"],
        source_url="https://www.jb.man.ac.uk/pulsar/glitches.html",
        task_categories=["tabular-classification"],
        collection_url="https://huggingface.co/collections/juliensimon/astronomy-datasets-69c24caf2f17e36128946743",
        banner={
            "url": "https://images-assets.nasa.gov/image/PIA21085/PIA21085~small.jpg",
            "alt": "Artist concept of a pulsar — a rapidly spinning neutron star emitting beams of radiation",
            "credit": "NASA/JPL-Caltech",
        },
        related_datasets=[
            "juliensimon/pulsar-catalog",
            "juliensimon/mcgill-magnetar-catalog",
            "juliensimon/gravitational-wave-events",
            "juliensimon/supernova-remnants",
        ],
    ) as p:
        df = p.clean(
            df,
            numeric=[
                "epoch_mjd", "epoch_mjd_err",
                "delta_nu_nu", "delta_nu_nu_err",
                "delta_nudot_nudot", "delta_nudot_nudot_err",
                "n_glitches",
            ],
        )
        p.publish(
            df,
            filename="pulsar_glitches.parquet",
            min_rows=400,
            expected_columns=expected or ["epoch_mjd"],
            critical_columns=critical or None,
            column_descriptions=COLUMN_DESCRIPTIONS,
            quick_stats=quick_stats,
            usage=usage,
            commit_message=f"Update pulsar glitch catalog: {n_total:,} glitches across {n_pulsars:,} pulsars",
        )
    print("Done.")


if __name__ == "__main__":
    main()
