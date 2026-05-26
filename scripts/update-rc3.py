#!/usr/bin/env python3
"""Fetch RC3 galaxy morphology catalog from VizieR and upload to HF.

Source: de Vaucouleurs, G. et al. (1991), "Third Reference Catalogue of
Bright Galaxies (RC3)", Springer-Verlag, New York.
VizieR catalog: VII/155
"""

import pandas as pd

from hf_dataset_utils import Pipeline
from hf_dataset_utils.tap import vizier_query

HF_REPO = "juliensimon/rc3-galaxy-morphology"

ADQL = """SELECT * FROM "VII/155/rc3" """

# ── Column mapping ───────────────────────────────────────────────────
RENAME = {
    "RA2000": "ra_deg",
    "RA_ICRS": "ra_deg",
    "RAJ2000": "ra_deg",
    "_RA": "ra_deg",
    "DE2000": "dec_deg",
    "DE_ICRS": "dec_deg",
    "DEJ2000": "dec_deg",
    "_DE": "dec_deg",
    "name": "galaxy_name",
    "Name": "galaxy_name",
    "PGC": "pgc_number",
    "type": "morphological_type",
    "T": "morphological_type_t",
    "LC": "luminosity_class",
    "SB": "surface_brightness",
    "BT": "bt_magnitude",
    "e_BT": "e_bt_magnitude",
    "B-V": "b_v_color",
    "U-B": "u_b_color",
    "HRV": "helio_radial_velocity",
    "e_HRV": "e_helio_radial_velocity",
    "logD25": "log_diameter_d25",
    "logR25": "log_axis_ratio_r25",
    "MType": "morphological_type",
}

# ── Column descriptions for README schema table ─────────────────────
COLUMN_DESCRIPTIONS = {
    "galaxy_name": "Galaxy primary designation (e.g., 'NGC 1068', 'M 77', 'IC 342'); null for objects cataloged only by PGC number",
    "pgc_number": "PGC (Principal Galaxies Catalogue) identifier; the standard cross-reference number used by HyperLEDA and most modern galaxy databases",
    "ra_deg": "ICRS J2000.0 right ascension in degrees (0-360)",
    "dec_deg": "ICRS J2000.0 declination in degrees (-90 to +90)",
    "morphological_type": "de Vaucouleurs revised Hubble type string (e.g., 'SA(rs)bc', 'SBb', 'E0', 'Irr'); encodes bar strength (SA/SAB/SB), inner ring, and arm openness; null if unclassified",
    "morphological_type_t": "Numerical de Vaucouleurs type T: -5 = elliptical (E), -3 = lenticular (S0-), 0 = lenticular (S0), 1-9 = spiral (Sa=1 to Sd=7, Sdm=8), 10 = irregular; null if unclassified",
    "luminosity_class": "van den Bergh luminosity class I-V (lower = brighter); distinguishes supergiant spirals (I) from dwarf spirals (V); null for ellipticals and most non-spiral types",
    "surface_brightness": "Mean effective surface brightness within the D25 isophote in B mag/arcsec^2; higher values indicate fainter (lower surface brightness) galaxies; null if not measured",
    "bt_magnitude": "Total apparent B-band magnitude (Johnson B); null for objects without CCD photometry; bright galaxies typically 8-15 mag",
    "e_bt_magnitude": "Uncertainty on bt_magnitude in magnitudes; null if bt_magnitude is null",
    "b_v_color": "Total B-V color index in magnitudes; ellipticals: ~0.90, spirals: ~0.45-0.80, irregulars: ~0.30-0.50; null if not measured",
    "u_b_color": "Total U-B color index in magnitudes; traces young stellar populations; star-forming galaxies: ~-0.3 to 0.0, old ellipticals: ~0.5; null if not measured",
    "helio_radial_velocity": "Heliocentric recession velocity in km/s from optical spectroscopy; null if no spectrum available",
    "e_helio_radial_velocity": "1-sigma uncertainty on helio_radial_velocity in km/s; null if helio_radial_velocity is null",
    "log_diameter_d25": "Log10 of the major-axis isophotal diameter at 25 B-mag/arcsec^2 in units of 0.1 arcmin (i.e., diameter in arcmin = 10^log_diameter_d25 / 10); null if not measured",
    "log_axis_ratio_r25": "Log10 of the major-to-minor axis ratio at the D25 isophote (log10(a/b)); 0 = circular, higher = more inclined/elongated; null if not measured",
}

# ── Dataset description ──────────────────────────────────────────────
DESCRIPTION = """\
The Third Reference Catalogue of Bright Galaxies (RC3), the classic comprehensive catalog of \
bright galaxies with Hubble-type morphological classifications, photometry, diameters, and \
radial velocities.

RC3 is the definitive catalog of bright galaxies, compiled by de Vaucouleurs, de Vaucouleurs, \
Corwin, Buta, Paturel, and Fouque (1991). It provides homogeneous morphological classifications \
on the revised Hubble system (numerical type T from -5 for ellipticals to +10 for irregulars), \
total B magnitudes, colors, diameters, axis ratios, luminosity classes, surface brightnesses, \
and heliocentric radial velocities. RC3 remains the standard reference for galaxy morphology \
and is widely used for training galaxy classification models.

The revised Hubble classification system used by RC3 assigns each galaxy a numerical type T \
that runs continuously from -5 for giant ellipticals through 0 for lenticulars (S0) to +10 \
for irregular galaxies, with spirals occupying the range +1 to +9 and subdivided by bar \
strength (SA, SAB, SB) and arm openness (a, b, c, d, m). This quantitative encoding of \
morphology has proven remarkably effective at predicting galaxy properties: T-type correlates \
strongly with color, gas fraction, star formation rate, bulge-to-disk ratio, and stellar \
population age.

Although compiled in 1991, RC3 remains widely cited because no subsequent catalog has matched \
its combination of completeness, homogeneity, and morphological detail for bright galaxies. \
It serves as the primary cross-reference for the PGC numbering system used by HyperLEDA and \
many modern galaxy catalogs, and it provides the foundational morphological classifications \
that downstream catalogs like HECATE inherit.
"""


def main():
    print("Fetching RC3 galaxy catalog from VizieR...")
    df = vizier_query(ADQL)
    print(f"  {len(df):,} raw rows")

    # Rename columns
    df = df.rename(columns={k: v for k, v in RENAME.items() if k in df.columns})

    # Drop VizieR internal columns
    for col in ["recno", "More", "SimbadName"]:
        if col in df.columns:
            df = df.drop(columns=[col])

    # Clean string columns
    for col in ["galaxy_name", "morphological_type"]:
        if col in df.columns:
            df[col] = df[col].astype(str).str.strip().replace(
                {"": pd.NA, "None": pd.NA, "nan": pd.NA, "null": pd.NA}
            )

    # Keep only described columns
    df = df[[c for c in df.columns if c in COLUMN_DESCRIPTIONS]]

    # ── Domain-specific stats for README ─────────────────────────────
    n_total = len(df)
    n_with_type = int(df["morphological_type"].notna().sum()) if "morphological_type" in df.columns else 0
    n_with_mag = int(df["bt_magnitude"].notna().sum()) if "bt_magnitude" in df.columns else 0
    n_with_rv = int(df["helio_radial_velocity"].notna().sum()) if "helio_radial_velocity" in df.columns else 0
    if "morphological_type_t" in df.columns:
        t_min = df["morphological_type_t"].min()
        t_max = df["morphological_type_t"].max()
    else:
        t_min, t_max = 0, 0

    quick_stats = f"""\
- **{n_total:,}** bright galaxies
- **{n_with_type:,}** with morphological type
- **{n_with_mag:,}** with B magnitude
- **{n_with_rv:,}** with radial velocity
- Hubble type T range: {t_min:.0f} to {t_max:.0f}"""

    usage = """\
```python
from datasets import load_dataset

ds = load_dataset("juliensimon/rc3-galaxy-morphology", split="train")
df = ds.to_pandas()

# Hubble type distribution
import matplotlib.pyplot as plt
df["morphological_type_t"].dropna().hist(bins=30)
plt.xlabel("Hubble Type T (-5=E, 0=S0/a, 5=Sc, 10=Irr)")
plt.ylabel("Count")
plt.title("RC3 Galaxy Morphological Type Distribution")
plt.show()

# Color-magnitude diagram
valid = df.dropna(subset=["bt_magnitude", "b_v_color"])
plt.scatter(valid["b_v_color"], valid["bt_magnitude"], s=1, alpha=0.3)
plt.gca().invert_yaxis()
plt.xlabel("B-V Color")
plt.ylabel("B magnitude")
plt.title("RC3 Color-Magnitude Diagram")
plt.show()

# Ellipticals vs spirals
ellipticals = df[df["morphological_type_t"] <= -3]
spirals = df[(df["morphological_type_t"] >= 1) & (df["morphological_type_t"] <= 9)]
print(f"Ellipticals (T <= -3): {len(ellipticals):,}")
print(f"Spirals (1 <= T <= 9): {len(spirals):,}")
```"""

    with Pipeline(
        repo=HF_REPO,
        pretty_name="Third Reference Catalogue of Bright Galaxies (RC3)",
        description=DESCRIPTION,
        tags=["space", "galaxy", "morphology", "rc3", "hubble-type",
              "astronomy", "open-data", "tabular-data", "parquet"],
        source_url="https://vizier.cds.unistra.fr/viz-bin/VizieR-3?-source=VII/155",
        license="other",
        license_name="vizier-scientific-use",
        license_link="https://cds.unistra.fr/vizier-org/licences_vizier.html",
        task_categories=["tabular-classification"],
        collection_url="https://huggingface.co/collections/juliensimon/astronomy-datasets-69c24caf2f17e36128946743",
        banner={
            "url": "https://images-assets.nasa.gov/image/PIA12110/PIA12110~small.jpg",
            "alt": "Hubble Deep Field revealing myriad galaxies across cosmic time",
            "credit": "NASA/ESA/STScI",
        },
        related_datasets=[
            "juliensimon/hecate-nearby-galaxies",
            "juliensimon/ngc-ic-catalog",
            "juliensimon/galaxy-zoo-2-morphology",
        ],
    ) as p:
        df = p.clean(
            df,
            numeric=[
                "ra_deg", "dec_deg", "morphological_type_t", "luminosity_class",
                "surface_brightness", "bt_magnitude", "e_bt_magnitude",
                "b_v_color", "u_b_color",
                "helio_radial_velocity", "e_helio_radial_velocity",
                "log_diameter_d25", "log_axis_ratio_r25",
            ],
            drop_mostly_null_threshold=0.95,
        )
        p.publish(
            df,
            filename="rc3_galaxies.parquet",
            min_rows=20_000,
            expected_columns=["ra_deg", "dec_deg"],
            critical_columns=["ra_deg", "dec_deg"],
            column_descriptions=COLUMN_DESCRIPTIONS,
            quick_stats=quick_stats,
            usage=usage,
            commit_message=f"Update RC3 galaxy morphology: {n_total:,} galaxies",
        )
    print("Done.")


if __name__ == "__main__":
    main()
