#!/usr/bin/env python3
"""Fetch Galactic Carbon Stars (GCCS) catalog from VizieR and upload to HF.

Source: Alksnis, A. et al. (2001), "A catalogue of Galactic carbon stars",
Baltic Astronomy, 10, 1. VizieR catalog: III/227.
"""

import pandas as pd

from hf_dataset_utils import Pipeline
from hf_dataset_utils.tap import vizier_query

HF_REPO = "juliensimon/carbon-stars"

# ── Source query ─────────────────────────────────────────────────────
ADQL = 'SELECT * FROM "III/227/catalog"'

# ── Column mapping ───────────────────────────────────────────────────
# Actual VizieR columns: recno, Jname, CGCS, RAJ2000, DEJ2000, l_Bmag, Bmag,
# u_Bmag, Vmag, u_Vmag, irmag, n_irmag, u_irmag, Sp, Names, Notes, Pr
RENAME = {
    "RAJ2000": "ra_deg",
    "RA_ICRS": "ra_deg",
    "_RA": "ra_deg",
    "DEJ2000": "dec_deg",
    "DE_ICRS": "dec_deg",
    "_DE": "dec_deg",
    "CGCS": "cgcs_number",
    "Jname": "j_name",
    "Bmag": "b_mag",
    "Vmag": "v_mag",
    "irmag": "ir_mag",
    "Sp": "spectral_type",
    "Names": "names",
    "Notes": "notes",
    "Pr": "priority",
    "l_Bmag": "b_mag_limit_flag",
    "u_Bmag": "b_mag_uncertainty_flag",
    "u_Vmag": "v_mag_uncertainty_flag",
    "n_irmag": "ir_mag_band",
    "u_irmag": "ir_mag_uncertainty_flag",
}

# ── Column descriptions for README schema table ─────────────────────
COLUMN_DESCRIPTIONS = {
    "cgcs_number": "Sequential catalog number in the CGCS (Catalogue of Galactic Carbon Stars, Stephenson 1989, updated Alksnis et al. 2001); primary sort key and identifier",
    "j_name": "J2000 positional designation derived from RA/Dec (e.g. 'J191104.6+040429'); useful for cross-matching with other surveys",
    "ra_deg": "Right ascension, ICRS J2000.0, in decimal degrees (0-360)",
    "dec_deg": "Declination, ICRS J2000.0, in decimal degrees (-90 to +90)",
    "b_mag": "Johnson B-band apparent magnitude; carbon stars are extremely red so B magnitudes are much fainter than V; null for many entries",
    "b_mag_limit_flag": "Limit flag for B magnitude: '<' or '>' indicates the value is an upper/lower limit rather than a measurement",
    "b_mag_uncertainty_flag": "Uncertainty qualifier for B magnitude (e.g. ':' for uncertain values)",
    "v_mag": "Johnson V-band apparent magnitude; carbon stars are very red, typical V = 6-14 mag; null for highly obscured AGB stars",
    "v_mag_uncertainty_flag": "Uncertainty qualifier for V magnitude (e.g. ':' for uncertain values)",
    "ir_mag": "Infrared magnitude from various surveys (band indicated by ir_mag_band); carbon stars are luminous IR sources due to circumstellar dust; null where no IR photometry available",
    "ir_mag_band": "Photometric band identifier for ir_mag: indicates which IR survey/band the magnitude comes from (e.g. K, L, or IRAS band)",
    "ir_mag_uncertainty_flag": "Uncertainty qualifier for infrared magnitude",
    "spectral_type": "Spectral classification string encoding carbon subclass (e.g. 'C-N5', 'C6,2', 'R0'); C-N = cool AGB giants, C-R = warm giants, C-J = enhanced 13C, C-H = halo; null for ~30% of entries",
    "names": "Cross-identification names from other catalogs (variable star designations, HD numbers, IRC numbers); multiple names separated by commas; null if no cross-IDs",
    "notes": "Catalog notes and remarks about the star (variability, binarity, spectral peculiarities); null for most entries",
    "priority": "Priority code from the original Stephenson catalog indicating confidence of carbon star classification; integer scale",
    "has_ir_photometry": "True if ir_mag is non-null; useful filter for studies requiring infrared data",
}

# ── Dataset description ──────────────────────────────────────────────
DESCRIPTION = """\
Catalog of Galactic carbon stars from the General Catalogue of Galactic Cool \
Carbon Stars (GCCS, 3rd Edition). Carbon stars are evolved red giant branch / \
asymptotic giant branch (AGB) stars whose atmospheres are enriched in carbon from \
internal nucleosynthesis (dredge-up episodes). Their distinctive molecular bands \
(C2, CN, CH) make them important tracers of stellar evolution and galactic structure.

The Stephenson GCCS (3rd Edition, Alksnis et al. 2001) is the definitive reference \
catalog of Galactic cool carbon stars, with equatorial positions, visual and infrared \
magnitudes, spectral types, and cross-identifications. Carbon stars are classified into \
several subtypes: C-N (classical cool AGB giants), C-R (warm carbon giants, possibly \
formed through binary mergers), C-J (strong 13C isotope features), C-H (high-velocity \
halo carbon stars), and C-Hd (hydrogen-deficient, R CrB type).

Carbon stars occupy a pivotal role in stellar evolution and galactic chemical enrichment. \
The defining characteristic — a C/O ratio greater than unity — arises primarily through \
the third dredge-up process on the AGB, where convective mixing carries freshly \
synthesized carbon-12 from the helium-burning shell to the surface. As luminous infrared \
sources (M_bol typically -3 to -6), carbon stars are detectable at large distances and \
serve as excellent tracers of intermediate-age stellar populations (1-4 Gyr).
"""


def main():
    print("Fetching Galactic Carbon Stars (GCCS) from VizieR...")
    df = vizier_query(ADQL)
    print(f"  {len(df):,} carbon stars fetched")

    # Drop VizieR internal columns
    for col in ["recno", "SimbadName", "More"]:
        if col in df.columns:
            df = df.drop(columns=[col])

    df = df.rename(columns={k: v for k, v in RENAME.items() if k in df.columns})

    # Clean string columns
    for col in ["j_name", "spectral_type", "names", "notes",
                "b_mag_limit_flag", "b_mag_uncertainty_flag",
                "v_mag_uncertainty_flag", "ir_mag_band", "ir_mag_uncertainty_flag"]:
        if col in df.columns:
            df[col] = df[col].astype(str).str.strip().replace(
                {"": pd.NA, "None": pd.NA, "nan": pd.NA, "null": pd.NA}
            )

    # Derived: has IR photometry
    df["has_ir_photometry"] = df["ir_mag"].notna() if "ir_mag" in df.columns else False

    # Keep only described columns
    df = df[[c for c in df.columns if c in COLUMN_DESCRIPTIONS]]

    # Sort by CGCS number if available
    if "cgcs_number" in df.columns:
        df["cgcs_number"] = pd.to_numeric(df["cgcs_number"], errors="coerce")
        df = df.sort_values("cgcs_number").reset_index(drop=True)
    else:
        df = df.sort_values("ra_deg").reset_index(drop=True)

    # ── Domain-specific stats for README ─────────────────────────────
    n_total = len(df)
    n_with_sp = int(df["spectral_type"].notna().sum()) if "spectral_type" in df.columns else 0
    n_with_ir = int(df["has_ir_photometry"].sum())
    v_valid = df["v_mag"].dropna()
    v_range = f"{v_valid.min():.1f}-{v_valid.max():.1f}" if len(v_valid) > 0 else "N/A"
    b_valid = df["b_mag"].dropna() if "b_mag" in df.columns else pd.Series(dtype=float)
    b_range = f"{b_valid.min():.1f}-{b_valid.max():.1f}" if len(b_valid) > 0 else "N/A"

    quick_stats = f"""\
- **{n_total:,}** Galactic carbon stars
- **{n_with_sp:,}** with spectral classification
- **{n_with_ir:,}** with infrared photometry
- V magnitude range: {v_range}
- B magnitude range: {b_range}"""

    usage = """\
```python
from datasets import load_dataset

ds = load_dataset("juliensimon/carbon-stars", split="train")
df = ds.to_pandas()

# Stars with spectral classification
classified = df.dropna(subset=["spectral_type"])
print(f"{len(classified):,} stars with spectral type")

# V-band magnitude distribution
import matplotlib.pyplot as plt
fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 5))
df["v_mag"].dropna().hist(bins=40, ax=ax1, edgecolor="k", alpha=0.7)
ax1.set_xlabel("V magnitude")
ax1.set_ylabel("Count")
ax1.set_title("V-band Distribution")

# Sky distribution in Galactic coordinates
ax2.scatter(df["ra_deg"], df["dec_deg"], s=0.5, alpha=0.3, c="orangered")
ax2.set_xlabel("RA (deg)")
ax2.set_ylabel("Dec (deg)")
ax2.set_title("Galactic Carbon Stars — Sky Distribution")
ax2.invert_xaxis()
plt.tight_layout()
plt.show()
```"""

    with Pipeline(
        repo=HF_REPO,
        pretty_name="Galactic Carbon Stars (GCCS)",
        description=DESCRIPTION,
        tags=["space", "stars", "carbon-stars", "agb", "evolved-stars",
              "spectroscopy", "astronomy", "open-data", "tabular-data", "parquet"],
        source_url="https://vizier.cds.unistra.fr/viz-bin/VizieR-3?-source=III/227",
        task_categories=["tabular-classification"],
        collection_url="https://huggingface.co/collections/juliensimon/astronomy-datasets-69c24caf2f17e36128946743",
        banner={
            "url": "https://images-assets.nasa.gov/image/GSFC_20171208_Archive_e000191/GSFC_20171208_Archive_e000191~medium.jpg",
            "alt": "A youthful globular star cluster observed by the Hubble Space Telescope",
            "credit": "NASA/ESA/Hubble",
        },
        related_datasets=[
            "juliensimon/wolf-rayet-stars",
            "juliensimon/brown-dwarf-catalog",
            "juliensimon/gcvs-variable-stars",
        ],
    ) as p:
        df = p.clean(
            df,
            numeric=["ra_deg", "dec_deg", "b_mag", "v_mag", "ir_mag"],
            integer={"cgcs_number": "Int64", "priority": "Int64"},
            drop_mostly_null_threshold=0.95,
        )
        p.publish(
            df,
            filename="carbon_stars.parquet",
            min_rows=5000,
            expected_columns=["ra_deg", "dec_deg"],
            critical_columns=["ra_deg", "dec_deg"],
            column_descriptions=COLUMN_DESCRIPTIONS,
            quick_stats=quick_stats,
            usage=usage,
            commit_message=f"Update Galactic Carbon Stars (GCCS): {n_total:,} stars",
        )
    print("Done.")


if __name__ == "__main__":
    main()
