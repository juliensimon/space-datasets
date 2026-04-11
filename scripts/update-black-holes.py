#!/usr/bin/env python3
"""Fetch known black hole systems from SIMBAD and upload to HF.

Source: SIMBAD astronomical database — confirmed black holes, candidates,
and X-ray binaries (BH, BH?, XB*, HXB, LXB object types).
"""

import io

import pandas as pd
import requests

from hf_dataset_utils import Pipeline

HF_REPO = "juliensimon/black-hole-catalog"

SIMBAD_TAP = "https://simbad.u-strasbg.fr/simbad/sim-tap/sync"

# SIMBAD otypes: BH = black hole, BH? = BH candidate, XB* = X-ray binary,
# HXB = High-mass XRB, LXB = Low-mass XRB
ADQL = """SELECT main_id AS name, ra, dec, otype_txt AS object_type, sp_type AS spectral_type
FROM basic
WHERE otype_txt = 'BH' OR otype_txt = 'BH?' OR otype_txt = 'XB*' OR otype_txt = 'HXB' OR otype_txt = 'LXB'
ORDER BY main_id"""

# ── Column descriptions for README schema table ─────────────────────
COLUMN_DESCRIPTIONS = {
    "name": "Primary SIMBAD identifier or common name (e.g. 'Cyg X-1', 'GRS 1915+105'); the canonical designation used in the astronomical literature for cross-matching",
    "ra_deg": "ICRS J2000.0 right ascension in degrees (0-360); useful for positional cross-matching with X-ray, radio, and optical surveys",
    "dec_deg": "ICRS J2000.0 declination in degrees (-90 to +90)",
    "object_type": "SIMBAD classification code: 'BH' = confirmed black hole, 'BH?' = black hole candidate awaiting definitive mass measurement, 'XB*' = generic X-ray binary, 'HXB' = high-mass X-ray binary (massive companion, wind accretion), 'LXB' = low-mass X-ray binary (Roche lobe overflow, often transient)",
    "bh_category": "Human-readable expansion of object_type; one of 'Confirmed Black Hole', 'Black Hole Candidate', 'X-ray Binary', 'High-Mass X-ray Binary', 'Low-Mass X-ray Binary', 'Other'",
    "spectral_type": "MK spectral classification of the companion or donor star (e.g. 'O9.7Iab' for Cyg X-1); indicates companion mass and evolutionary state; null for systems without spectroscopic data or for isolated black holes",
}

# ── Dataset description ──────────────────────────────────────────────
DESCRIPTION = """\
Catalog of known black hole systems — confirmed black holes, candidates, and \
X-ray binaries from the SIMBAD astronomical database.

Black holes are regions of spacetime where gravity is so extreme that nothing -- not even \
light -- can escape once past the event horizon. Stellar-mass black holes, the primary focus \
of this catalog, form when massive stars (typically above 20-25 solar masses) exhaust their \
nuclear fuel and undergo gravitational collapse. They are most readily detected when they exist \
in binary systems with a companion star, accreting material that heats to millions of degrees \
and emits intense X-radiation. The SIMBAD classification system distinguishes confirmed black \
holes (BH), candidates awaiting definitive mass measurements (BH?), and the X-ray binary \
systems (XB*, HXB, LXB) in which black holes are found.

The distinction between high-mass X-ray binaries (HXBs) and low-mass X-ray binaries (LXBs) \
reflects fundamentally different evolutionary pathways and accretion physics. HXBs contain \
young, massive companion stars and are powered primarily by wind accretion, while LXBs involve \
older, low-mass companions that transfer material through Roche lobe overflow, often producing \
characteristic transient outbursts separated by years of quiescence. Dynamical mass measurements \
from radial velocity curves of the companion star are the gold standard for confirming a compact \
object as a black hole -- any compact object exceeding roughly 3 solar masses (the \
Tolman-Oppenheimer-Volkoff limit for neutron stars) is classified as a black hole.

This catalog is valuable for studying the mass distribution of stellar-mass black holes, the \
spatial distribution of compact objects in the Galaxy, and the population statistics that \
constrain binary stellar evolution models. It complements the gravitational wave event catalog, \
which probes the merging population, by providing the census of black holes detected through \
electromagnetic radiation in accreting systems.
"""


def main():
    print("Fetching black hole systems from SIMBAD...")

    resp = requests.get(SIMBAD_TAP, params={
        "REQUEST": "doQuery",
        "LANG": "ADQL",
        "FORMAT": "csv",
        "QUERY": ADQL,
    }, timeout=120)
    resp.raise_for_status()

    df = pd.read_csv(io.StringIO(resp.text))
    print(f"  {len(df)} objects from SIMBAD")

    # Rename columns
    df = df.rename(columns={
        "name": "name",
        "ra": "ra_deg",
        "dec": "dec_deg",
        "object_type": "object_type",
        "spectral_type": "spectral_type",
    })

    # Deduplicate (same object may appear with multiple distance measurements)
    df = df.drop_duplicates("name", keep="first")

    # Classify BH type
    type_map = {
        "BH": "Confirmed Black Hole",
        "BH?": "Black Hole Candidate",
        "XB*": "X-ray Binary",
        "HXB": "High-Mass X-ray Binary",
        "LXB": "Low-Mass X-ray Binary",
    }
    df["bh_category"] = df["object_type"].map(type_map).fillna("Other")

    # Keep only described columns
    df = df[[c for c in df.columns if c in COLUMN_DESCRIPTIONS]]

    df = df.sort_values("name").reset_index(drop=True)

    # ── Domain-specific stats for README ─────────────────────────────
    n = len(df)
    n_confirmed = int((df["object_type"] == "BH").sum())
    n_candidate = int((df["object_type"] == "BH?").sum())
    n_xrb = int(df["object_type"].isin(["XB*", "HXB", "LXB"]).sum())

    quick_stats = f"""\
- **{n}** black hole systems total
- **{n_confirmed}** confirmed black holes
- **{n_candidate}** black hole candidates
- **{n_xrb}** X-ray binary systems hosting black hole companions"""

    usage = """\
```python
from datasets import load_dataset

ds = load_dataset("juliensimon/black-hole-catalog", split="train")
df = ds.to_pandas()

# Confirmed black holes only
confirmed = df[df["object_type"] == "BH"]
print(f"{len(confirmed)} confirmed black holes")

# By category
print(df["bh_category"].value_counts())

# Category distribution plot
import matplotlib.pyplot as plt
df["bh_category"].value_counts().plot.barh()
plt.xlabel("Count")
plt.title("Black Hole Systems by Category")
plt.tight_layout()
plt.show()
```"""

    with Pipeline(
        repo=HF_REPO,
        pretty_name="Black Hole Catalog",
        description=DESCRIPTION,
        tags=["space", "open-data", "astronomy", "black-hole", "x-ray-binary",
              "simbad", "high-energy", "tabular-data", "parquet"],
        source_url="https://simbad.u-strasbg.fr/",
        task_categories=["tabular-classification"],
        collection_url="https://huggingface.co/collections/juliensimon/astronomy-datasets-69c24caf2f17e36128946743",
        banner={
            "url": "https://images-assets.nasa.gov/image/PIA22085/PIA22085~small.jpg",
            "alt": "Artist concept of a black hole with a relativistic jet",
            "credit": "NASA/JPL-Caltech",
        },
        related_datasets=[
            "juliensimon/gravitational-wave-events",
            "juliensimon/quasar-catalog",
            "juliensimon/pulsar-catalog",
        ],
    ) as p:
        df = p.clean(
            df,
            numeric=["ra_deg", "dec_deg"],
            strings=["name", "object_type", "bh_category", "spectral_type"],
        )
        p.publish(
            df,
            filename="black_holes.parquet",
            min_rows=50,
            expected_columns=["name", "ra_deg", "dec_deg", "object_type"],
            critical_columns=["name", "ra_deg"],
            column_descriptions=COLUMN_DESCRIPTIONS,
            quick_stats=quick_stats,
            usage=usage,
            commit_message=f"Update black hole catalog: {n} systems",
        )
    print("Done.")


if __name__ == "__main__":
    main()
