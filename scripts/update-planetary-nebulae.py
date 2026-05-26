#!/usr/bin/env python3
"""Fetch MUSE Planetary Nebulae catalog from VizieR and upload to HF.

Source: Jacoby, G.H. et al. (2024), "Planetary Nebulae from the MUSE Survey",
ApJS, 271, 40. VizieR catalog: J/ApJS/271/40.
"""

import pandas as pd

from hf_dataset_utils import Pipeline
from hf_dataset_utils.tap import vizier_query

HF_REPO = "juliensimon/planetary-nebulae"

# ── Source query ─────────────────────────────────────────────────────
ADQL = 'SELECT * FROM "J/ApJS/271/40/table3"'

# ── Column mapping ───────────────────────────────────────────────────
RENAME = {
    "RAJ2000": "ra_deg",
    "RA_ICRS": "ra_deg",
    "_RA": "ra_deg",
    "DEJ2000": "dec_deg",
    "DE_ICRS": "dec_deg",
    "_DE": "dec_deg",
    "Gal": "galaxy",
    "PNID": "pn_id",
    "Field": "field",
    "m5007": "m5007_mag",
    "e_m5007": "m5007_err",
    "lam5007": "lambda_5007_flux",
    "Flag": "flag",
}

# ── Column descriptions for README schema table ─────────────────────
COLUMN_DESCRIPTIONS = {
    "galaxy": "Host galaxy name (e.g. 'NGC 628', 'NGC 474'); each galaxy was surveyed with multiple MUSE pointings to build a complete PNe census",
    "pn_id": "Planetary nebula identifier within the survey, unique per galaxy; format varies by field",
    "field": "MUSE pointing field identifier within the host galaxy; a single galaxy may have multiple fields to cover its extent",
    "ra_deg": "Right ascension of the planetary nebula in decimal degrees, ICRS J2000.0 (0-360)",
    "dec_deg": "Declination of the planetary nebula in decimal degrees, ICRS J2000.0 (-90 to +90)",
    "m5007_mag": "Apparent magnitude in the [OIII] 5007 Angstrom emission line; this is the single brightest emission feature of PNe and the standard detection/distance tool via the planetary nebula luminosity function (PNLF); brighter (lower) values indicate more luminous PNe; the PNLF bright-end cutoff at M* ~ -4.5 mag is empirically constant across galaxy types",
    "m5007_err": "1-sigma uncertainty on the [OIII] 5007 magnitude (mag)",
    "lambda_5007_flux": "Measured [OIII] 5007 Angstrom emission line flux in instrumental units; used to derive m5007_mag; null where flux measurement was not possible",
    "flag": "Quality or classification flag from the survey; indicates detection confidence or special properties of the planetary nebula",
}

# ── Dataset description ──────────────────────────────────────────────
DESCRIPTION = """\
Catalog of planetary nebulae from the MUSE (Multi Unit Spectroscopic Explorer) survey \
on ESO's Very Large Telescope, with positions and [OIII] 5007 magnitudes across multiple \
host galaxies. From Jacoby et al. (2024, ApJS, 271, 40).

Planetary nebulae (PNe) are glowing shells of ionized gas expelled by intermediate-mass \
stars (1-8 solar masses) at the end of their lives. They are important distance indicators \
and tracers of stellar populations and chemical enrichment. The [OIII] 5007 Angstrom line \
is the single brightest emission feature and serves as the standard detection and distance \
measurement tool through the planetary nebula luminosity function (PNLF), one of the most \
reliable secondary distance indicators in extragalactic astronomy.

The MUSE integral-field spectrograph provides simultaneous imaging and spectroscopy over \
a 1x1 arcminute field of view with 0.2-arcsecond spatial sampling, enabling detection of \
PNe that would be missed by traditional narrow-band imaging surveys. MUSE's spectral \
coverage from 4700 to 9300 Angstroms captures not only [OIII] and H-alpha but also \
diagnostic lines that constrain nebular excitation, chemical abundances, and central star \
temperature.
"""


def main():
    print("Fetching MUSE planetary nebulae from VizieR...")
    df = vizier_query(ADQL)
    print(f"  {len(df):,} planetary nebulae")

    # Drop VizieR internal columns
    for col in ["recno", "SimbadName"]:
        if col in df.columns:
            df = df.drop(columns=[col])

    df = df.rename(columns={k: v for k, v in RENAME.items() if k in df.columns})

    # Clean string columns
    for col in ["galaxy", "pn_id", "field", "flag"]:
        if col in df.columns:
            df[col] = df[col].astype(str).str.strip().replace(
                {"": pd.NA, "None": pd.NA, "nan": pd.NA, "null": pd.NA}
            )

    # Keep only described columns
    df = df[[c for c in df.columns if c in COLUMN_DESCRIPTIONS]]

    # ── Domain-specific stats for README ─────────────────────────────
    n_total = len(df)
    n_with_m5007 = int(df["m5007_mag"].notna().sum()) if "m5007_mag" in df.columns else 0
    n_galaxies = int(df["galaxy"].nunique()) if "galaxy" in df.columns else 0
    m5007_valid = df["m5007_mag"].dropna() if "m5007_mag" in df.columns else pd.Series(dtype=float)
    m5007_range = f"{m5007_valid.min():.1f} to {m5007_valid.max():.1f}" if len(m5007_valid) > 0 else "N/A"

    quick_stats = f"""\
- **{n_total:,}** planetary nebulae
- **{n_with_m5007:,}** with [OIII] 5007 magnitude measurements
- **{n_galaxies}** host galaxies surveyed
- [OIII] m5007 range: {m5007_range} mag"""

    usage = """\
```python
from datasets import load_dataset

ds = load_dataset("juliensimon/planetary-nebulae", split="train")
df = ds.to_pandas()

# PNLF (Planetary Nebula Luminosity Function) per galaxy
import matplotlib.pyplot as plt

galaxies = df["galaxy"].value_counts().head(4).index
fig, axes = plt.subplots(2, 2, figsize=(10, 8))
for ax, gal in zip(axes.flat, galaxies):
    sub = df[(df["galaxy"] == gal) & df["m5007_mag"].notna()]
    ax.hist(sub["m5007_mag"], bins=20, edgecolor="k", alpha=0.7)
    ax.set_xlabel("[OIII] m5007 (mag)")
    ax.set_ylabel("Count")
    ax.set_title(f"{gal} ({len(sub)} PNe)")
plt.suptitle("Planetary Nebula Luminosity Functions")
plt.tight_layout()
plt.show()
```"""

    with Pipeline(
        repo=HF_REPO,
        pretty_name="Planetary Nebulae (MUSE Survey)",
        description=DESCRIPTION,
        tags=["space", "planetary-nebula", "muse", "astronomy",
              "open-data", "tabular-data", "parquet"],
        source_url="https://vizier.cds.unistra.fr/viz-bin/VizieR-3?-source=J/ApJS/271/40",
        license="other",
        license_name="vizier-scientific-use",
        license_link="https://cds.unistra.fr/vizier-org/licences_vizier.html",
        task_categories=["tabular-classification"],
        collection_url="https://huggingface.co/collections/juliensimon/astronomy-datasets-69c24caf2f17e36128946743",
        banner={
            "url": "https://images-assets.nasa.gov/image/GSFC_20171208_Archive_e000191/GSFC_20171208_Archive_e000191~medium.jpg",
            "alt": "A youthful globular star cluster observed by the Hubble Space Telescope",
            "credit": "NASA/ESA/Hubble",
        },
        related_datasets=[
            "juliensimon/open-star-clusters",
            "juliensimon/globular-clusters",
        ],
    ) as p:
        df = p.clean(
            df,
            numeric=["ra_deg", "dec_deg", "m5007_mag", "m5007_err", "lambda_5007_flux"],
            drop_mostly_null_threshold=0.95,
        )
        p.publish(
            df,
            filename="planetary_nebulae.parquet",
            min_rows=1000,
            expected_columns=["ra_deg", "dec_deg"],
            critical_columns=["ra_deg", "dec_deg"],
            column_descriptions=COLUMN_DESCRIPTIONS,
            quick_stats=quick_stats,
            usage=usage,
            commit_message=f"Update planetary nebulae: {n_total:,} PNe",
        )
    print("Done.")


if __name__ == "__main__":
    main()
