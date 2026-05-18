#!/usr/bin/env python3
"""Fetch quasar/AGN catalog from SIMBAD and upload to HF."""

import io

import pandas as pd
import requests

from hf_dataset_utils import Pipeline

HF_REPO = "juliensimon/quasar-catalog"

SIMBAD_TAP = "https://simbad.u-strasbg.fr/simbad/sim-tap/sync"

# SIMBAD otypes for AGN: QSO (quasar), AGN (active galactic nucleus),
# Sy1/Sy2 (Seyfert), BLL (BL Lac), Bla (Blazar), LIN (LINER)
ADQL = """SELECT TOP 100000 main_id AS name, ra, dec, otype AS object_type
FROM basic
WHERE otype = 'QSO' OR otype = 'AGN' OR otype = 'Sy1' OR otype = 'Sy2' OR otype = 'BLL' OR otype = 'Bla' OR otype = 'LIN'
ORDER BY main_id"""

# -- Column descriptions for README schema table ---------------------------
COLUMN_DESCRIPTIONS = {
    "name": "Primary SIMBAD identifier (e.g. 'QSO J1230+1223' or '3C 273'); unique within SIMBAD but may differ from other catalog designations",
    "ra_deg": "Right ascension of the AGN nucleus in the ICRS J2000.0 frame, decimal degrees (0-360)",
    "dec_deg": "Declination of the AGN nucleus in the ICRS J2000.0 frame, decimal degrees (-90 to +90)",
    "object_type": "SIMBAD machine-readable type code: 'QSO' = radio-quiet quasar, 'AGN' = broad-line active galactic nucleus, 'Sy1' = Seyfert 1 (broad + narrow lines, type-1 viewing angle), 'Sy2' = Seyfert 2 (narrow lines only, obscured nucleus), 'BLL' = BL Lac object (featureless continuum, jet pointing toward observer), 'Bla' = blazar (BL Lac or FSRQ with relativistic jet), 'LIN' = LINER (Low Ionization Nuclear Emission Region, weak AGN activity)",
    "agn_category": "Human-readable category derived from object_type: one of 'Quasar', 'AGN', 'Seyfert 1', 'Seyfert 2', 'BL Lac Object', 'Blazar', 'LINER'; useful for grouped analysis without parsing SIMBAD codes",
}

# -- Dataset description ----------------------------------------------------
DESCRIPTION = """\
Catalog of quasars and active galactic nuclei from SIMBAD -- quasars, Seyfert galaxies, \
blazars, and LINERs with positions and classifications.

Active galactic nuclei are galaxies whose central supermassive black holes are actively \
accreting matter, releasing enormous amounts of energy across the electromagnetic spectrum. \
Quasars, the most luminous subclass, can outshine their entire host galaxy by factors of a \
hundred or more and are visible at cosmological distances, making them powerful probes of \
the early universe. The different AGN categories in this catalog -- Seyfert 1 and 2 galaxies, \
blazars, BL Lac objects, and LINERs -- are thought to represent different viewing angles \
and accretion rates of the same underlying phenomenon, unified under orientation-dependent models.

These objects are critical for multiple areas of astrophysics. Quasars serve as background \
beacons for studying the intergalactic medium through absorption-line spectroscopy, they \
anchor the International Celestial Reference Frame (ICRF) used for precision astrometry, \
and their redshift distribution traces the growth history of supermassive black holes across \
cosmic time. Blazars, whose relativistic jets point nearly along our line of sight, are \
among the brightest persistent sources in the gamma-ray sky and are candidate sources of \
high-energy cosmic neutrinos.

The SIMBAD database aggregates classifications from thousands of publications, providing a \
heterogeneous but broadly representative census of known AGN. This catalog is useful for \
cross-matching with multi-wavelength surveys, selecting targets for spectroscopic follow-up, \
and building training sets for machine-learning classification of AGN from photometric data.
"""


def main():
    print("Fetching quasar/AGN catalog from SIMBAD...")

    resp = requests.get(SIMBAD_TAP, params={
        "REQUEST": "doQuery",
        "LANG": "ADQL",
        "FORMAT": "csv",
        "QUERY": ADQL,
    }, timeout=300)
    resp.raise_for_status()

    df = pd.read_csv(io.StringIO(resp.text))
    print(f"  {len(df)} objects from SIMBAD")

    df = df.rename(columns={
        "name": "name",
        "ra": "ra_deg",
        "dec": "dec_deg",
        "object_type": "object_type",
    })

    # Deduplicate (multiple redshift measurements)
    df = df.drop_duplicates("name", keep="first")

    # Readable AGN category
    type_map = {
        "QSO": "Quasar",
        "AGN": "Active Galactic Nucleus",
        "Sy1": "Seyfert 1",
        "Sy2": "Seyfert 2",
        "BLL": "BL Lac Object",
        "Bla": "Blazar",
        "LIN": "LINER",
    }
    df["agn_category"] = df["object_type"].map(type_map).fillna(df["object_type"])

    # Keep only described columns
    df = df[[c for c in df.columns if c in COLUMN_DESCRIPTIONS]]

    df = df.sort_values("name").reset_index(drop=True)

    # Stats
    n = len(df)
    n_qso = int((df["object_type"] == "QSO").sum())
    n_agn = int((df["object_type"] == "AGN").sum())
    n_seyfert = int(df["object_type"].isin(["Sy1", "Sy2"]).sum())
    n_blazar = int(df["object_type"].isin(["BLL", "Bla"]).sum())
    n_liner = int((df["object_type"] == "LIN").sum())

    quick_stats = f"""\
- **{n:,}** objects total
- **{n_qso:,}** quasars (QSO)
- **{n_seyfert:,}** Seyfert galaxies (Sy1 + Sy2)
- **{n_blazar:,}** blazars / BL Lac objects
- **{n_agn:,}** general AGN
- **{n_liner:,}** LINERs"""

    usage = """\
```python
from datasets import load_dataset

ds = load_dataset("juliensimon/quasar-catalog", split="train")
df = ds.to_pandas()

# AGN type breakdown
print(df["agn_category"].value_counts())

# Sky distribution by type
import matplotlib.pyplot as plt
for cat in ["Quasar", "Seyfert 1", "BL Lac Object"]:
    sub = df[df["agn_category"] == cat]
    plt.scatter(sub["ra_deg"], sub["dec_deg"], s=0.5, alpha=0.3, label=cat)
plt.xlabel("RA (deg)")
plt.ylabel("Dec (deg)")
plt.legend(markerscale=10)
plt.title("AGN Sky Distribution by Type")
plt.show()
```"""

    with Pipeline(
        repo=HF_REPO,
        pretty_name="Quasar & AGN Catalog",
        description=DESCRIPTION,
        tags=["space", "quasar", "agn", "blazar", "seyfert", "cosmology",
              "astronomy", "simbad", "open-data", "tabular-data", "parquet"],
        source_url="https://simbad.u-strasbg.fr/simbad/",
        task_categories=["tabular-classification"],
        collection_url="https://huggingface.co/collections/juliensimon/astronomy-datasets-69c24caf2f17e36128946743",
        banner={
            "url": "https://images-assets.nasa.gov/image/PIA12110/PIA12110~small.jpg",
            "alt": "Deep field image revealing distant galaxies and quasars",
            "credit": "NASA/ESA/STScI",
        },
        related_datasets=[
            "juliensimon/black-hole-catalog",
            "juliensimon/messier-catalog",
            "juliensimon/ngc-ic-catalog",
            "juliensimon/galaxy-clusters",
        ],
    ) as p:
        df = p.clean(
            df,
            numeric=["ra_deg", "dec_deg"],
            drop_mostly_null_threshold=0.95,
        )
        p.publish(
            df,
            filename="quasars.parquet",
            min_rows=1000,
            expected_columns=["name", "ra_deg", "dec_deg", "object_type"],
            critical_columns=["name", "ra_deg"],
            column_descriptions=COLUMN_DESCRIPTIONS,
            quick_stats=quick_stats,
            usage=usage,
            commit_message=f"Update quasar catalog: {n:,} objects",
        )
    print("Done.")


if __name__ == "__main__":
    main()
