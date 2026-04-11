#!/usr/bin/env python3
"""Fetch Mars ChemCam MOC oxide compositions from PDS and upload to HF.

Source: PDS Geosciences Node — MSL ChemCam LIBS RDR
Major Oxide Compositions (MOC) derived using PLS+ICA multivariate model.
"""

import io
import re
import time

import pandas as pd
import requests

from hf_dataset_utils import Pipeline

BASE_URL = (
    "https://pds-geosciences.wustl.edu"
    "/msl/msl-m-chemcam-libs-4_5-rdr-v1/mslccm_1xxx/data/moc/"
)
HF_REPO = "juliensimon/mars-chemcam-compositions"

# All known MOC CSV files, ordered by sol range
CSV_FILES = [
    "moc_0000_0089.csv", "moc_0090_0179.csv", "moc_0180_0269.csv",
    "moc_0270_0359.csv", "moc_0360_0449.csv", "moc_0450_0583.csv",
    "moc_0584_0707.csv", "moc_0708_0804.csv", "moc_0805_0938.csv",
    "moc_0939_1062.csv", "moc_1063_1159.csv", "moc_1160_1293.csv",
    "moc_1294_1417.csv", "moc_1418_1514.csv", "moc_1515_1648.csv",
    "moc_1649_1772.csv", "moc_1773_1869.csv", "moc_1870_2003.csv",
    "moc_2004_2127.csv", "moc_2128_2224.csv", "moc_2225_2358.csv",
    "moc_2359_2482.csv", "moc_2483_2579.csv", "moc_2580_2713.csv",
    "moc_2714_2837.csv", "moc_2838_2934.csv", "moc_2935_3068.csv",
    "moc_3069_3192.csv", "moc_3193_3289.csv", "moc_3290_3423.csv",
    "moc_3424_3547.csv", "moc_3548_3644.csv", "moc_3645_3778.csv",
    "moc_3779_3902.csv", "moc_3903_3999.csv", "moc_4000_4133.csv",
    "moc_4134_4257.csv", "moc_4258_4354.csv", "moc_4355_4488.csv",
    "moc_4489_4612.csv",
]

OXIDES = ["SiO2", "TiO2", "Al2O3", "FeOT", "MgO", "CaO", "Na2O", "K2O", "MnO"]

# Raw header: File, Target, SiO2, +/-, SiO2 RMSEP, SiO2_shots_stdev, ...
_RAW_NAMES = ["file", "target"]
for _ox in OXIDES:
    _lo = _ox.lower()
    _RAW_NAMES += [_lo, f"{_lo}_sep", f"{_lo}_rmsep", f"{_lo}_shots_stdev"]
_RAW_NAMES += ["sum_of_oxides", "distance_m", "laser_power", "spectrum_total"]

_SEP_COLS = [f"{ox.lower()}_sep" for ox in OXIDES]

# ── Column descriptions ─────────────────────────────────────────────
COLUMN_DESCRIPTIONS = {
    "file": "PDS spectrum filename (encodes sol, sequence, shot number)",
    "target": "Rock or soil target name assigned by the mission team (e.g. 'Jake_M', 'Bathurst_Inlet'); each target receives ~30 laser shots",
    "sio2": "Silicon dioxide weight percent (wt%); Martian basalt typically 45-55 wt%, felsic outliers >60 wt%",
    "sio2_rmsep": "SiO2 root-mean-square error of prediction (wt%) from the PLS+ICA calibration model",
    "sio2_shots_stdev": "SiO2 standard deviation across individual laser shots within this analysis point",
    "tio2": "Titanium dioxide weight percent (wt%); typically 0.5-2 wt% in Martian basalts",
    "tio2_rmsep": "TiO2 RMSEP from calibration model (wt%)",
    "tio2_shots_stdev": "TiO2 shot-to-shot standard deviation (wt%)",
    "al2o3": "Aluminum oxide weight percent (wt%); typically 8-15 wt%, higher in evolved/felsic rocks",
    "al2o3_rmsep": "Al2O3 RMSEP from calibration model (wt%)",
    "al2o3_shots_stdev": "Al2O3 shot-to-shot standard deviation (wt%)",
    "feot": "Total iron reported as FeO weight percent (wt%); typically 15-25 wt% in Martian basalts",
    "feot_rmsep": "FeOT RMSEP from calibration model (wt%)",
    "feot_shots_stdev": "FeOT shot-to-shot standard deviation (wt%)",
    "mgo": "Magnesium oxide weight percent (wt%); typically 5-15 wt% in mafic compositions",
    "mgo_rmsep": "MgO RMSEP from calibration model (wt%)",
    "mgo_shots_stdev": "MgO shot-to-shot standard deviation (wt%)",
    "cao": "Calcium oxide weight percent (wt%); typically 5-12 wt%; high values indicate calcium-rich minerals",
    "cao_rmsep": "CaO RMSEP from calibration model (wt%)",
    "cao_shots_stdev": "CaO shot-to-shot standard deviation (wt%)",
    "na2o": "Sodium oxide weight percent (wt%); typically 1-4 wt%; high values indicate alkali-rich rocks",
    "na2o_rmsep": "Na2O RMSEP from calibration model (wt%)",
    "na2o_shots_stdev": "Na2O shot-to-shot standard deviation (wt%)",
    "k2o": "Potassium oxide weight percent (wt%); typically 0.2-1.5 wt%; enriched in some evolved rocks",
    "k2o_rmsep": "K2O RMSEP from calibration model (wt%)",
    "k2o_shots_stdev": "K2O shot-to-shot standard deviation (wt%)",
    "mno": "Manganese oxide weight percent (wt%); typically <0.5 wt%; high values indicate oxidizing aqueous conditions",
    "mno_rmsep": "MnO RMSEP from calibration model (wt%)",
    "mno_shots_stdev": "MnO shot-to-shot standard deviation (wt%)",
    "sum_of_oxides": "Sum of all nine major oxide weight percents; should total ~100 wt% for unaltered rock",
    "distance_m": "Distance from ChemCam to target in meters; range 1.5-7 m",
    "laser_power": "Laser pulse energy setting used for this analysis point (mJ)",
    "spectrum_total": "Sum of all spectral channel intensities (arbitrary units); quality indicator for the LIBS plasma",
    "sol_range_min": "Minimum sol number in the source MOC data file; Curiosity sol 0 = Aug 6 2012",
    "sol_range_max": "Maximum sol number in the source MOC data file; each ~1.0275 Earth days",
}

# ── Dataset description ──────────────────────────────────────────────
DESCRIPTION = """\
Major oxide compositions of Mars surface rock and soil targets analyzed by the \
ChemCam LIBS instrument on the Curiosity rover, from the PDS Geosciences Node.

ChemCam fires a focused laser pulse at rock and soil targets up to ~7 meters \
away, creating a plasma whose emission spectrum reveals elemental composition. \
The Major Oxide Compositions (MOC) data product provides predicted weight \
percentages for nine major oxides (SiO2, TiO2, Al2O3, FeOT, MgO, CaO, \
Na2O, K2O, MnO) derived from the LIBS spectra using a combined PLS+ICA \
multivariate model.

Each row represents a single LIBS analysis point. Multiple points are \
typically measured per target to characterize compositional variability. \
Uncertainty estimates (RMSEP and shot-to-shot standard deviation) are \
provided for each oxide.

Laser-Induced Breakdown Spectroscopy (LIBS) is a technique where a focused pulsed \
laser ablates a small amount of material from a target surface, generating a \
high-temperature plasma whose optical emission lines reveal the elemental composition. \
ChemCam was the first LIBS instrument deployed on another planet and has been operating \
on Curiosity since its landing in Gale Crater in August 2012. The ability to analyze \
rocks and soils remotely has dramatically increased the pace of geochemical exploration, \
enabling thousands of analyses across Curiosity's multi-kilometer traverse from the \
crater floor up through the sedimentary strata of Mount Sharp (Aeolis Mons).

The major oxide compositions provide a window into the igneous, sedimentary, and \
alteration history of the Martian crust. The mean SiO2 content of typical Martian \
basaltic targets falls near 45-50 wt%, consistent with tholeiitic basalt. However, \
ChemCam has also identified unexpected lithologies including high-silica compositions \
(>60 wt% SiO2), high-manganese-oxide coatings suggesting oxidizing aqueous conditions, \
and alkali-rich compositions with no direct terrestrial analog.
"""


def parse_sol_range(filename: str) -> tuple[int, int]:
    """Extract (sol_min, sol_max) from a filename like moc_0000_0089.csv."""
    m = re.match(r"moc_(\d+)_(\d+)\.csv", filename)
    if not m:
        raise ValueError(f"Cannot parse sol range from {filename}")
    return int(m.group(1)), int(m.group(2))


def download_csv(filename: str) -> pd.DataFrame:
    """Download one MOC CSV, skip metadata rows, return DataFrame."""
    url = BASE_URL + filename
    resp = requests.get(url, timeout=60)
    resp.raise_for_status()

    lines = resp.text.splitlines()
    header_idx = None
    for i, line in enumerate(lines):
        if line.startswith("File,Target,SiO2"):
            header_idx = i
            break
    if header_idx is None:
        raise ValueError(f"Could not find header row in {filename}")

    data_text = "\n".join(lines[header_idx + 1:])
    if not data_text.strip():
        return pd.DataFrame(columns=[c for c in _RAW_NAMES if c not in _SEP_COLS])

    df = pd.read_csv(
        io.StringIO(data_text),
        header=None,
        names=_RAW_NAMES,
        na_values=["", " "],
    )
    df = df.drop(columns=_SEP_COLS, errors="ignore")

    sol_min, sol_max = parse_sol_range(filename)
    df["sol_range_min"] = sol_min
    df["sol_range_max"] = sol_max

    return df


def main():
    print("Fetching ChemCam MOC oxide compositions from PDS Geosciences...")
    print(f"  {len(CSV_FILES)} CSV files to download")

    frames = []
    for i, csv_file in enumerate(CSV_FILES):
        print(f"  [{i + 1}/{len(CSV_FILES)}] {csv_file}...", end=" ", flush=True)
        df = download_csv(csv_file)
        print(f"{len(df)} rows")
        frames.append(df)
        if i < len(CSV_FILES) - 1:
            time.sleep(0.5)

    df = pd.concat(frames, ignore_index=True)
    print(f"  Total: {len(df):,} rows")

    # Drop completely empty rows
    df = df.dropna(subset=["target"], how="all").reset_index(drop=True)

    # Sort by sol range then target name
    df = df.sort_values(["sol_range_min", "target", "file"]).reset_index(drop=True)

    # Keep only described columns
    df = df[[c for c in df.columns if c in COLUMN_DESCRIPTIONS]]

    # ── Domain-specific stats ────────────────────────────────────────
    n_targets = df["target"].nunique()
    sol_min = int(df["sol_range_min"].min())
    sol_max = int(df["sol_range_max"].max())
    sio2_mean = df["sio2"].mean()
    feot_mean = df["feot"].mean()

    quick_stats = f"""\
- **{len(df):,}** LIBS point analyses across **{n_targets:,}** targets
- Sols **{sol_min}** to **{sol_max}** of Curiosity's traverse
- Mean SiO2: **{sio2_mean:.1f} wt%** | Mean FeOT: **{feot_mean:.1f} wt%**"""

    usage = """\
```python
from datasets import load_dataset

ds = load_dataset("juliensimon/mars-chemcam-compositions", split="train")
df = ds.to_pandas()

# Average oxide composition per target
target_avg = df.groupby("target")[
    ["sio2", "tio2", "al2o3", "feot", "mgo", "cao", "na2o", "k2o"]
].mean()

# High-silica targets (possible felsic rocks)
felsic = target_avg[target_avg["sio2"] > 60].sort_values("sio2", ascending=False)

# Composition variability within a single target
import matplotlib.pyplot as plt
for oxide in ["sio2", "feot", "mgo"]:
    plt.hist(df[oxide].dropna(), bins=50, alpha=0.6, label=oxide.upper())
plt.xlabel("Weight %")
plt.ylabel("Count")
plt.legend()
plt.title("ChemCam Oxide Distributions")
plt.show()
```"""

    # Build float columns list for cleaning
    float_cols = []
    for oxide in OXIDES:
        o = oxide.lower()
        float_cols += [o, f"{o}_rmsep", f"{o}_shots_stdev"]
    float_cols += ["sum_of_oxides", "distance_m"]

    with Pipeline(
        repo=HF_REPO,
        pretty_name="Mars ChemCam LIBS Oxide Compositions",
        description=DESCRIPTION,
        tags=["space", "mars", "curiosity", "chemcam", "geochemistry", "nasa",
              "planetary-science", "open-data", "tabular-data", "parquet"],
        source_url="https://pds-geosciences.wustl.edu/msl/msl-m-chemcam-libs-4_5-rdr-v1/mslccm_1xxx/data/moc/",
        task_categories=["tabular-classification", "tabular-regression"],
        collection_url="https://huggingface.co/collections/juliensimon/space-probe-and-mission-datasets-69c3fe82d410a42b1e313167",
        banner={
            "url": "https://images-assets.nasa.gov/image/PIA19808/PIA19808~small.jpg",
            "alt": "NASA's Curiosity rover on the surface of Mars",
            "credit": "NASA/JPL-Caltech/MSSS",
        },
        related_datasets=[
            "juliensimon/mars-craters-robbins",
            "juliensimon/neo-close-approaches",
            "juliensimon/jpl-small-body-database",
        ],
    ) as p:
        df = p.clean(
            df,
            numeric=float_cols,
        )
        p.publish(
            df,
            filename="mars_chemcam_compositions.parquet",
            min_rows=3_000,
            expected_columns=["file", "target", "sol_range_min", "sol_range_max",
                              "sum_of_oxides", "distance_m"] + [o.lower() for o in OXIDES],
            critical_columns=[o.lower() for o in OXIDES],
            max_null_pct=0.05,
            column_descriptions=COLUMN_DESCRIPTIONS,
            quick_stats=quick_stats,
            usage=usage,
            commit_message=f"Update Mars ChemCam compositions: {len(df):,} records",
        )
    print("Done.")


if __name__ == "__main__":
    main()
