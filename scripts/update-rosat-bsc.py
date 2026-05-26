#!/usr/bin/env python3
"""Fetch ROSAT All-Sky Survey Bright Source Catalogue (1RXS) from VizieR and upload to HF.

Source: Voges et al. (1999), A&A 349, 389 — VizieR IX/10A/1rxs
Static dataset — first complete soft X-ray (0.1–2.4 keV) all-sky survey.
"""

from hf_dataset_utils import Pipeline
from hf_dataset_utils.tap import vizier_query

HF_REPO = "juliensimon/rosat-bright-source-catalog"

ADQL = 'SELECT * FROM "IX/10A/1rxs"'

RENAME = {
    "1RXS": "iau_name",
    "n_1RXS": "note_flag",
    "RAJ2000": "ra_deg",
    "DEJ2000": "dec_deg",
    "PosErr": "pos_error_arcsec",
    "Count": "count_rate",
    "e_Count": "count_rate_err",
    "bgCt": "bg_count_rate",
    "ExpTime": "exp_time_s",
    "HR1": "hardness_ratio_1",
    "e_HR1": "hardness_ratio_1_err",
    "HR2": "hardness_ratio_2",
    "e_HR2": "hardness_ratio_2_err",
    "Extent": "source_extent",
    "L_Extent": "extent_likelihood",
    "Ldetect": "detection_likelihood",
    "ExtRad": "extent_radius_arcsec",
    "PHA": "spectral_band",
    "VigFactor": "vignetting_factor",
    "Ncand": "num_candidates",
}

DROP_COLS = ["recno", "ScrFlags", "NewFlag", "PrioFlags", "IncDate", "UpdDate", "SASS", "MASOL"]

COLUMN_DESCRIPTIONS = {
    "iau_name": "IAU source designation in format 1RXS JHHMMSS.s+DDMMSS",
    "note_flag": "Note flag: 'N' = new source added post-publication",
    "ra_deg": "Right ascension (J2000, degrees)",
    "dec_deg": "Declination (J2000, degrees)",
    "pos_error_arcsec": "90% confidence positional error radius (arcsec); typical ~30 arcsec",
    "count_rate": "ROSAT PSPC source count rate in the 0.1–2.4 keV band (counts/s)",
    "count_rate_err": "1-sigma error on count_rate (counts/s)",
    "bg_count_rate": "Background count rate per arcmin² at source position (counts/s/arcmin²)",
    "exp_time_s": "Effective ROSAT PSPC exposure time at source position (seconds)",
    "hardness_ratio_1": "Hardness ratio HR1 = (B-A)/(B+A), where A=0.1–0.4 keV, B=0.5–2.0 keV",
    "hardness_ratio_1_err": "1-sigma error on hardness_ratio_1",
    "hardness_ratio_2": "Hardness ratio HR2 = (D-C)/(D+C), where C=0.5–0.9 keV, D=0.9–2.0 keV",
    "hardness_ratio_2_err": "1-sigma error on hardness_ratio_2",
    "source_extent": "Source extent (arcsec) from RASS profile fitting; 0 = point source",
    "extent_likelihood": "Likelihood of source being extended; >10 suggests extent",
    "detection_likelihood": "Maximum likelihood of source detection; threshold ~15 for BSC",
    "extent_radius_arcsec": "Radius used for source photon extraction (arcsec)",
    "spectral_band": "Hardness-based spectral band classification (a–e, hard to soft)",
    "vignetting_factor": "Effective exposure correction for off-axis vignetting (0–1)",
    "num_candidates": "Number of source candidates in the detection cell",
}

DESCRIPTION = """\
The ROSAT All-Sky Survey Bright Source Catalogue (RASS-BSC or 1RXS) contains \
18,806 X-ray sources detected during the ROSAT All-Sky Survey in the soft \
X-ray band (0.1–2.4 keV). Published by Voges et al. (1999), it is the first \
complete all-sky X-ray survey performed with an imaging telescope.

The ROSAT (Röntgensatellit) mission, a joint German/US/UK project, scanned the \
entire sky during its first six months of operation (August 1990 – February 1991) \
using its Position Sensitive Proportional Counter (PSPC). The resulting all-sky \
survey revealed the soft X-ray universe in unprecedented detail, detecting stellar \
coronae, cataclysmic variables, white dwarfs, neutron stars, active galactic nuclei, \
galaxy clusters, and supernova remnants. Each source required a detection likelihood \
≥15 (~6σ significance) to be included in the bright source catalogue.

The two hardness ratios (HR1, HR2) characterise the spectral shape of each source \
without requiring spectral fitting. HR1 distinguishes soft thermal plasma sources \
(stellar coronae, <1 keV) from harder sources (AGN, X-ray binaries, >1 keV). \
Together they span the full ROSAT bandpass and enable quick classification of \
large samples. The count rate can be converted to unabsorbed flux using an assumed \
spectral model and the hydrogen column density toward each source.

This catalogue is the definitive soft X-ray baseline for the entire sky, used \
extensively for identifying counterparts of sources detected by later missions \
(XMM-Newton, Chandra, Swift) and for population studies of X-ray emitting classes. \
It complements harder X-ray catalogs such as the Swift-BAT 157-month survey \
(15–195 keV) and the 4XMM-DR14 serendipitous catalog (0.2–12 keV)."""

COLLECTION_URL = "https://huggingface.co/collections/juliensimon/astronomy-datasets-69c24caf2f17e36128946743"


def main():
    print("Fetching ROSAT Bright Source Catalogue from VizieR...")
    df = vizier_query(ADQL)
    print(f"  {len(df):,} rows fetched")

    df = df.drop(columns=[c for c in DROP_COLS if c in df.columns])
    df = df.rename(columns=RENAME)

    n = len(df)
    n_extended = int((df["source_extent"] > 0).sum())
    med_exp = int(df["exp_time_s"].median())
    count_max = df["count_rate"].max()
    top_src = df.loc[df["count_rate"].idxmax(), "iau_name"]

    quick_stats = f"""\
- **{n:,}** soft X-ray sources (0.1–2.4 keV), detection likelihood ≥ 15
- **{n_extended:,}** extended sources ({n_extended/n*100:.1f}% of catalogue)
- Median exposure time: **{med_exp:,} s** — peak count rate {count_max:.1f} ct/s ({top_src})
- Full-sky coverage; typical positional accuracy ~30 arcsec"""

    usage = f"""\
```python
from datasets import load_dataset

ds = load_dataset("{HF_REPO}", split="train")
df = ds.to_pandas()

# Hardest sources (likely AGN or X-ray binaries)
hard = df[df["hardness_ratio_1"] > 0.5].sort_values("count_rate", ascending=False)

# Sky distribution
import matplotlib.pyplot as plt
import numpy as np
ra = np.where(df["ra_deg"] > 180, df["ra_deg"] - 360, df["ra_deg"])
plt.figure(figsize=(12, 5))
plt.scatter(ra, df["dec_deg"], s=0.3, alpha=0.4, c=np.log10(df["count_rate"].clip(0.01)))
plt.colorbar(label="log₁₀(count rate)")
plt.xlabel("RA (deg, centred on 0)")
plt.ylabel("Dec (deg)")
plt.title("ROSAT BSC — X-ray sky")
plt.show()
```"""

    with Pipeline(
        repo=HF_REPO,
        pretty_name="ROSAT All-Sky Survey Bright Source Catalog",
        description=DESCRIPTION,
        tags=["space", "x-ray", "astronomy", "rosat", "soft-x-ray", "sky-survey",
              "open-data", "tabular-data", "parquet"],
        source_url="https://vizier.cds.unistra.fr/viz-bin/VizieR-3?-source=IX/10A/1rxs",
        license="other",
        license_name="vizier-scientific-use",
        license_link="https://cds.unistra.fr/vizier-org/licences_vizier.html",
        task_categories=["tabular-classification"],
        collection_url=COLLECTION_URL,
        banner={
            "url": "https://images-assets.nasa.gov/image/PIA03519/PIA03519~small.jpg",
            "alt": "All-sky X-ray map from ROSAT survey showing the hot universe",
            "credit": "NASA/ROSAT",
        },
        related_datasets=[
            "juliensimon/4xmm-dr14-xray-sources",
            "juliensimon/chandra-source-catalog",
            "juliensimon/swift-bat-hard-xray-survey",
        ],
    ) as p:
        NUMERIC_COLS = [
            "ra_deg", "dec_deg", "pos_error_arcsec", "count_rate", "count_rate_err",
            "bg_count_rate", "exp_time_s", "hardness_ratio_1", "hardness_ratio_1_err",
            "hardness_ratio_2", "hardness_ratio_2_err", "source_extent", "extent_likelihood",
            "detection_likelihood", "extent_radius_arcsec", "vignetting_factor", "num_candidates",
        ]
        df = p.clean(
            df,
            numeric=NUMERIC_COLS,
            strings=["iau_name", "note_flag", "spectral_band"],
            drop_mostly_null_threshold=0.95,
        )
        p.publish(
            df,
            filename="rosat_bsc.parquet",
            min_rows=18_000,
            expected_columns=["iau_name", "ra_deg", "dec_deg", "count_rate"],
            critical_columns=["iau_name", "ra_deg", "dec_deg"],
            column_descriptions=COLUMN_DESCRIPTIONS,
            quick_stats=quick_stats,
            usage=usage,
            commit_message=f"Upload ROSAT BSC: {n:,} soft X-ray sources",
        )
    print("Done.")


if __name__ == "__main__":
    main()
