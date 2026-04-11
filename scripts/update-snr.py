#!/usr/bin/env python3
"""Fetch Green's SNR Catalog from HEASARC and upload to HF.

Source: Green (2019) — A Catalogue of Galactic Supernova Remnants
HEASARC table: snrgreen
"""

import pandas as pd

from hf_dataset_utils import Pipeline
from hf_dataset_utils.tap import heasarc_query

HF_REPO = "juliensimon/supernova-remnants"

ADQL = """\
SELECT name, alt_names, ra, dec, lii, bii, major_diameter, minor_diameter,
  type, flux_1_ghz, spectral_index
FROM snrgreen ORDER BY name\
"""

SNR_TYPE_MAP = {
    "S": "shell",
    "F": "filled-centre",
    "C": "composite",
    "?": "uncertain",
}

# ── Column descriptions for README schema table ─────────────────────
COLUMN_DESCRIPTIONS = {
    "name": "SNR designation in Galactic coordinates (e.g. 'G001.0-00.1')",
    "alt_names": "Alternative/common names (e.g. 'Cas A', 'Crab Nebula'); null for unnamed remnants",
    "ra": "Right ascension, ICRS J2000.0 (degrees, 0-360)",
    "dec": "Declination, ICRS J2000.0 (degrees, -90 to +90)",
    "lii": "Galactic longitude (degrees, 0-360)",
    "bii": "Galactic latitude (degrees, -90 to +90); most SNRs lie within +-5 deg of the Galactic plane",
    "major_diameter": "Angular size of the major axis (arcmin); ranges from <1' for young compact remnants to >300' for old evolved SNRs like Vela",
    "minor_diameter": "Angular size of the minor axis (arcmin); null if the remnant is approximately circular or the minor axis is unmeasured",
    "type": "Morphological type code: S (shell -- forward shock dominates), F (filled-centre/plerion -- pulsar wind nebula), C (composite -- both features), ? (uncertain)",
    "flux_1_ghz": "Integrated radio flux density at 1 GHz (Jansky; 1 Jy = 10^-26 W/m^2/Hz); null for remnants too faint or confused for measurement",
    "spectral_index": "Radio spectral index alpha (S_nu proportional to nu^alpha); shell-type SNRs typically alpha ~ -0.5, plerions (filled-centre) alpha ~ 0 to -0.3; null if spectrum is unmeasured",
    "snr_type_name": "Full type name derived from type code: shell, filled-centre, composite, uncertain",
}

# ── Dataset description ──────────────────────────────────────────────
DESCRIPTION = """\
Galactic supernova remnants from Green's catalog with positions, angular sizes, radio \
flux, and spectral indices.

Supernova remnants (SNRs) are the expanding shells of gas and dust left behind after a \
supernova explosion. They are key sources of cosmic rays and play a major role in the \
chemical enrichment of the interstellar medium. Green's catalog is the standard reference \
for Galactic SNRs, maintained since 1984.

This dataset includes positions (equatorial and Galactic), angular sizes, morphological \
type, 1 GHz radio flux density, and radio spectral index for each remnant.

Supernova remnants are among the most important objects in astrophysics. Their expanding \
blast waves are widely believed to be the primary accelerators of Galactic cosmic rays up \
to the "knee" of the cosmic ray spectrum (~3 PeV). The three morphological types -- shell, \
filled-centre (plerion), and composite -- reflect distinct physical configurations: \
shell-type remnants are dominated by the forward shock sweeping up the interstellar medium, \
filled-centre remnants are powered by a central pulsar wind nebula, and composites exhibit \
both features.

The radio spectral index is a key diagnostic: shell-type SNRs typically show spectral \
indices around -0.5 (consistent with diffusive shock acceleration), while filled-centre \
remnants powered by pulsar winds tend to have flatter spectra (-0.0 to -0.3). Green's \
catalog remains the definitive census of the ~300 known Galactic SNRs -- a number thought \
to represent only a fraction of the true population.
"""


def main():
    print("Fetching Green's SNR Catalog from HEASARC...")
    df = heasarc_query("snrgreen", ADQL)
    print(f"  {len(df):,} SNRs fetched")

    # Derived column: full SNR type name
    if "type" in df.columns:
        df["snr_type_name"] = df["type"].apply(
            lambda x: SNR_TYPE_MAP.get(str(x).strip().rstrip("?"), "uncertain")
            if pd.notna(x) and str(x).strip() else None
        )

    # Keep only described columns
    df = df[[c for c in df.columns if c in COLUMN_DESCRIPTIONS]]

    # Sort by name
    df = df.sort_values("name").reset_index(drop=True)

    # ── Domain-specific stats for README ─────────────────────────────
    n_total = len(df)
    type_counts = df["snr_type_name"].value_counts().to_dict() if "snr_type_name" in df.columns else {}
    n_shell = type_counts.get("shell", 0)
    n_filled = type_counts.get("filled-centre", 0)
    n_composite = type_counts.get("composite", 0)
    n_with_flux = int(df["flux_1_ghz"].notna().sum())

    quick_stats = f"""\
- **{n_total:,}** supernova remnants
- **{n_shell}** shell, **{n_filled}** filled-centre, **{n_composite}** composite
- **{n_with_flux}** with measured 1 GHz radio flux"""

    usage = """\
```python
from datasets import load_dataset

ds = load_dataset("juliensimon/supernova-remnants", split="train")
df = ds.to_pandas()

# SNRs by type
print(df["snr_type_name"].value_counts())

# Brightest SNRs at 1 GHz
top = df.nlargest(10, "flux_1_ghz")[["name", "alt_names", "flux_1_ghz"]]

# Sky distribution in Galactic coordinates
import matplotlib.pyplot as plt
plt.scatter(df["lii"], df["bii"], s=5)
plt.xlabel("Galactic longitude (deg)")
plt.ylabel("Galactic latitude (deg)")
plt.title("Galactic SNR Distribution")
plt.show()
```"""

    with Pipeline(
        repo=HF_REPO,
        pretty_name="Green's Supernova Remnant Catalog",
        description=DESCRIPTION,
        tags=["space", "supernova-remnant", "snr", "astronomy", "radio",
              "galactic", "open-data", "tabular-data", "parquet"],
        source_url="https://www.mrao.cam.ac.uk/surveys/snrs/",
        task_categories=["tabular-classification"],
        collection_url="https://huggingface.co/collections/juliensimon/astronomy-datasets-69c24caf2f17e36128946743",
        banner={
            "url": "https://images-assets.nasa.gov/image/PIA03606/PIA03606~small.jpg",
            "alt": "The Crab Nebula, a supernova remnant",
            "credit": "NASA/ESA/Hubble",
        },
        related_datasets=[
            "juliensimon/gamma-ray-bursts",
            "juliensimon/gravitational-wave-events",
            "juliensimon/pulsar-catalog",
        ],
    ) as p:
        df = p.clean(
            df,
            numeric=[
                "ra", "dec", "lii", "bii", "major_diameter", "minor_diameter",
                "flux_1_ghz", "spectral_index",
            ],
            drop_mostly_null_threshold=0.95,
        )
        p.publish(
            df,
            filename="snr.parquet",
            min_rows=200,
            expected_columns=["name", "ra", "dec", "type", "flux_1_ghz"],
            critical_columns=["name", "ra", "dec"],
            column_descriptions=COLUMN_DESCRIPTIONS,
            quick_stats=quick_stats,
            usage=usage,
            commit_message=f"Update SNR catalog: {n_total:,} remnants",
        )
    print("Done.")


if __name__ == "__main__":
    main()
