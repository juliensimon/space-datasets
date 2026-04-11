#!/usr/bin/env python3
"""Fetch Nesvorny HCM Asteroid Families (V2.0) from PDS SBN and upload to HF.

Source: PDS Small Bodies Node (sbnarchive.psi.edu)
~170K asteroids grouped into 274 dynamical families from collision events.
Combines the original 2015 families (119) with 153 new families from 2024.
"""

import io
import re
import zipfile
from pathlib import Path

import pandas as pd
import requests

from hf_dataset_utils import Pipeline

ZIP_URL = "https://sbnarchive.psi.edu/pds4/non_mission/ast.nesvorny.families_V2_0.zip"
HF_REPO = "juliensimon/nesvorny-asteroid-families"

# Fixed-width spec for families_2015/*.tab (72-byte records)
FW_2015_COLSPECS = [
    (0, 6),    # ast_number
    (7, 14),   # a_prop
    (15, 23),  # e_prop
    (24, 32),  # sin_i_prop
    (33, 38),  # abs_mag
    (39, 47),  # c_param
    (48, 51),  # family_number
    (52, 70),  # family_name
]
FW_2015_NAMES = [
    "asteroid_number", "proper_a_au", "proper_e", "sin_i",
    "abs_mag", "c_param", "family_number", "family_name",
]

# Fixed-width spec for familylist.tab
FW_FAMLIST_COLSPECS = [
    (0, 3),    # family_number
    (4, 22),   # family_name
    (23, 26),  # distance_cutoff
    (27, 34),  # member_count
    (35, 41),  # prop_a_min
    (42, 48),  # prop_a_max
    (49, 55),  # prop_e_min
    (56, 62),  # prop_e_max
    (63, 68),  # prop_i_min
    (69, 74),  # prop_i_max
    (75, 76),  # no_file_flag
]
FW_FAMLIST_NAMES = [
    "family_number", "family_name", "distance_cutoff_ms",
    "member_count", "prop_a_min_au", "prop_a_max_au",
    "prop_e_min", "prop_e_max", "prop_i_min_deg", "prop_i_max_deg",
    "no_file_flag",
]

# CSV columns for families_2024/*.csv (no header row)
CSV_2024_NAMES = [
    "proper_a_au", "proper_e", "sin_i",
    "freq_g_arcsec_yr", "freq_s_arcsec_yr",
    "abs_mag", "n_oppositions", "packed_name", "unpacked_name",
]

COLUMN_DESCRIPTIONS = {
    "asteroid_number": "MPC catalog number (positive integer); null for unnumbered objects identified only by provisional designation",
    "proper_a_au": "Proper semimajor axis in AU; time-averaged, perturbation-free equivalent of osculating semi-major axis; range ~1.7-5.3 AU across the full catalog",
    "proper_e": "Proper eccentricity (dimensionless, 0-1); time-averaged, perturbation-free; used as one of the three clustering axes",
    "sin_i": "Sine of proper inclination (dimensionless, 0-1); used instead of inclination itself to linearise the HCM distance metric",
    "abs_mag": "Absolute magnitude H in magnitudes; used as a proxy for asteroid size (smaller H = larger object); null for a small fraction of entries",
    "c_param": "Interloper identification parameter from Nesvorny (2015); positive values indicate likely true family members, negative suggest interlopers; null for 2024-catalog entries",
    "freq_g_arcsec_yr": "Proper precession frequency of the pericenter longitude g in arcsec/yr; provides an additional dynamical discriminant beyond (a, e, sin i); null for all 2015-catalog entries",
    "freq_s_arcsec_yr": "Proper precession frequency of the nodal longitude s in arcsec/yr; used together with freq_g to resolve family overlaps in the inner belt; null for all 2015-catalog entries",
    "n_oppositions": "Number of observed oppositions recorded in the MPC database; proxy for orbit quality; null for all 2015-catalog entries",
    "packed_name": "MPC packed-format designation (e.g., 'K04A00A'); null for 2015-catalog entries",
    "unpacked_name": "MPC human-readable name or provisional designation (e.g., '2004 AA'); null for 2015-catalog entries",
    "family_number": "Nesvorny catalog family identifier (integer); e.g., 4 = Vesta family, 10 = Hygiea family; stable across catalog versions for 2015 families",
    "family_name": "Name of the family, typically the name of its largest member (e.g., 'Vesta', 'Flora', 'Themis')",
    "region": "Main-belt region: inner (~2.0-2.5 AU), middle (~2.5-2.82 AU), outer (~2.82-3.28 AU), hilda_hungaria, highinclination, phocaea, or other",
    "source": "Catalog epoch: '2015' (original Nesvorny et al. 2015 families) or '2024' (newly identified families from 2024 update)",
}

DESCRIPTION = """\
Asteroid families are groups of bodies sharing similar orbits, identified as fragments from \
catastrophic collisions in the asteroid belt. This dataset contains asteroid-family memberships \
from the Nesvorny HCM (Hierarchical Clustering Method) catalog V2.0.

The dataset combines the original 2015 family identifications with 153 newly discovered families \
from the 2024 update, based on proper orbital elements for 1.25 million main-belt asteroids. \
The hierarchical clustering method groups asteroids by proximity in proper element space \
(semimajor axis, eccentricity, inclination), revealing the collisional history of the solar system.

Families span the entire asteroid belt: inner belt (Flora, Vesta), middle belt (Eunomia, \
Koronis), outer belt (Themis, Eos, Hygiea), plus Hilda, Hungaria, Phocaea, and \
high-inclination populations.

Asteroid families are the fossil record of catastrophic collisions in the main belt. When a large \
asteroid is struck by a projectile at several kilometers per second, the resulting impact can \
shatter the target body and disperse thousands to millions of fragments into nearby orbits. Over \
time, these fragments spread along the parent body's original orbit due to differences in ejection \
velocity, creating a cluster of objects that share similar proper orbital elements.

The age of an asteroid family can be estimated from the dispersion of its members in semimajor \
axis. Immediately after formation, fragments cluster tightly around the parent body's orbit; \
over time, the Yarkovsky effect causes small members to drift inward or outward in semimajor \
axis, producing a characteristic V-shaped signature when plotting absolute magnitude against \
semimajor axis.
"""


def parse_family_from_filename_2024(fname: str) -> tuple[str, int, str]:
    """Extract region, family number, and family name from a 2024 CSV filename."""
    stem = Path(fname).stem
    stem = re.sub(r"_fam\d+$", "", stem)
    m = re.match(r"^([a-z]+)_(\d+)_(.+)$", stem)
    if m:
        region = m.group(1)
        fam_num = int(m.group(2))
        fam_name = m.group(3).replace("_", " ")
        return region, fam_num, fam_name
    return "unknown", 0, stem


def extract_asteroid_number(unpacked: str) -> int | None:
    """Try to extract a numeric asteroid number from the unpacked name field."""
    if pd.isna(unpacked):
        return None
    s = str(unpacked).strip()
    if s.isdigit():
        return int(s)
    return None


def main():
    # ── 1. Download ZIP archive ──────────────────────────────────────────
    print("Downloading Nesvorny Asteroid Families V2.0 archive...")
    resp = requests.get(ZIP_URL, timeout=300)
    resp.raise_for_status()
    print(f"  Downloaded {len(resp.content) / 1024 / 1024:.1f} MB")

    zdata = io.BytesIO(resp.content)

    # ── 2. Parse family list ─────────────────────────────────────────────
    with zipfile.ZipFile(zdata) as zf:
        famlist_path = [n for n in zf.namelist() if n.endswith("familylist.tab")][0]
        with zf.open(famlist_path) as f:
            famlist = pd.read_fwf(
                f, colspecs=FW_FAMLIST_COLSPECS, names=FW_FAMLIST_NAMES,
                dtype={"family_number": "Int64"},
            )
        famlist["family_name"] = famlist["family_name"].str.strip()
        famlist["no_file_flag"] = famlist["no_file_flag"].str.strip()
        print(f"  Family list: {len(famlist)} families")

        fam_lookup = dict(zip(famlist["family_number"], famlist["family_name"]))

        # ── 3. Parse families_2015 .tab files ────────────────────────────
        tab_files = sorted([
            n for n in zf.namelist()
            if "/families_2015/" in n and n.endswith(".tab")
        ])
        print(f"  Parsing {len(tab_files)} families_2015 .tab files...")

        frames_2015 = []
        for tf in tab_files:
            try:
                with zf.open(tf) as f:
                    part = pd.read_fwf(
                        f, colspecs=FW_2015_COLSPECS, names=FW_2015_NAMES,
                    )
                    part["family_name"] = part["family_name"].str.strip()
                    part["source"] = "2015"
                    frames_2015.append(part)
            except Exception as e:
                print(f"    Warning: skipped {tf} ({e})")

        df_2015 = pd.concat(frames_2015, ignore_index=True) if frames_2015 else pd.DataFrame()
        print(f"    2015 families: {len(df_2015):,} asteroid-family memberships")

        # ── 4. Parse families_2024 .csv files ────────────────────────────
        csv_files = sorted([
            n for n in zf.namelist()
            if "/families_2024/" in n and n.endswith(".csv")
        ])
        print(f"  Parsing {len(csv_files)} families_2024 .csv files...")

        frames_2024 = []
        for cf in csv_files:
            try:
                with zf.open(cf) as f:
                    part = pd.read_csv(f, header=None, names=CSV_2024_NAMES)
                    region, fam_num, fam_name = parse_family_from_filename_2024(
                        Path(cf).name
                    )
                    part["family_number"] = fam_num
                    official = fam_lookup.get(fam_num)
                    if official:
                        part["family_name"] = official
                    else:
                        display_name = fam_name.title() if not fam_name[0].isdigit() else fam_name
                        part["family_name"] = f"{fam_num} {display_name}" if fam_num > 0 else display_name
                    part["region"] = region
                    part["asteroid_number"] = part["unpacked_name"].apply(
                        extract_asteroid_number
                    )
                    part["source"] = "2024"
                    frames_2024.append(part)
            except Exception as e:
                print(f"    Warning: skipped {cf} ({e})")

        df_2024 = pd.concat(frames_2024, ignore_index=True) if frames_2024 else pd.DataFrame()
        print(f"    2024 families: {len(df_2024):,} asteroid-family memberships")

    # ── 5. Unify schema and combine ──────────────────────────────────────
    for col in ["freq_g_arcsec_yr", "freq_s_arcsec_yr"]:
        if col not in df_2015.columns:
            df_2015[col] = float("nan")
    for col in ["n_oppositions"]:
        if col not in df_2015.columns:
            df_2015[col] = pd.array([pd.NA] * len(df_2015), dtype="Int64")
    for col in ["packed_name", "unpacked_name", "region"]:
        if col not in df_2015.columns:
            df_2015[col] = pd.NA
    if "c_param" not in df_2024.columns:
        df_2024["c_param"] = float("nan")

    def region_from_family_number(fnum):
        if pd.isna(fnum):
            return "unknown"
        fnum = int(fnum)
        if 1 <= fnum <= 10:
            return "hilda_hungaria"
        if 401 <= fnum <= 417:
            return "inner"
        if 501 <= fnum <= 541:
            return "middle"
        if 601 <= fnum <= 641:
            return "outer"
        if 701 <= fnum <= 701:
            return "phocaea"
        if 801 <= fnum <= 807:
            return "highinclination"
        if 901 <= fnum <= 905:
            return "outer"
        return "other"

    df_2015["region"] = df_2015["family_number"].apply(region_from_family_number)

    final_cols = [
        "asteroid_number", "proper_a_au", "proper_e", "sin_i",
        "abs_mag", "c_param",
        "freq_g_arcsec_yr", "freq_s_arcsec_yr",
        "n_oppositions", "packed_name", "unpacked_name",
        "family_number", "family_name", "region", "source",
    ]
    df = pd.concat([df_2015[final_cols], df_2024[final_cols]], ignore_index=True)
    print(f"  Combined: {len(df):,} rows")

    df["region"] = df["region"].replace({"highi": "highinclination"})

    # ── 6. Type coercion ─────────────────────────────────────────────────
    for col in ["proper_a_au", "proper_e", "sin_i", "abs_mag", "c_param",
                "freq_g_arcsec_yr", "freq_s_arcsec_yr"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    df["asteroid_number"] = pd.to_numeric(df["asteroid_number"], errors="coerce").astype("Int64")
    df["family_number"] = pd.to_numeric(df["family_number"], errors="coerce").astype("Int64")
    df["n_oppositions"] = pd.to_numeric(df["n_oppositions"], errors="coerce").astype("Int64")

    df["c_param"] = df["c_param"].replace(-99.9999, pd.NA)

    for col in ["family_name", "packed_name", "unpacked_name", "region", "source"]:
        if col in df.columns:
            df[col] = df[col].astype(str).str.strip().replace({"<NA>": pd.NA, "nan": pd.NA})

    # Keep only described columns
    df = df[[c for c in df.columns if c in COLUMN_DESCRIPTIONS]]

    # ── 7. Stats ─────────────────────────────────────────────────────────
    n_total = len(df)
    n_families = df["family_number"].nunique()
    n_from_2015 = int((df["source"] == "2015").sum())
    n_from_2024 = int((df["source"] == "2024").sum())
    n_numbered = int(df["asteroid_number"].notna().sum())
    a_min = df["proper_a_au"].min()
    a_max = df["proper_a_au"].max()

    print(f"  {n_total:,} total memberships across {n_families} families")
    print(f"  {n_from_2015:,} from 2015 catalog, {n_from_2024:,} from 2024 catalog")
    print(f"  {n_numbered:,} with numbered asteroid IDs")
    print(f"  Proper semimajor axis range: {a_min:.4f} - {a_max:.4f} AU")

    quick_stats = f"""\
- **{n_total:,}** asteroid-family memberships across **{n_families}** families
- {n_from_2015:,} from 2015 catalog, {n_from_2024:,} from 2024 catalog
- {n_numbered:,} with numbered asteroid IDs
- Proper semimajor axis range: {a_min:.4f} -- {a_max:.4f} AU"""

    usage = """\
```python
from datasets import load_dataset

ds = load_dataset("juliensimon/nesvorny-asteroid-families", split="train")
df = ds.to_pandas()

# Largest families
top = df.groupby("family_name").size().sort_values(ascending=False).head(10)
print(top)

# Plot families in proper element space
import matplotlib.pyplot as plt
fig, ax = plt.subplots(figsize=(12, 6))
for name, grp in df.groupby("family_name"):
    if len(grp) > 1000:
        ax.scatter(grp["proper_a_au"], grp["sin_i"], s=0.1, alpha=0.3, label=name)
ax.set_xlabel("Proper semimajor axis (AU)")
ax.set_ylabel("sin(i)")
ax.legend(markerscale=20, fontsize=8)
plt.title("Major Asteroid Families in Proper Element Space")
plt.show()
```"""

    with Pipeline(
        repo=HF_REPO,
        pretty_name="Nesvorny Asteroid Families (HCM V2.0)",
        description=DESCRIPTION,
        tags=["space", "asteroids", "families", "collisions", "orbital-mechanics",
              "open-data", "tabular-data", "parquet"],
        source_url="https://sbn.psi.edu/pds/resource/nesvornyfam.html",
        task_categories=["tabular-classification", "tabular-regression"],
        collection_url="https://huggingface.co/collections/juliensimon/orbital-mechanics-datasets-69c24caca4ab3934c9856994",
        banner={
            "url": "https://images-assets.nasa.gov/image/PIA17666/PIA17666~small.jpg",
            "alt": "Rosetta spacecraft approaching Comet 67P/Churyumov-Gerasimenko",
            "credit": "NASA/ESA",
        },
        related_datasets=[
            "juliensimon/jpl-small-body-database",
            "juliensimon/bus-demeo-asteroid-taxonomy",
            "juliensimon/asterank-asteroid-mining",
        ],
    ) as p:
        df = p.clean(
            df,
            numeric=[
                "proper_a_au", "proper_e", "sin_i", "abs_mag", "c_param",
                "freq_g_arcsec_yr", "freq_s_arcsec_yr",
            ],
            drop_mostly_null_threshold=0.95,
        )
        p.publish(
            df,
            filename="nesvorny_asteroid_families.parquet",
            min_rows=150_000,
            expected_columns=[
                "asteroid_number", "proper_a_au", "proper_e", "sin_i",
                "abs_mag", "family_number", "family_name",
            ],
            critical_columns=["proper_a_au", "proper_e", "sin_i", "family_number"],
            column_descriptions=COLUMN_DESCRIPTIONS,
            quick_stats=quick_stats,
            usage=usage,
            commit_message=f"Update Nesvorny asteroid families: {n_total:,} members in {n_families} families",
        )
    print("Done.")


if __name__ == "__main__":
    main()
