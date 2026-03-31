#!/usr/bin/env python3
"""Fetch Gaia DR3 Young Stellar Objects catalog from ESA Gaia Archive and upload to HF.

YSO candidates are identified by joining gaiadr3.vari_classifier_result (best_class_name = 'YSO')
with gaiadr3.vari_summary (variability statistics) and gaiadr3.gaia_source (astrometry/photometry).
~79K sources total, paginated via TOP + source_id > last_id.
"""

import io
import os
import subprocess
import tempfile
import time
from pathlib import Path

import pandas as pd
import requests

from validate import check_dataset

GAIA_TAP = "https://gea.esac.esa.int/tap-server/tap/sync"
HF_REPO = "juliensimon/gaia-dr3-young-stellar-objects"
PAGE_SIZE = 50_000

# Columns to select from the three-way join
COLUMNS = """
c.source_id, c.best_class_name, c.best_class_score,
g.ra, g.dec, g.l, g.b,
g.parallax, g.parallax_error, g.pmra, g.pmdec,
g.phot_g_mean_mag, g.phot_bp_mean_mag, g.phot_rp_mean_mag,
s.mean_mag_g_fov, s.mean_mag_bp, s.mean_mag_rp,
s.median_mag_g_fov, s.median_mag_bp, s.median_mag_rp,
s.std_dev_mag_g_fov, s.std_dev_mag_bp, s.std_dev_mag_rp,
s.trimmed_range_mag_g_fov, s.trimmed_range_mag_bp, s.trimmed_range_mag_rp,
s.range_mag_g_fov, s.range_mag_bp, s.range_mag_rp,
s.min_mag_g_fov, s.max_mag_g_fov,
s.num_selected_g_fov, s.num_selected_bp, s.num_selected_rp,
s.skewness_mag_g_fov, s.kurtosis_mag_g_fov,
s.mad_mag_g_fov, s.abbe_mag_g_fov, s.iqr_mag_g_fov
""".strip()

FROM_CLAUSE = (
    "FROM gaiadr3.vari_classifier_result c "
    "JOIN gaiadr3.vari_summary s ON c.source_id = s.source_id "
    "JOIN gaiadr3.gaia_source g ON c.source_id = g.source_id"
)


def fetch_gaia_yso():
    """Fetch YSO candidates via paginated JOIN across classifier, summary, and source tables."""
    all_dfs = []
    last_id = 0
    page = 0
    while True:
        query = (
            f"SELECT TOP {PAGE_SIZE} {COLUMNS} "
            f"{FROM_CLAUSE} "
            f"WHERE c.best_class_name = 'YSO' AND c.source_id > {last_id} "
            f"ORDER BY c.source_id"
        )
        page += 1
        print(f"  Page {page}: fetching up to {PAGE_SIZE:,} rows (source_id > {last_id})...")
        resp = requests.post(GAIA_TAP, data={
            "REQUEST": "doQuery", "LANG": "ADQL", "FORMAT": "csv",
            "QUERY": query,
        }, timeout=600)
        resp.raise_for_status()
        df = pd.read_csv(io.StringIO(resp.text))
        if len(df) == 0:
            break
        all_dfs.append(df)
        last_id = int(df["source_id"].max())
        print(f"    got {len(df):,} rows (last source_id: {last_id})")
        if len(df) < PAGE_SIZE:
            break
        time.sleep(2)
    return pd.concat(all_dfs, ignore_index=True)


def main():
    print("Fetching Gaia DR3 Young Stellar Objects from ESA Gaia Archive...")
    df = fetch_gaia_yso()
    print(f"  {len(df):,} raw rows")

    # Convert object columns to numeric where appropriate
    for col in df.select_dtypes(include=["object"]).columns:
        if col == "best_class_name":
            continue
        converted = pd.to_numeric(df[col], errors="coerce")
        if converted.notna().sum() > 0.5 * df[col].notna().sum():
            df[col] = converted

    # Integer columns
    int_cols = ["num_selected_g_fov", "num_selected_bp", "num_selected_rp"]
    for col in int_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").astype("Int32")

    # Derived: BP-RP color index from catalog photometry
    if "phot_bp_mean_mag" in df.columns and "phot_rp_mean_mag" in df.columns:
        df["bp_rp"] = df["phot_bp_mean_mag"] - df["phot_rp_mean_mag"]

    # Sort by source_id
    if "source_id" in df.columns:
        df = df.sort_values("source_id").reset_index(drop=True)

    # Stats
    n_total = len(df)
    g_median = df["median_mag_g_fov"].median() if "median_mag_g_fov" in df.columns else float("nan")
    score_median = df["best_class_score"].median() if "best_class_score" in df.columns else float("nan")

    # Validate
    check_dataset(
        df,
        "gaia-yso",
        min_rows=50_000,
        expected_columns=["source_id", "best_class_name", "best_class_score", "ra", "dec",
                          "median_mag_g_fov", "parallax"],
        critical_columns=["source_id", "best_class_name"],
    )

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        data_dir = tmp / "data"
        data_dir.mkdir()

        out = data_dir / "gaia_dr3_young_stellar_objects.parquet"
        df.to_parquet(out, index=False, engine="pyarrow", compression="zstd")
        size_mb = out.stat().st_size / 1024 / 1024
        print(f"  {size_mb:.1f} MB parquet")

        (tmp / "README.md").write_text(f"""---
license: cc-by-4.0
pretty_name: "Gaia DR3 Young Stellar Objects"
language:
  - en
description: "Gaia DR3 young stellar object (YSO) candidates — {n_total:,} pre-main-sequence stars with classification scores, variability parameters, astrometry, and multi-band photometry from ESA Gaia mission."
task_categories:
  - tabular-classification
  - tabular-regression
tags:
  - space
  - gaia
  - yso
  - young-stars
  - star-formation
  - esa
  - astronomy
  - open-data
  - tabular-data
  - parquet
size_categories:
  - 10K<n<100K
configs:
  - config_name: default
    data_files:
      - split: train
        path: data/gaia_dr3_young_stellar_objects.parquet
    default: true
---

# Gaia DR3 Young Stellar Objects

*Part of the [Astronomy Datasets](https://huggingface.co/collections/juliensimon/astronomy-datasets-69c24caf2f17e36128946743) collection on Hugging Face.*

The Gaia DR3 young stellar object (YSO) catalog, containing **{n_total:,}** YSO candidates
identified by the ESA Gaia mission's variability classification pipeline. Each source includes
a YSO classification confidence score, variability statistics (amplitudes, standard deviations,
skewness, kurtosis), astrometry (positions, parallax, proper motions), and multi-band
photometry (G, BP, RP).

## Dataset description

Young stellar objects are pre-main-sequence stars still in the process of forming, often
surrounded by circumstellar disks and exhibiting irregular photometric variability. Gaia's
all-sky photometric survey identified these candidates through automated variability
classification in the `vari_classifier_result` table. The `best_class_score` field gives
the classifier's confidence for the YSO label (higher = more confident).

This dataset joins three Gaia DR3 tables:
- **`vari_classifier_result`** — YSO classification and confidence score
- **`vari_summary`** — variability statistics (mean/median magnitudes, amplitudes, scatter)
- **`gaia_source`** — astrometry (ra, dec, parallax, proper motion) and catalog photometry

Young stellar objects span a broad evolutionary sequence from deeply embedded protostars
(Class 0/I) still accreting from their natal envelopes, through classical T Tauri stars
(Class II) with optically thick circumstellar disks, to weak-lined T Tauri stars (Class III)
whose disks have largely dissipated. Their photometric variability arises from multiple
physical mechanisms operating simultaneously: hot spots at the base of magnetospheric
accretion columns produce periodic modulation tied to the stellar rotation period; variable
accretion rates cause irregular flickering on timescales of hours to weeks; disk warps and
orbiting dust structures create quasi-periodic extinction dips; and powerful magnetic
reconnection events drive flares with amplitudes of several magnitudes in extreme cases.

The Gaia variability classifier identifies YSO candidates primarily through their
characteristic aperiodic and semi-periodic brightness fluctuations, which differ statistically
from the variability signatures of eclipsing binaries, pulsating stars, and AGN. The
variability statistics in this catalog -- standard deviation, trimmed range, skewness,
kurtosis, and the Abbe value (a measure of smoothness) -- capture these distinctive patterns
and are particularly useful for separating accretion-dominated variability (typically
asymmetric, with negative skewness from fading events) from spot-dominated variability
(more symmetric and periodic).

Because Gaia operates at optical wavelengths, this catalog is most complete for the more
evolved, less embedded YSO populations (Class II and III) and is naturally biased against
the youngest, most heavily obscured protostars that are better detected at infrared and
submillimeter wavelengths. Nevertheless, the combination of precise Gaia astrometry
(parallaxes and proper motions) with the variability metrics makes this catalog uniquely
powerful for identifying co-moving groups of young stars, mapping the three-dimensional
structure of nearby star-forming regions, and studying the dependence of variability
properties on stellar age, mass, and disk evolutionary state.

## Key columns

| Column | Type | Description |
|--------|------|-------------|
| `source_id` | int64 | Gaia DR3 unique source identifier |
| `best_class_name` | string | Classification label (always "YSO" in this dataset) |
| `best_class_score` | float64 | Classification confidence score (0-1) |
| `ra` | float64 | Right ascension (deg, ICRS, epoch 2016.0) |
| `dec` | float64 | Declination (deg, ICRS, epoch 2016.0) |
| `l` | float64 | Galactic longitude (deg) |
| `b` | float64 | Galactic latitude (deg) |
| `parallax` | float64 | Parallax (mas) |
| `parallax_error` | float64 | Parallax uncertainty (mas) |
| `pmra` | float64 | Proper motion in RA (mas/yr) |
| `pmdec` | float64 | Proper motion in Dec (mas/yr) |
| `phot_g_mean_mag` | float64 | G-band mean magnitude (catalog) |
| `median_mag_g_fov` | float64 | Median G-band magnitude (variability) |
| `median_mag_bp` | float64 | Median BP-band magnitude (variability) |
| `median_mag_rp` | float64 | Median RP-band magnitude (variability) |
| `bp_rp` | float64 | BP-RP color index (derived) |
| `std_dev_mag_g_fov` | float64 | G-band magnitude standard deviation |
| `trimmed_range_mag_g_fov` | float64 | G-band variability amplitude |
| `skewness_mag_g_fov` | float64 | G-band magnitude skewness |
| `kurtosis_mag_g_fov` | float64 | G-band magnitude kurtosis |
| `num_selected_g_fov` | Int32 | Number of G-band observations used |

Full schema includes {len(df.columns)} columns with variability metrics and photometric parameters.

## Quick stats

- **{n_total:,}** YSO candidates
- Median G magnitude: {g_median:.2f}
- Median classification score: {score_median:.3f}

## Usage

```python
from datasets import load_dataset

ds = load_dataset("juliensimon/gaia-dr3-young-stellar-objects", split="train")
df = ds.to_pandas()

# Classification score distribution
print(df["best_class_score"].describe())

# High-confidence YSOs (score > 0.5)
confident = df[df["best_class_score"] > 0.5]
print(f"High-confidence YSOs: {{len(confident):,}}")

# Color-magnitude diagram
import matplotlib.pyplot as plt
plt.scatter(df["bp_rp"], df["phot_g_mean_mag"], s=1, alpha=0.3, c=df["best_class_score"], cmap="viridis")
plt.colorbar(label="Classification score")
plt.xlabel("BP - RP (mag)")
plt.ylabel("G (mag)")
plt.gca().invert_yaxis()
plt.title("Gaia DR3 YSO Color-Magnitude Diagram")
plt.show()
```

## Data source

Gaia Collaboration (2023), *Gaia Data Release 3: variability processing and analysis results.*
European Space Agency. Via ESA Gaia Archive — joined from `gaiadr3.vari_classifier_result`,
`gaiadr3.vari_summary`, and `gaiadr3.gaia_source`.

## Related datasets

- [Gaia DR3 Eclipsing Binaries](https://huggingface.co/datasets/juliensimon/gaia-dr3-eclipsing-binaries) — Gaia eclipsing binary candidates
- [Gaia DR3 Variable Star Summary](https://huggingface.co/datasets/juliensimon/gaia-dr3-variable-summary) — all Gaia variable star classifications

## Pipeline

Source code: [juliensimon/space-datasets](https://github.com/juliensimon/space-datasets)

## Support

If you find this dataset useful, please give it a ❤️ on the [dataset page](https://huggingface.co/datasets/juliensimon/gaia-dr3-young-stellar-objects) and share feedback in the Community tab! Also consider giving a ⭐️ to the [space-datasets](https://github.com/juliensimon/space-datasets) repo.

## Citation

```bibtex
@dataset{{gaia_dr3_young_stellar_objects,
  author = {{Simon, Julien}},
  title = {{Gaia DR3 Young Stellar Objects}},
  year = {{2026}},
  publisher = {{Hugging Face}},
  url = {{https://huggingface.co/datasets/juliensimon/gaia-dr3-young-stellar-objects}},
  note = {{Based on Gaia DR3 (ESA)}}
}}
```

## License

[CC-BY-4.0](https://creativecommons.org/licenses/by/4.0/)
""")

        print("Uploading to HF...")
        commit_msg = f"Update Gaia DR3 young stellar objects: {n_total:,} sources"
        subprocess.run(
            ["hf", "upload", HF_REPO, str(tmp), ".",
             "--repo-type", "dataset",
             "--commit-message", commit_msg],
            check=True,
        )

    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a") as f:
            f.write(f"rows={len(df)}\n")
    print("Done.")


if __name__ == "__main__":
    main()
