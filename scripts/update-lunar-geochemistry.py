#!/usr/bin/env python3
"""Fetch Astromat Synthesis lunar sample geochemistry and upload to HF."""

import io
import sys
import tarfile

import pandas as pd
import requests

from hf_dataset_utils import Pipeline

# EarthChem Library download (no auth required, form POST)
DOWNLOAD_URL = "https://ecl.earthchem.org/dl_multi.php"
DOWNLOAD_PARAMS = {
    "id": "3696",
    "verifySubmit": "yes",
    "system": "ec",
    "dlFormat": "all_dataset_3696.tar.gz",
}
HF_REPO = "juliensimon/lunar-sample-geochemistry"

# Metadata columns to always keep
META_COLS = [
    "Sample Name", "Citation", "Collection", "Sample Type", "Sample SubType",
    "Analysis Type", "Analyzed Material", "Mineral", "Analysis Comment",
]

# Major oxides (weight %) — the core geochemistry measurements
MAJOR_OXIDES = [
    "SiO2", "TiO2", "Al2O3", "FeO", "FeOT", "Fe2O3", "MgO",
    "MnO", "CaO", "Na2O", "K2O", "P2O5", "Cr2O3",
]

# Key trace elements (ppm) — commonly used in lunar petrology
TRACE_ELEMENTS = [
    "Ba", "Co", "Cr", "Cu", "Ga", "Hf", "La", "Li", "Nb", "Ni",
    "Rb", "Sc", "Sr", "Ta", "Th", "U", "V", "Y", "Zn", "Zr",
    # Rare earth elements
    "Ce", "Dy", "Er", "Eu", "Gd", "Ho", "Lu", "Nd", "Pr",
    "Sm", "Tb", "Tm", "Yb",
]

# ── Column descriptions for README schema table ─────────────────────
COLUMN_DESCRIPTIONS = {
    "sample_name": "Unique sample identifier assigned by the collecting mission or laboratory (e.g. '10003,152' for Apollo 11 sample 10003, split 152)",
    "citation": "Bibliographic reference for the analysis (author, year, journal); traces each measurement to its original publication",
    "collection": "Mission or collection of origin (e.g. 'Apollo 11', 'Luna 24', 'Chang'e 5'); identifies the return mission and landing site",
    "sample_type": "Primary petrologic classification: BASALT, BRECCIA, SOIL, ROCK, GLASS, etc.; fundamental for grouping analyses by lithology",
    "sample_subtype": "Refined subtype within sample_type (e.g. 'HIGH-TI BASALT', 'ANORTHOSITE'); provides finer lithological resolution",
    "analysis_type": "Analytical technique used: XRF, EPMA, INAA, ICP-MS, wet chemistry, etc.; different methods have different precision and accuracy",
    "analyzed_material": "What was analyzed: whole rock, mineral separate, glass, matrix, clast; critical for interpreting bulk vs. phase compositions",
    "mineral": "Specific mineral phase analyzed (e.g. 'OLIVINE', 'PYROXENE', 'PLAGIOCLASE'); null for whole-rock analyses",
    "analysis_comment": "Free-text notes on the analysis (e.g. grain size, special preparation, analytical conditions); often null",
    "mission": "Derived mission name extracted from collection field: Apollo 11-17, Luna 16/20/24, or Chang'e 5; 'Other' for unresolved origins",
    "sio2_wt_pct": "Silicon dioxide (SiO2) in weight percent; the dominant oxide in silicate rocks, ranges ~38-48 wt% in lunar basalts and ~44-46 wt% in highland rocks",
    "tio2_wt_pct": "Titanium dioxide (TiO2) in weight percent; key discriminant for high-Ti (>6 wt%) vs low-Ti (<3 wt%) lunar basalts; reflects ilmenite abundance",
    "al2o3_wt_pct": "Aluminum oxide (Al2O3) in weight percent; high in plagioclase-rich highland rocks (~25-35 wt%), low in mare basalts (~8-14 wt%)",
    "feo_wt_pct": "Ferrous iron oxide (FeO) in weight percent; total iron as FeO is a primary indicator of magmatic differentiation; ranges ~15-22 wt% in basalts",
    "feot_wt_pct": "Total iron expressed as FeO (FeOT) in weight percent; combines FeO and Fe2O3 as a single ferrous equivalent for comparison across studies",
    "fe2o3_wt_pct": "Ferric iron oxide (Fe2O3) in weight percent; very low on the Moon due to reducing conditions; usually <1 wt% or below detection",
    "mgo_wt_pct": "Magnesium oxide (MgO) in weight percent; high in olivine-rich cumulates and picritic basalts; Mg# (Mg/(Mg+Fe)) tracks differentiation",
    "mno_wt_pct": "Manganese oxide (MnO) in weight percent; typically 0.2-0.3 wt% in lunar basalts; Mn/Fe ratio distinguishes lunar from terrestrial basalts",
    "cao_wt_pct": "Calcium oxide (CaO) in weight percent; abundant in plagioclase (~15-20 wt% in anorthosites); tracks plagioclase proportion",
    "na2o_wt_pct": "Sodium oxide (Na2O) in weight percent; very low on the Moon (~0.2-0.5 wt%); Na-bearing plagioclase is less common than on Earth",
    "k2o_wt_pct": "Potassium oxide (K2O) in weight percent; enriched in KREEP-bearing samples (~0.1-1 wt%); one of the defining KREEP elements",
    "p2o5_wt_pct": "Phosphorus pentoxide (P2O5) in weight percent; enriched in KREEP and late-stage differentiates; host mineral is apatite",
    "cr2o3_wt_pct": "Chromium oxide (Cr2O3) in weight percent; concentrated in chromite and pyroxene; useful for tracking crystal fractionation",
    "ba_ppm": "Barium concentration in parts per million; an incompatible lithophile element enriched in KREEP and late-stage differentiates",
    "co_ppm": "Cobalt concentration in ppm; siderophile element that partitions into metal and olivine; traces meteoritic contamination",
    "cr_ppm": "Chromium concentration in ppm; compatible in pyroxene and spinel; decreases during fractional crystallization",
    "cu_ppm": "Copper concentration in ppm; chalcophile element; traces sulfide phases and meteoritic input",
    "ga_ppm": "Gallium concentration in ppm; moderately volatile lithophile; substitutes for Al in plagioclase",
    "hf_ppm": "Hafnium concentration in ppm; high field strength element that co-varies with Zr; used in Hf isotope systematics",
    "la_ppm": "Lanthanum concentration in ppm; lightest rare earth element (LREE); enriched in KREEP (~100-200x chondrite)",
    "li_ppm": "Lithium concentration in ppm; moderately incompatible; useful for tracing late-stage magmatic processes",
    "nb_ppm": "Niobium concentration in ppm; high field strength element; Nb/Ta ratio diagnostic of source mineralogy",
    "ni_ppm": "Nickel concentration in ppm; siderophile element partitioning into metal; elevated values indicate meteoritic contamination in soils",
    "rb_ppm": "Rubidium concentration in ppm; highly incompatible alkali element; Rb/Sr ratio used for Rb-Sr isochron dating",
    "sc_ppm": "Scandium concentration in ppm; compatible in clinopyroxene; robust indicator of pyroxene fractionation",
    "sr_ppm": "Strontium concentration in ppm; substitutes for Ca in plagioclase; Sr isotopes constrain source reservoir ages",
    "ta_ppm": "Tantalum concentration in ppm; high field strength element closely associated with Nb; traces mantle source processes",
    "th_ppm": "Thorium concentration in ppm; highly incompatible heat-producing element; concentrates in KREEP; mapped globally by Lunar Prospector",
    "u_ppm": "Uranium concentration in ppm; highly incompatible radioactive element; U-Pb system provides crystallization ages; co-varies with Th",
    "v_ppm": "Vanadium concentration in ppm; redox-sensitive; V/Ti ratio varies with oxygen fugacity",
    "y_ppm": "Yttrium concentration in ppm; behaves as a heavy rare earth element; indicator of garnet involvement in source",
    "zn_ppm": "Zinc concentration in ppm; moderately volatile chalcophile; tracks volatile depletion in lunar samples",
    "zr_ppm": "Zirconium concentration in ppm; high field strength element concentrated in zircon; Zr/Hf ratio nearly constant (~35)",
    "ce_ppm": "Cerium concentration in ppm; light REE; Ce anomalies (relative to La and Pr) indicate oxidation state",
    "dy_ppm": "Dysprosium concentration in ppm; middle REE; part of the REE pattern used for petrogenetic modeling",
    "er_ppm": "Erbium concentration in ppm; heavy REE; tracks degree of HREE enrichment in source",
    "eu_ppm": "Europium concentration in ppm; unique among REE as Eu2+ substitutes into plagioclase; positive Eu anomaly = cumulate plagioclase, negative = plagioclase removal",
    "gd_ppm": "Gadolinium concentration in ppm; middle REE at the boundary between LREE and HREE; smooth in most magmatic processes",
    "ho_ppm": "Holmium concentration in ppm; heavy REE; contributes to REE pattern shape",
    "lu_ppm": "Lutetium concentration in ppm; heaviest REE; Lu-Hf isotope system dates crust formation events",
    "nd_ppm": "Neodymium concentration in ppm; light REE; Sm-Nd isotope system provides magmatic source ages; enriched in KREEP",
    "pr_ppm": "Praseodymium concentration in ppm; light REE between Ce and Nd; used to detect Ce anomalies",
    "sm_ppm": "Samarium concentration in ppm; light-to-middle REE; Sm/Nd ratio varies with degree of melting; key for Sm-Nd dating",
    "tb_ppm": "Terbium concentration in ppm; middle REE; fills the gap between Gd and Dy in REE patterns",
    "tm_ppm": "Thulium concentration in ppm; heavy REE; one of the rarest REE, often below detection limits in low-REE samples",
    "yb_ppm": "Ytterbium concentration in ppm; heavy REE; Yb/Lu ratio traces residual garnet in the source",
}

# ── Dataset description ──────────────────────────────────────────────
DESCRIPTION = """\
Geochemical analyses of lunar samples from Apollo, Luna, and Chang'e 5 missions. \
Major oxides and trace elements compiled by the Astromat/EarthChem project from \
peer-reviewed publications spanning 1970 to 2025.

Between 1969 and 2020, six Apollo missions (382 kg), three Soviet Luna missions (326 g), \
and China's Chang'e 5 mission (1.73 kg) returned samples from the Moon's surface. These \
samples — basalts, breccias, soils, and crustal rocks — have been analyzed in laboratories \
worldwide for over 50 years, producing a rich geochemical database that underpins our \
understanding of the Moon's origin, differentiation, and volcanic history.

Major oxides (SiO2, TiO2, Al2O3, FeO, MgO, CaO, etc.) in weight percent define the bulk \
composition and are used to classify lunar rock types (high-Ti basalt, low-Ti basalt, \
KREEP-rich, ferroan anorthosite). Trace elements and rare earth elements in ppm provide \
diagnostic signatures for petrogenetic processes: partial melting, fractional crystallization, \
and impact mixing.
"""


def find_value_columns(df, elements, unit_hint="wt%"):
    """Find actual value columns for given element names.

    The Astromat CSV has groups of 4 columns per measurement:
    'SiO2 (wt%) Method (comment)', 'SiO2 (wt%) Method', 'SiO2 (wt%)', 'SiO2 (wt%) Lab'
    We want the bare value columns like 'SiO2 (wt%)'.
    """
    found = {}
    for elem in elements:
        for unit in [unit_hint, "ppm", "wt%", "vol%"]:
            target = f"{elem} ({unit})"
            if target in df.columns:
                found[elem] = target
                break
        if elem not in found and elem in df.columns:
            found[elem] = elem
    return found


def main():
    print("Fetching Astromat lunar sample geochemistry...")
    resp = requests.post(DOWNLOAD_URL, data=DOWNLOAD_PARAMS, timeout=120,
                         headers={"User-Agent": "space-datasets/1.0"})
    resp.raise_for_status()
    print(f"  Downloaded {len(resp.content) / 1024 / 1024:.1f} MB")

    # Extract CSV from tar.gz
    df = None
    with tarfile.open(fileobj=io.BytesIO(resp.content), mode="r:gz") as tar:
        for member in tar.getmembers():
            if member.name.endswith(".csv"):
                print(f"  Extracting {member.name} ({member.size / 1024 / 1024:.0f} MB)")
                f = tar.extractfile(member)
                if f:
                    df = pd.read_csv(f, low_memory=False, encoding="latin-1")
                    break

    if df is None:
        print("::error::No CSV found in archive")
        sys.exit(1)

    print(f"  {len(df):,} raw rows, {len(df.columns):,} columns")

    # Strip whitespace from column names
    df.columns = df.columns.str.strip()

    # Find and select relevant columns
    meta_available = [c for c in META_COLS if c in df.columns]
    oxide_map = find_value_columns(df, MAJOR_OXIDES, unit_hint="wt%")
    trace_map = find_value_columns(df, TRACE_ELEMENTS, unit_hint="ppm")

    print(f"  Found {len(meta_available)} metadata, {len(oxide_map)} oxide, {len(trace_map)} trace columns")

    # Build the trimmed dataframe
    keep_cols = meta_available + list(oxide_map.values()) + list(trace_map.values())
    df_slim = df[keep_cols].copy()

    # Rename to clean snake_case
    rename = {}
    for c in meta_available:
        rename[c] = c.lower().replace(" ", "_")
    for elem, col in oxide_map.items():
        rename[col] = f"{elem.lower()}_wt_pct"
    for elem, col in trace_map.items():
        rename[col] = f"{elem.lower()}_ppm"

    df_slim = df_slim.rename(columns=rename)

    # Clean string columns
    for col in df_slim.select_dtypes(include=["object"]).columns:
        df_slim[col] = df_slim[col].str.strip()
        df_slim[col] = df_slim[col].replace({"": None, "nan": None})

    # Derive mission from Collection column
    if "collection" in df_slim.columns:
        def extract_mission(coll):
            if pd.isna(coll):
                return None
            coll = str(coll)
            for mission in ["Apollo 11", "Apollo 12", "Apollo 14", "Apollo 15", "Apollo 16", "Apollo 17",
                            "Luna 16", "Luna 20", "Luna 24", "Chang'e 5", "Chang'e-5"]:
                if mission.lower() in coll.lower():
                    return mission.replace("Chang'e-5", "Chang'e 5")
            return "Other"
        df_slim["mission"] = df_slim["collection"].apply(extract_mission)

    # Keep only described columns
    df_slim = df_slim[[c for c in df_slim.columns if c in COLUMN_DESCRIPTIONS]]

    # Coerce numeric columns
    numeric_cols = [c for c in df_slim.columns if c.endswith("_wt_pct") or c.endswith("_ppm")]

    df_slim = df_slim.sort_values("sample_name").reset_index(drop=True)

    # ── Domain-specific stats for README ─────────────────────────────
    n_total = len(df_slim)
    n_samples = df_slim["sample_name"].nunique() if "sample_name" in df_slim.columns else 0
    n_citations = df_slim["citation"].nunique() if "citation" in df_slim.columns else 0
    n_cols = len(df_slim.columns)

    mission_counts = {}
    if "mission" in df_slim.columns:
        mission_counts = df_slim["mission"].value_counts().to_dict()

    sample_type_counts = {}
    if "sample_type" in df_slim.columns:
        sample_type_counts = df_slim["sample_type"].value_counts().head(6).to_dict()

    sample_lines = "\n".join(
        f"| {stype} | {count:,} |"
        for stype, count in sorted(sample_type_counts.items(), key=lambda x: -x[1])
    )
    mission_lines = "\n".join(
        f"| {mission} | {count:,} |"
        for mission, count in sorted(mission_counts.items(), key=lambda x: -x[1])
    )

    quick_stats = f"""\
- **{n_total:,}** total analyses from **{n_samples:,}** unique samples
- **{n_citations}** published references
- **{n_cols}** columns (metadata + major oxides + trace elements + REEs)

## Sample types

| Type | Analyses |
|------|----------:|
{sample_lines}

## Missions

| Mission | Analyses |
|---------|----------:|
{mission_lines}"""

    usage = """\
```python
from datasets import load_dataset

ds = load_dataset("juliensimon/lunar-sample-geochemistry", split="train")
df = ds.to_pandas()

# TAS-like plot for lunar basalts
import matplotlib.pyplot as plt
basalts = df[df["sample_type"].str.contains("BASALT", na=False)]
valid = basalts.dropna(subset=["sio2_wt_pct", "tio2_wt_pct"])
plt.scatter(valid["sio2_wt_pct"], valid["tio2_wt_pct"], alpha=0.3, s=10)
plt.xlabel("SiO2 (wt%)")
plt.ylabel("TiO2 (wt%)")
plt.title("Lunar Basalt Compositions")
plt.show()

# Compare missions
print(df.groupby("mission")[["sio2_wt_pct", "feo_wt_pct", "mgo_wt_pct"]].mean())

# Filter Apollo 15 samples
a15 = df[df["mission"] == "Apollo 15"]
print(f"Apollo 15: {len(a15)} analyses")
```"""

    with Pipeline(
        repo=HF_REPO,
        pretty_name="Lunar Sample Geochemistry (Astromat Synthesis)",
        description=DESCRIPTION,
        tags=["space", "moon", "lunar", "geochemistry", "apollo",
              "astromat", "petrology", "planetary-science",
              "open-data", "tabular-data", "parquet"],
        source_url="https://doi.org/10.60520/IEDA/113696",
        task_categories=["tabular-classification", "tabular-regression"],
        collection_url="https://huggingface.co/collections/juliensimon/planetary-science-datasets-69c2d4683bd6a66c34fb4af2",
        banner={
            "url": "https://images-assets.nasa.gov/image/as08-14-2506/as08-14-2506~small.jpg",
            "alt": "The Moon seen from Apollo 8, showing craters and surface detail",
            "credit": "NASA/Apollo 8",
        },
        related_datasets=[
            "juliensimon/lunar-craters-robbins",
            "juliensimon/meteorite-database",
            "juliensimon/meteorite-landings",
            "juliensimon/planetary-nomenclature",
        ],
    ) as p:
        df_slim = p.clean(
            df_slim,
            numeric=numeric_cols,
            drop_mostly_null_threshold=0.99,
        )
        p.publish(
            df_slim,
            filename="lunar_geochemistry.parquet",
            min_rows=10_000,
            expected_columns=["sample_name"],
            critical_columns=["sample_name"],
            warn_all_nulls=0.95,
            column_descriptions=COLUMN_DESCRIPTIONS,
            quick_stats=quick_stats,
            usage=usage,
            commit_message=f"Update lunar geochemistry: {n_total:,} analyses from {n_samples:,} samples",
        )
    print("Done.")


if __name__ == "__main__":
    main()
