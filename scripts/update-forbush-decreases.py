#!/usr/bin/env python3
"""Fetch Forbush decrease events from IZMIRAN FEID catalog and upload to HF.

Source: IZMIRAN Forbush Effects and Interplanetary Disturbances (FEID)
database — comprehensive catalog of Forbush decrease events with solar
wind, IMF, CME, and geomagnetic parameters.
"""

import io
import sys
import zipfile
from pathlib import Path

import pandas as pd
import requests

from hf_dataset_utils import Pipeline

FEID_URL = "http://spaceweather.izmiran.ru/dbs/fds/events.zip"
HF_REPO = "juliensimon/forbush-decreases"

# Null sentinel values used by IZMIRAN
NULL_SENTINELS = {"-999", "-999.0", "-999.9", "-99.9", "-9.999", "-9.99", "-9", "None", "none", ""}

# Key columns to keep (from the ~108 available). Grouped by category.
KEEP_COLUMNS = {
    # Event identification
    "Date": "date",
    "Time": "time",
    "Otype": "onset_type",
    "Qs": "quality",
    # Solar source
    "Sdate": "solar_source_date",
    "Stime": "solar_source_time",
    "Stype": "solar_source_type",
    # Solar wind
    "Vsp": "solar_wind_speed_onset_km_s",
    "Vmean": "solar_wind_speed_mean_km_s",
    "Vmax": "solar_wind_speed_max_km_s",
    # IMF
    "Bmax": "imf_b_max_nt",
    "Bzmin": "imf_bz_min_nt",
    # Forbush decrease magnitude and timing
    "Magn": "fd_magnitude_pct",
    "MagnM": "fd_magnitude_corrected_pct",
    "Tmin": "fd_min_time_hours",
    "Dmin": "fd_min_depth_pct",
    # Spectral
    "GammaM": "spectral_index_max",
    "GammaD": "spectral_index_min",
    # Geomagnetic
    "Kpmax": "kp_max",
    "Apmax": "ap_max",
    "Dstmin": "dst_min_nt",
    # CME
    "CMEdate": "cme_date",
    "CMEtime": "cme_time",
    "CMEwidth": "cme_width_deg",
    "CMEangle": "cme_angle_deg",
    # Flags
    "GLE": "ground_level_enhancement",
    "SSN": "sunspot_number",
}

# ── Column descriptions for README schema table ─────────────────────
COLUMN_DESCRIPTIONS = {
    "datetime_utc": "Event onset time in UTC, constructed from the IZMIRAN Date and Time fields; marks the beginning of the cosmic ray intensity decrease as observed by the neutron monitor network",
    "onset_type": "Onset type code: 1=shock+SSC (sudden storm commencement), 2=interplanetary shock without SSC, 3=weak SSC, 9=no shock detected; characterizes how the interplanetary disturbance arrived at Earth",
    "quality": "Data quality rating from 1 (poor) to 5 (excellent); reflects the clarity of the Forbush decrease signature in neutron monitor data and the completeness of associated measurements",
    "solar_source_datetime_utc": "UTC timestamp of the identified solar source event (flare or eruption) that produced the interplanetary disturbance causing this Forbush decrease",
    "solar_source_type": "Solar source type code identifying the kind of solar event (flare, filament eruption, etc.) that produced the interplanetary disturbance",
    "solar_wind_speed_onset_km_s": "Solar wind bulk speed at the onset of the Forbush decrease (km/s); typical quiet values ~400 km/s, disturbed values 500-1000+ km/s",
    "solar_wind_speed_mean_km_s": "Mean solar wind speed during the Forbush decrease event (km/s); averaged over the decrease and early recovery phase",
    "solar_wind_speed_max_km_s": "Maximum solar wind speed recorded during the event (km/s); peaks often coincide with the passage of the ICME sheath or ejecta",
    "imf_b_max_nt": "Maximum interplanetary magnetic field magnitude during the event (nT); enhanced B inside ICMEs is the primary cause of cosmic ray shielding",
    "imf_bz_min_nt": "Minimum IMF Bz component during the event (nT, GSM coordinates); large negative Bz drives geomagnetic storms via dayside reconnection",
    "fd_magnitude_pct": "Forbush decrease magnitude at 10 GV rigidity (%), measuring the peak reduction in galactic cosmic ray intensity; typical values 1-10%, extreme events >15%",
    "fd_magnitude_corrected_pct": "Magnetosphere-corrected Forbush decrease magnitude (%); removes the contribution of geomagnetic cutoff changes to isolate the interplanetary modulation",
    "fd_min_time_hours": "Time from onset to minimum cosmic ray flux (hours); characterizes the speed of the decrease phase, typically 6-24 hours",
    "fd_min_depth_pct": "Minimum depth of cosmic ray decrease (%); the deepest point of the Forbush decrease profile",
    "spectral_index_max": "Maximum spectral index (gamma) of the Forbush decrease; describes the rigidity dependence of the cosmic ray modulation during the decrease phase",
    "spectral_index_min": "Minimum spectral index during the recovery phase; the rigidity spectrum typically softens as cosmic rays recover",
    "kp_max": "Maximum Kp geomagnetic index during the event (0-9 scale); Kp >= 5 indicates a geomagnetic storm, often concurrent with large Forbush decreases",
    "ap_max": "Maximum Ap geomagnetic index during the event; linearized version of Kp providing a more physical measure of geomagnetic disturbance",
    "dst_min_nt": "Minimum Dst index during the event (nT); Dst < -50 nT indicates a geomagnetic storm, < -100 nT an intense storm; measures ring current enhancement",
    "cme_datetime_utc": "UTC timestamp of the associated coronal mass ejection (CME) as observed by coronagraphs (typically SOHO/LASCO); null if no CME association was identified",
    "cme_width_deg": "Angular width of the associated CME (degrees); halo CMEs (360 deg) are most likely to impact Earth and produce large Forbush decreases",
    "cme_angle_deg": "Position angle of the associated CME (degrees from solar north); indicates the direction of initial CME propagation in the plane of the sky",
    "ground_level_enhancement": "Ground-level enhancement (GLE) flag; values >0 indicate that this Forbush decrease coincided with a GLE — a rare event where solar energetic particles are detected at ground level",
    "sunspot_number": "Daily international sunspot number at the time of the event; proxy for overall solar activity level, correlates with Forbush decrease frequency over the solar cycle",
}

# ── Dataset description ──────────────────────────────────────────────
DESCRIPTION = """\
A comprehensive catalog of Forbush decrease events from the IZMIRAN FEID \
(Forbush Effects and Interplanetary Disturbances) database. Each event includes \
solar wind parameters, interplanetary magnetic field measurements, Forbush \
decrease magnitudes, geomagnetic indices, and associated CME data.

A **Forbush decrease** is a rapid reduction in the galactic cosmic ray intensity \
observed at Earth, caused by the passage of an interplanetary coronal mass ejection \
(ICME) or co-rotating interaction region (CIR) through the heliosphere. The enhanced \
magnetic field within these structures acts as a shield, temporarily deflecting \
galactic cosmic rays away from the inner solar system. Typical decreases range from \
1-10% of the ambient cosmic ray flux, with the largest events exceeding 15%.

Forbush decreases are measured by the worldwide network of ground-based neutron \
monitors at ~10 GV rigidity. The FEID catalog cross-references each cosmic ray \
decrease with its solar source (flare, CME), the interplanetary disturbance \
parameters (solar wind speed, IMF magnitude, Bz component), and the geomagnetic \
response (Kp, Ap, Dst indices). This multi-parameter approach makes the FEID one \
of the most richly annotated Forbush decrease catalogs available.

These events are important for: (1) understanding cosmic ray modulation by solar \
activity, (2) forecasting radiation environment changes relevant to aviation and \
spaceflight, and (3) studying the propagation and geo-effectiveness of CMEs and \
ICMEs through the heliosphere.
"""


def parse_event_file(text):
    """Parse a single IZMIRAN FEID event file (tab-separated key-value pairs)."""
    record = {}
    for line in text.strip().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split("\t", 1)
        if len(parts) == 2:
            key, value = parts[0].strip(), parts[1].strip()
            if value in NULL_SENTINELS:
                value = None
            record[key] = value
    return record


def main():
    print("Fetching Forbush decrease catalog from IZMIRAN FEID...")
    resp = requests.get(FEID_URL, timeout=120, headers={"User-Agent": "space-datasets/1.0"})
    resp.raise_for_status()
    print(f"  Downloaded {len(resp.content) / 1024 / 1024:.1f} MB zip")

    # Parse all event files from the zip
    records = []
    with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
        txt_files = [n for n in zf.namelist() if n.endswith(".txt") and not n.startswith("__")]
        print(f"  {len(txt_files)} event files in archive")

        for fname in sorted(txt_files):
            try:
                text = zf.read(fname).decode("utf-8", errors="replace")
                record = parse_event_file(text)
                if record:
                    record["_filename"] = Path(fname).stem
                    records.append(record)
            except Exception as e:
                print(f"    Skipping {fname}: {e}")

    if not records:
        print("::error::No event files parsed")
        sys.exit(1)

    print(f"  Parsed {len(records):,} events")

    # Create DataFrame from all fields first
    df_full = pd.DataFrame(records)

    # Select and rename columns we want to keep
    available = {k: v for k, v in KEEP_COLUMNS.items() if k in df_full.columns}
    df = df_full[list(available.keys())].rename(columns=available)

    # Build datetime from date + time
    if "date" in df.columns and "time" in df.columns:
        df["datetime_utc"] = pd.to_datetime(
            df["date"].astype(str) + " " + df["time"].fillna("00:00").astype(str),
            errors="coerce",
        )
        df = df.drop(columns=["date", "time"])

    # Build CME datetime
    if "cme_date" in df.columns and "cme_time" in df.columns:
        df["cme_datetime_utc"] = pd.to_datetime(
            df["cme_date"].astype(str) + " " + df["cme_time"].fillna("00:00").astype(str),
            errors="coerce",
        )
        df = df.drop(columns=["cme_date", "cme_time"])

    # Build solar source datetime
    if "solar_source_date" in df.columns and "solar_source_time" in df.columns:
        df["solar_source_datetime_utc"] = pd.to_datetime(
            df["solar_source_date"].astype(str) + " " + df["solar_source_time"].fillna("00:00").astype(str),
            errors="coerce",
        )
        df = df.drop(columns=["solar_source_date", "solar_source_time"])

    # Sort by datetime and drop rows without it
    if "datetime_utc" in df.columns:
        df = df.sort_values("datetime_utc").reset_index(drop=True)
        n_before = len(df)
        df = df.dropna(subset=["datetime_utc"]).reset_index(drop=True)
        if n_before - len(df) > 0:
            print(f"  Dropped {n_before - len(df)} rows with invalid datetime")

    # Keep only described columns
    df = df[[c for c in df.columns if c in COLUMN_DESCRIPTIONS]]

    # ── Domain-specific stats for README ─────────────────────────────
    n_total = len(df)
    year_min = df["datetime_utc"].dt.year.min()
    year_max = df["datetime_utc"].dt.year.max()
    fd_mag_median = df["fd_magnitude_pct"].median() if "fd_magnitude_pct" in df.columns else None
    fd_mag_max = df["fd_magnitude_pct"].max() if "fd_magnitude_pct" in df.columns else None
    n_with_cme = int(df["cme_datetime_utc"].notna().sum()) if "cme_datetime_utc" in df.columns else 0
    n_with_dst = int(df["dst_min_nt"].notna().sum()) if "dst_min_nt" in df.columns else 0
    n_gle = int((df["ground_level_enhancement"] > 0).sum()) if "ground_level_enhancement" in df.columns else 0

    fd_stats = ""
    if fd_mag_median is not None:
        fd_stats = f"- Median FD magnitude: **{fd_mag_median:.1f}%**, maximum: **{fd_mag_max:.1f}%**\n"

    quick_stats = f"""\
- **{n_total:,}** Forbush decrease events ({year_min}--{year_max})
{fd_stats}- **{n_with_cme}** events with associated CME data
- **{n_with_dst}** events with Dst index measurements
- **{n_gle}** events coinciding with ground-level enhancements (GLEs)"""

    usage = """\
```python
from datasets import load_dataset

ds = load_dataset("juliensimon/forbush-decreases", split="train")
df = ds.to_pandas()

# FD magnitude distribution
import matplotlib.pyplot as plt
df["fd_magnitude_pct"].dropna().hist(bins=50)
plt.xlabel("Forbush Decrease Magnitude (%)")
plt.ylabel("Count")
plt.title("Distribution of Forbush Decrease Magnitudes")
plt.show()

# FD magnitude vs solar wind speed
valid = df.dropna(subset=["fd_magnitude_pct", "solar_wind_speed_max_km_s"])
plt.scatter(valid["solar_wind_speed_max_km_s"], valid["fd_magnitude_pct"], alpha=0.3, s=10)
plt.xlabel("Max Solar Wind Speed (km/s)")
plt.ylabel("FD Magnitude (%)")
plt.title("Forbush Decrease vs Solar Wind Speed")
plt.show()

# Annual event count (tracks solar cycle)
df["year"] = df["datetime_utc"].dt.year
df.groupby("year").size().plot(kind="bar", figsize=(14, 4))
plt.ylabel("Events per year")
plt.title("Forbush Decrease Events by Year")
plt.show()
```"""

    # Numeric columns for p.clean()
    numeric_cols = [
        "solar_wind_speed_onset_km_s", "solar_wind_speed_mean_km_s", "solar_wind_speed_max_km_s",
        "imf_b_max_nt", "imf_bz_min_nt",
        "fd_magnitude_pct", "fd_magnitude_corrected_pct", "fd_min_time_hours", "fd_min_depth_pct",
        "spectral_index_max", "spectral_index_min",
        "kp_max", "ap_max", "dst_min_nt",
        "cme_width_deg", "cme_angle_deg",
        "sunspot_number", "quality", "onset_type", "solar_source_type",
        "ground_level_enhancement",
    ]

    with Pipeline(
        repo=HF_REPO,
        pretty_name="Forbush Decrease Events (IZMIRAN FEID)",
        description=DESCRIPTION,
        tags=["space", "space-weather", "forbush-decrease", "cosmic-rays",
              "solar-wind", "cme", "geomagnetic", "izmiran",
              "open-data", "tabular-data", "parquet"],
        source_url="http://spaceweather.izmiran.ru/eng/dbs.html",
        task_categories=["tabular-regression", "time-series-forecasting"],
        collection_url="https://huggingface.co/collections/juliensimon/space-weather-datasets-69c24cae98f1666f2101ca70",
        banner={
            "url": "https://images-assets.nasa.gov/image/iss072e159172/iss072e159172~medium.jpg",
            "alt": "Aurora borealis blankets the Earth, seen from the ISS",
            "credit": "NASA",
        },
        related_datasets=[
            "juliensimon/neutron-monitor",
            "juliensimon/donki",
            "juliensimon/dst-index",
            "juliensimon/substorm-onsets",
        ],
    ) as p:
        df = p.clean(
            df,
            numeric=[c for c in numeric_cols if c in df.columns],
            drop_mostly_null_threshold=0.95,
        )
        p.publish(
            df,
            filename="forbush_decreases.parquet",
            min_rows=1_000,
            expected_columns=["datetime_utc"],
            critical_columns=["datetime_utc"],
            column_descriptions=COLUMN_DESCRIPTIONS,
            quick_stats=quick_stats,
            usage=usage,
            commit_message=f"Update Forbush decreases: {n_total:,} events",
        )
    print("Done.")


if __name__ == "__main__":
    main()
