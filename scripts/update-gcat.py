#!/usr/bin/env python3
"""Fetch GCAT launch vehicles, engines, and stages, upload to HF.

Source: Jonathan McDowell's General Catalog of Artificial Space Objects (GCAT)
https://planet4589.org/space/gcat/
"""

import pandas as pd

from hf_dataset_utils import Pipeline
from hf_dataset_utils.banner import banner_markdown as render_banner
from hf_dataset_utils.banner import download_banner
from hf_dataset_utils.github import emit_output
from hf_dataset_utils.readme import _citation_bibtex, _size_category
from hf_dataset_utils.upload import upload_to_hf, write_parquet
from hf_dataset_utils.validation import check_dataset

LV_URL = "https://planet4589.org/space/gcat/tsv/tables/lv.tsv"
ENGINES_URL = "https://planet4589.org/space/gcat/tsv/tables/engines.tsv"
STAGES_URL = "https://planet4589.org/space/gcat/tsv/tables/stages.tsv"
HF_REPO = "juliensimon/gcat-launch-vehicles"

LV_COLS = [
    "lv_name", "lv_family", "lv_manufacturer", "lv_variant", "lv_alias",
    "lv_min_stage", "lv_max_stage", "length_m", "length_flag", "diameter_m",
    "diameter_flag", "launch_mass_t", "mass_flag", "leo_capacity_kg",
    "gto_capacity_kg", "to_thrust_kn", "class", "apogee_km", "range",
]

ENGINE_COLS = [
    "name", "manufacturer", "family", "alt_name", "oxidizer", "fuel",
    "mass_kg", "mass_flag", "impulse", "impulse_flag", "thrust_kn",
    "thrust_flag", "isp_s", "isp_flag", "duration_s", "duration_flag",
    "chambers", "date", "usage", "group",
]

STAGE_COLS = [
    "stage_name", "stage_family", "stage_manufacturer", "stage_alt_name",
    "length_m", "diameter_m", "launch_mass_t", "dry_mass_kg", "thrust_kn",
    "duration_s", "engine", "n_engines",
]

# ── Column descriptions ───────────────────────────────────────────────

VEH_COLUMN_DESCRIPTIONS = {
    "lv_name": "Full launch vehicle designation (e.g. 'Falcon 9 v1.2', 'Soyuz-2-1a'); the primary identifier combining family, variant, and version used in GCAT launch records",
    "lv_family": "Vehicle family grouping related variants (e.g. 'Falcon', 'Soyuz', 'Atlas'); useful for aggregating launch statistics across evolutionary variants",
    "lv_manufacturer": "GCAT code for the manufacturer or prime contractor (e.g. 'SpaceX', 'RKTs', 'ULA'); may refer to the current or historical builder",
    "lv_variant": "Specific variant designation within the family (e.g. 'Block 5', 'FG'); distinguishes performance upgrades, stage configurations, or customer-specific modifications",
    "lv_alias": "Alternative name or designation used in other catalogs or by different agencies; null when no common alias exists",
    "lv_min_stage": "Minimum number of stages in the vehicle's standard configuration; vehicles with optional strap-on boosters or kick stages may have a range between min and max",
    "lv_max_stage": "Maximum number of stages including optional upper stages or strap-on boosters",
    "length_m": "Overall vehicle length in meters from base to payload fairing tip; null when not publicly documented",
    "length_flag": "Qualifier on length: '~' approximate, '<' upper bound, '>' lower bound; null for exact reported values",
    "diameter_m": "Maximum core body diameter in meters (excludes strap-on boosters); standard for comparing vehicle classes",
    "diameter_flag": "Qualifier on diameter: '~' approximate, '<' upper bound, '>' lower bound",
    "launch_mass_t": "Total launch mass in metric tonnes including propellant, structure, and payload; null for many sounding rockets and older vehicles",
    "mass_flag": "Qualifier on launch mass: '~' approximate, '<' upper bound, '>' lower bound",
    "leo_capacity_kg": "Maximum payload mass to low Earth orbit (typically 200 km circular) in kg; the standard metric for comparing launch vehicle capability; null for suborbital-only vehicles",
    "gto_capacity_kg": "Maximum payload mass to geostationary transfer orbit in kg; typically 40-60% of LEO capacity; null for vehicles not designed for GTO missions",
    "to_thrust_kn": "Total liftoff thrust of all first-stage engines plus boosters in kilonewtons; determines the vehicle's thrust-to-weight ratio at launch",
    "class": "Vehicle class code: O = orbital, R = research/sounding rocket, I = intercontinental ballistic missile test, T = test vehicle; determines whether the vehicle is designed to reach orbit",
    "apogee_km": "Design or typical apogee altitude in km for suborbital vehicles; null for orbital-class vehicles where apogee depends on the mission",
    "range": "Operational range designation or notes; may indicate sounding rocket altitude range or ICBM range class",
}

ENG_COLUMN_DESCRIPTIONS = {
    "name": "Engine designation (e.g. 'Merlin 1D', 'RD-180', 'RS-25'); the primary identifier used in engineering references and GCAT stage records",
    "manufacturer": "GCAT code for the engine manufacturer (e.g. 'SpaceX', 'Energomash', 'Aerojet Rocketdyne')",
    "family": "Engine family grouping related variants (e.g. 'Merlin', 'RD-170/180', 'RL-10'); engines in a family share core design heritage",
    "alt_name": "Alternative designation or export name for the engine; null when no alias is commonly used",
    "oxidizer": "Oxidizer propellant type: LOX (liquid oxygen), NTO (nitrogen tetroxide), IRFNA (inhibited red fuming nitric acid), AP (ammonium perchlorate for solids), etc.",
    "fuel": "Fuel propellant type: RP-1 (refined kerosene), LH2 (liquid hydrogen), UDMH (unsymmetrical dimethylhydrazine), HTPB (hydroxyl-terminated polybutadiene for solids), etc.",
    "mass_kg": "Dry mass of the engine assembly in kg (without propellant); null for many engines where mass is not publicly disclosed",
    "mass_flag": "Qualifier on mass: '~' approximate, '<' upper bound, '>' lower bound",
    "impulse": "Total impulse in kN-s (thrust x burn time); a measure of the engine's total energy delivery; null when not reported",
    "impulse_flag": "Qualifier on impulse: '~' approximate, '<' upper bound, '>' lower bound",
    "thrust_kn": "Vacuum or sea-level thrust in kilonewtons; the primary performance metric for comparing engines; thrust specification (vac vs SL) varies by source",
    "thrust_flag": "Qualifier on thrust: '~' approximate, '<' upper bound, '>' lower bound; 'v' for vacuum, 's' for sea-level",
    "isp_s": "Specific impulse in seconds -- the key efficiency metric for rocket engines; higher Isp means more delta-v per kg of propellant; LOX/LH2 engines achieve 420-460 s, LOX/kerosene 280-340 s, solids 230-280 s",
    "isp_flag": "Qualifier on specific impulse: '~' approximate, 'v' vacuum, 's' sea-level",
    "duration_s": "Nominal burn duration in seconds; ranges from a few seconds for solid boosters to 500+ s for upper-stage cryogenic engines",
    "duration_flag": "Qualifier on duration: '~' approximate, '<' upper bound, '>' lower bound",
    "chambers": "Number of combustion chambers; most engines have 1, but some (e.g. RD-170) have 2 or 4 chambers fed by a single turbopump assembly",
    "date": "Date of first known use or test firing; may be approximate (year only) for older or classified engines",
    "usage": "Description of vehicle applications where this engine is or was used (e.g. 'Falcon 9 first stage', 'Atlas V')",
    "group": "Propellant group classification: Liquid, Solid, Hybrid, Cold Gas, Electric, Nuclear; determines the engine's operational characteristics and performance envelope",
}

STG_COLUMN_DESCRIPTIONS = {
    "stage_name": "Stage designation (e.g. 'Falcon 9 v1.2 S1', 'Centaur V'); identifies the specific stage assembly within a launch vehicle stack",
    "stage_family": "Stage family grouping related variants (e.g. 'Centaur', 'Briz-M'); stages in a family share structural heritage",
    "stage_manufacturer": "GCAT code for the stage manufacturer or integrator",
    "stage_alt_name": "Alternative designation for the stage; null when no common alias exists",
    "length_m": "Stage length in meters excluding interstage adapters; null when not publicly documented",
    "diameter_m": "Stage body diameter in meters; typically matches the core vehicle diameter",
    "launch_mass_t": "Stage mass at launch in metric tonnes including propellant; the key parameter for mass-ratio and delta-v calculations",
    "dry_mass_kg": "Stage dry mass (empty, no propellant) in kg; combined with launch mass, determines the mass ratio (key to delta-v via the Tsiolkovsky equation)",
    "thrust_kn": "Total stage thrust in kilonewtons from all engines; may differ from individual engine thrust when multiple engines are clustered",
    "duration_s": "Nominal burn duration in seconds for the stage",
    "engine": "Engine name used in this stage; cross-references the engines table for detailed propulsion specifications",
    "n_engines": "Number of engines powering this stage; e.g. 9 for Falcon 9 first stage, 1 for most upper stages",
}

# ── Dataset description ──────────────────────────────────────────────

DESCRIPTION = """\
Launch vehicle specifications, rocket engines, and vehicle stages from Jonathan McDowell's \
General Catalog of Artificial Space Objects (GCAT) at the Harvard-Smithsonian Center for \
Astrophysics. GCAT is the most comprehensive open reference for spaceflight hardware.

The vehicle table covers the full spectrum of rocketry, from small sounding rockets to \
super-heavy orbital launch vehicles. Key parameters like LEO and GTO payload capacity, \
liftoff thrust, and physical dimensions enable quantitative comparison across vehicle \
families. The engine table catalogs specific impulse (a measure of fuel efficiency), \
thrust levels, propellant combinations (LOX/kerosene, LOX/LH2, hypergolic, solid), and \
burn durations for engines spanning seven decades of development. The stage table connects \
engines to their vehicle applications, documenting how many engines power each stage and \
the stage-level mass fractions that determine overall vehicle performance.

These tables support a range of analyses: comparing launch vehicle economics (cost per \
kilogram to orbit), studying propulsion technology trends over time, assessing launch \
provider capabilities for mission planning, and building physics-based models of launch \
vehicle performance.
"""


def _schema_section(title, descriptions):
    """Generate a markdown schema table from column descriptions dict."""
    lines = [f"### {title}", "", "| Column | Description |", "|--------|-------------|"]
    for col, desc in descriptions.items():
        lines.append(f"| `{col}` | {desc} |")
    return "\n".join(lines)


def _fetch_tsv(url, col_names, label):
    """Fetch a GCAT TSV, assign column names, clean up."""
    print(f"Fetching {label}...")
    df = pd.read_csv(url, sep="\t", comment="#", names=col_names,
                     low_memory=False, skipinitialspace=True)
    for col in df.select_dtypes(include="object").columns:
        df[col] = df[col].str.strip()
    df.replace("-", pd.NA, inplace=True)
    print(f"  {len(df):,} {label}")
    return df


def main():
    # ── Fetch ────────────────────────────────────────────────────────────
    vehicles = _fetch_tsv(LV_URL, LV_COLS, "launch vehicles")
    engines = _fetch_tsv(ENGINES_URL, ENGINE_COLS, "engines")
    stages = _fetch_tsv(STAGES_URL, STAGE_COLS, "stages")

    # ── Coerce numeric columns ───────────────────────────────────────────
    veh_numeric = [
        "lv_min_stage", "lv_max_stage", "length_m", "diameter_m",
        "launch_mass_t", "leo_capacity_kg", "gto_capacity_kg",
        "to_thrust_kn", "apogee_km",
    ]
    eng_numeric = [
        "mass_kg", "impulse", "thrust_kn", "isp_s", "duration_s", "chambers",
    ]
    stg_numeric = [
        "length_m", "diameter_m", "launch_mass_t", "dry_mass_kg",
        "thrust_kn", "duration_s", "n_engines",
    ]
    for col in veh_numeric:
        if col in vehicles.columns:
            vehicles[col] = pd.to_numeric(vehicles[col], errors="coerce")
    for col in eng_numeric:
        if col in engines.columns:
            engines[col] = pd.to_numeric(engines[col], errors="coerce")
    for col in stg_numeric:
        if col in stages.columns:
            stages[col] = pd.to_numeric(stages[col], errors="coerce")

    # ── Keep only described columns ──────────────────────────────────────
    vehicles = vehicles[[c for c in vehicles.columns if c in VEH_COLUMN_DESCRIPTIONS]]
    engines = engines[[c for c in engines.columns if c in ENG_COLUMN_DESCRIPTIONS]]
    stages = stages[[c for c in stages.columns if c in STG_COLUMN_DESCRIPTIONS]]

    # ── Validate ─────────────────────────────────────────────────────────
    total_rows = len(vehicles) + len(engines) + len(stages)

    check_dataset(vehicles, "vehicles", min_rows=500,
                  expected_columns=["lv_name", "lv_family", "lv_manufacturer", "class"],
                  critical_columns=["lv_name"])
    check_dataset(engines, "engines", min_rows=500,
                  expected_columns=["name", "manufacturer", "thrust_kn", "isp_s"],
                  critical_columns=["name"])
    check_dataset(stages, "stages", min_rows=500,
                  expected_columns=["stage_name", "stage_family", "engine", "n_engines"],
                  critical_columns=["stage_name"])

    # ── Stats for README ─────────────────────────────────────────────────
    n_families = vehicles["lv_family"].nunique()
    n_manufacturers = vehicles["lv_manufacturer"].nunique()
    n_engine_groups = engines["group"].nunique() if "group" in engines.columns else 0
    median_isp = engines["isp_s"].median()
    max_thrust = engines["thrust_kn"].max()

    quick_stats = f"""\
- **{len(vehicles):,}** launch vehicle variants across **{n_families}** families
- **{len(engines):,}** engines from **{n_manufacturers}** manufacturers
- **{len(stages):,}** stage configurations
- **{n_engine_groups}** propellant groups (solid, liquid, hybrid, etc.)
- Median specific impulse: **{median_isp:.0f} s**, max thrust: **{max_thrust:,.0f} kN**"""

    usage = """\
```python
from datasets import load_dataset

vehicles = load_dataset("juliensimon/gcat-launch-vehicles", "vehicles", split="train")
engines = load_dataset("juliensimon/gcat-launch-vehicles", "engines", split="train")
stages = load_dataset("juliensimon/gcat-launch-vehicles", "stages", split="train")

vdf = vehicles.to_pandas()

# Largest launch vehicles by mass
print(vdf.nlargest(10, "launch_mass_t")[["lv_name", "launch_mass_t", "leo_capacity_kg"]])

# Engines by specific impulse
edf = engines.to_pandas()
print(edf.nlargest(10, "isp_s")[["name", "fuel", "oxidizer", "isp_s", "thrust_kn"]])

# Thrust vs Isp scatter by propellant group
import matplotlib.pyplot as plt
for grp in ["Liquid", "Solid"]:
    sub = edf[edf["group"] == grp].dropna(subset=["thrust_kn", "isp_s"])
    plt.scatter(sub["isp_s"], sub["thrust_kn"], label=grp, alpha=0.6)
plt.xlabel("Specific Impulse (s)")
plt.ylabel("Thrust (kN)")
plt.legend()
plt.title("Rocket Engine Performance: Thrust vs Isp")
plt.show()
```"""

    # ── Build multi-config dataset ───────────────────────────────────────
    with Pipeline(
        repo=HF_REPO,
        pretty_name="GCAT Launch Vehicles and Engines",
        description="",  # custom README below
        tags=[],
        source_url="https://planet4589.org/space/gcat/",
        collection_url="https://huggingface.co/collections/juliensimon/orbital-mechanics-datasets-69c24caca4ab3934c9856994",
        banner={
            "url": "https://images-assets.nasa.gov/image/iss071e439624/iss071e439624~medium.jpg",
            "alt": "An orbital sunrise illuminates the Earth's atmosphere, seen from the ISS",
            "credit": "NASA",
        },
    ) as p:
        write_parquet(vehicles, p.data_dir / "vehicles.parquet")
        write_parquet(engines, p.data_dir / "engines.parquet")
        write_parquet(stages, p.data_dir / "stages.parquet")

        # Banner
        banner_file = download_banner(p.banner["url"], p.tmp_dir)
        banner_md = render_banner(
            p.banner["alt"], p.banner["credit"], filename=banner_file,
        ) if banner_file else ""

        veh_schema = _schema_section("Vehicles schema", VEH_COLUMN_DESCRIPTIONS)
        eng_schema = _schema_section("Engines schema", ENG_COLUMN_DESCRIPTIONS)
        stg_schema = _schema_section("Stages schema", STG_COLUMN_DESCRIPTIONS)

        readme = f"""---
license: cc-by-4.0
pretty_name: "GCAT Launch Vehicles and Engines"
language:
  - en
description: "Launch vehicle specs, rocket engines, and stage data from GCAT. {total_rows:,} records across three tables."
task_categories:
  - tabular-classification
tags:
  - space
  - rockets
  - launch-vehicles
  - engines
  - orbital-mechanics
  - open-data
  - gcat
  - tabular-data
  - parquet
size_categories:
  - {_size_category(total_rows)}
configs:
  - config_name: vehicles
    data_files:
      - split: train
        path: data/vehicles.parquet
    default: true
  - config_name: engines
    data_files:
      - split: train
        path: data/engines.parquet
  - config_name: stages
    data_files:
      - split: train
        path: data/stages.parquet
---

# GCAT Launch Vehicles and Engines
{banner_md}
*Part of a [dataset collection](https://huggingface.co/collections/juliensimon/orbital-mechanics-datasets-69c24caca4ab3934c9856994) on Hugging Face.*

## Dataset description

{DESCRIPTION}

## Configs

| Config | Records | Description |
|--------|---------|-------------|
| `vehicles` | **{len(vehicles):,}** | Launch vehicle variants with physical specs and payload capacity |
| `engines` | **{len(engines):,}** | Rocket engine specifications, propellants, and performance |
| `stages` | **{len(stages):,}** | Stage configurations linking engines to vehicles |

{veh_schema}

{eng_schema}

{stg_schema}

## Quick stats

{quick_stats}

## Usage

{usage}

## Data source

[GCAT](https://planet4589.org/space/gcat/) (General Catalog of Artificial Space Objects)
by Jonathan McDowell, Harvard-Smithsonian Center for Astrophysics.

## Related datasets

- [juliensimon/space-launch-log](https://huggingface.co/datasets/juliensimon/space-launch-log)
- [juliensimon/space-track-satcat](https://huggingface.co/datasets/juliensimon/space-track-satcat)
- [juliensimon/starlink-fleet-data](https://huggingface.co/datasets/juliensimon/starlink-fleet-data)

## Citation

{_citation_bibtex(HF_REPO, "GCAT Launch Vehicles and Engines")}

## License

[CC-BY-4.0](https://creativecommons.org/licenses/by/4.0/)
"""
        (p.tmp_dir / "README.md").write_text(readme)

        upload_to_hf(
            HF_REPO, p.tmp_dir,
            f"Update GCAT launch vehicles: {len(vehicles):,} vehicles, "
            f"{len(engines):,} engines, {len(stages):,} stages",
        )

    emit_output(rows=total_rows)
    print(f"Done. {total_rows:,} total rows.")


if __name__ == "__main__":
    main()
