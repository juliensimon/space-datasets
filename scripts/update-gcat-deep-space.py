#!/usr/bin/env python3
"""Fetch GCAT deep space objects and planetary landings, upload to HF.

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

DEEP_URL = "https://planet4589.org/space/gcat/tsv/cat/deepcat.tsv"
LANDER_URL = "https://planet4589.org/space/gcat/tsv/cat/landercat.tsv"
HF_REPO = "juliensimon/gcat-deep-space"

DEEP_COLS = [
    "jcat", "satcat", "launch_tag", "piece", "type", "name", "pl_name",
    "ldate", "parent", "sdate", "primary", "ddate", "status", "dest",
    "owner", "state", "manufacturer", "bus", "motor", "mass", "mass_flag",
    "dry_mass", "dry_flag", "tot_mass", "tot_flag", "length", "l_flag",
    "diameter", "d_flag", "span", "span_flag", "shape", "odate", "perigee",
    "pf", "apogee", "af", "inc", "if_flag", "op_orbit", "oqual", "alt_names",
]

LANDER_COLS = [
    "jcat", "piece", "name", "owner", "state", "world", "lon", "lat",
    "ltype", "status", "launch_date", "land_date", "off_date", "dur",
    "lsite", "comment",
]

# ── Column descriptions ───────────────────────────────────────────────

DEEP_COLUMN_DESCRIPTIONS = {
    "jcat": "GCAT deep space catalog ID (e.g. 'D00001'); unique identifier for every object that has traveled beyond cislunar space or entered heliocentric orbit",
    "satcat": "NORAD/Space Force catalog number if tracked; 'NNA' if no US military tracking number was assigned (common for non-US deep space objects)",
    "launch_tag": "GCAT launch event identifier linking this object to its originating launch in the launch log",
    "piece": "COSPAR international designator (YYYY-NNNX format) identifying the specific piece from a given launch",
    "type": "Object type code: P = payload (operational spacecraft), R = rocket body (upper stage/booster), C = component (adapter, shroud, debris)",
    "name": "Primary name or tracking designation of the object",
    "pl_name": "Operational payload name assigned by the owner/operator; null for rocket bodies and components",
    "ldate": "Launch date in ISO format; the date the parent mission left Earth",
    "parent": "JCAT identifier of the parent object from which this piece separated; null for primary payloads",
    "sdate": "Separation date from parent object in ISO format; null if the object is the primary payload or separation date is unknown",
    "primary": "Primary gravitational body the object orbits: Sun (heliocentric), Moon, Mars, Venus, Jupiter, Saturn, etc.",
    "ddate": "Date the object entered deep space or escaped Earth orbit; marks transition from cislunar to interplanetary space",
    "status": "Current disposition code: O = in orbit, I = impacted, L = landed, E = escaped solar system, D = deorbited, A = active",
    "dest": "Destination or target body: Luna, Mars, Venus, Jupiter, Saturn, HCO (heliocentric orbit), Escape (leaving solar system), etc.",
    "owner": "GCAT code for the owning organization or space agency (e.g. 'NASA', 'ROSCOSMOS', 'ESA', 'JAXA')",
    "state": "Country/state code of the responsible nation (e.g. 'US', 'RU', 'CN', 'JP', 'EU')",
    "manufacturer": "GCAT code for the organization that built the object",
    "bus": "Spacecraft bus or platform model (e.g. 'MRO', 'Mars Express'); null when not publicly known",
    "motor": "Propulsion motor designation for rocket bodies or spacecraft with onboard propulsion",
    "mass": "Mass of the object in kg at launch; null when not publicly reported",
    "mass_flag": "Qualifier on mass: '~' approximate, '<' upper bound, '>' lower bound",
    "dry_mass": "Dry mass (no propellant) in kg; null for most objects where dry mass is not separately reported",
    "dry_flag": "Qualifier on dry mass: '~' approximate, '<' upper bound, '>' lower bound",
    "tot_mass": "Total mass including all attached hardware in kg; null when not reported",
    "tot_flag": "Qualifier on total mass: '~' approximate, '<' upper bound, '>' lower bound",
    "length": "Length of the object in meters; null for most objects where dimensions are not cataloged",
    "l_flag": "Qualifier on length: '~' approximate, '<' upper bound, '>' lower bound",
    "diameter": "Maximum cross-sectional diameter in meters; null when not publicly known",
    "d_flag": "Qualifier on diameter: '~' approximate, '<' upper bound, '>' lower bound",
    "span": "Maximum span including deployable structures (solar arrays, antennas) in meters",
    "span_flag": "Qualifier on span: '~' approximate, '<' upper bound, '>' lower bound",
    "shape": "Geometric shape description (e.g. 'box', 'cyl', 'sphere'); used for identification and modeling",
    "odate": "Epoch date for the orbital elements in perigee, apogee, and inclination columns",
    "perigee": "Periapsis altitude in km at the reference epoch; meaning depends on the primary body (periselene for Moon, periareion for Mars)",
    "pf": "Qualifier on perigee: '~' approximate, '<' upper bound, '>' lower bound",
    "apogee": "Apoapsis altitude in km at the reference epoch; for heliocentric objects this is the aphelion distance",
    "af": "Qualifier on apogee: '~' approximate, '<' upper bound, '>' lower bound",
    "inc": "Orbital inclination in degrees relative to the primary body's equatorial plane",
    "if_flag": "Qualifier on inclination: '~' approximate, '<' upper bound, '>' lower bound",
    "op_orbit": "Operational orbit type classification (e.g. 'HCO' for heliocentric, 'Lunar', 'Mars orbit')",
    "oqual": "Orbit determination quality indicator reflecting confidence in the orbital elements",
    "alt_names": "Pipe-separated list of alternative names, previous designations, or synonyms",
}

LANDER_COLUMN_DESCRIPTIONS = {
    "jcat": "GCAT deep space catalog ID linking to the deep space objects table; enables cross-referencing with spacecraft specifications",
    "piece": "COSPAR international designator (YYYY-NNNX format) for the landing object",
    "name": "Name of the landing craft or impacting object (e.g. 'Apollo 11 LM', 'Huygens', 'Chang'e 5')",
    "owner": "GCAT code for the owning organization or space agency",
    "state": "Country/state code of the responsible nation",
    "world": "Target world where landing/impact occurred: Luna, Mars, Venus, Titan, Eros, Ryugu, Bennu, Itokawa, etc.",
    "lon": "Landing/impact longitude in degrees on the target body's surface; null when location is unknown or the object was destroyed during entry",
    "lat": "Landing/impact latitude in degrees on the target body's surface; null when location is unknown",
    "ltype": "Landing type code: L = controlled landing, I = impact (intentional or crash), LA = landing attempt (failed), F = flyby deployment",
    "status": "Outcome status: L = successfully landed, I = impacted, C = crashed, F = failed to reach surface, S = survived impact",
    "launch_date": "Launch date of the mission in ISO format",
    "land_date": "Date and time of landing or impact in ISO format; null if the event date is uncertain",
    "off_date": "End-of-mission date on the surface; null if the lander is still operating or if loss-of-signal date is unknown",
    "dur": "Surface operations duration in days; ranges from 0 (impact-only) to 14+ years for long-lived rovers; null when unknown",
    "lsite": "Landing site name if formally designated (e.g. 'Tranquility Base', 'Utopia Planitia', 'Huygens Landing Site')",
    "comment": "Mission notes including landing details, scientific objectives, or failure descriptions",
}

# ── Dataset description ──────────────────────────────────────────────

DESCRIPTION = """\
Deep space spacecraft and planetary/lunar landings from Jonathan McDowell's \
General Catalog of Artificial Space Objects (GCAT) at the Harvard-Smithsonian \
Center for Astrophysics.

The deep space catalog lists every spacecraft, rocket stage, and component that has \
traveled beyond cislunar space or entered a heliocentric orbit, from the pioneering \
Luna and Pioneer missions of 1959 to modern interplanetary probes. It includes mission \
metadata, physical specifications (mass, dimensions, shape), orbital parameters, and \
current status for each object.

The planetary landings catalog records every intentional and unintentional contact with \
another world -- soft landings, hard impacts, controlled crashes, and flyby probe \
deployments. The data spans the full international history of planetary exploration, \
from Soviet Luna and Venera missions, NASA's Surveyor and Apollo landings, ESA's Huygens \
descent to Titan, Japan's Hayabusa asteroid sample returns, China's Chang'e lunar program, \
and India's Chandrayaan missions.

Together these tables enable analysis of interplanetary mission trends, success rates by \
nation and decade, the geographic distribution of lunar landing sites, and the evolution \
of deep space spacecraft design over six decades.
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
    deep = _fetch_tsv(DEEP_URL, DEEP_COLS, "deep space objects")
    landers = _fetch_tsv(LANDER_URL, LANDER_COLS, "planetary landings")

    # ── Coerce numeric columns ───────────────────────────────────────────
    for col in ["mass", "dry_mass", "tot_mass", "length", "diameter", "span",
                "perigee", "apogee", "inc"]:
        if col in deep.columns:
            deep[col] = pd.to_numeric(deep[col], errors="coerce")
    for col in ["lon", "lat", "dur"]:
        if col in landers.columns:
            landers[col] = pd.to_numeric(landers[col], errors="coerce")

    # ── Keep only described columns ──────────────────────────────────────
    deep = deep[[c for c in deep.columns if c in DEEP_COLUMN_DESCRIPTIONS]]
    landers = landers[[c for c in landers.columns if c in LANDER_COLUMN_DESCRIPTIONS]]

    # ── Validate ─────────────────────────────────────────────────────────
    total_rows = len(deep) + len(landers)

    check_dataset(deep, "deep_space_objects", min_rows=500,
                  expected_columns=["jcat", "name", "state", "dest", "status"],
                  critical_columns=["jcat", "name"])
    check_dataset(landers, "planetary_landings", min_rows=200,
                  expected_columns=["jcat", "name", "world", "land_date", "status"],
                  critical_columns=["jcat", "name"])

    # ── Stats for README ─────────────────────────────────────────────────
    n_deep_states = deep["state"].nunique()
    n_dests = deep["dest"].nunique()
    n_lander_worlds = landers["world"].nunique()
    world_counts = landers["world"].value_counts()
    ltype_counts = landers["ltype"].value_counts()
    n_landings = int(ltype_counts.get("L", 0))
    n_impacts = int(ltype_counts.get("I", 0))

    quick_stats = f"""\
- **{len(deep):,}** deep space objects from **{n_deep_states}** countries/entities
- **{n_dests}** distinct destinations
- **{len(landers):,}** planetary landings on **{n_lander_worlds}** worlds
- **{n_landings}** successful landings, **{n_impacts}** impacts
- Landings by world: {', '.join(f'{w} ({c})' for w, c in world_counts.head(6).items())}"""

    usage = """\
```python
from datasets import load_dataset

deep = load_dataset("juliensimon/gcat-deep-space", "deep_space_objects", split="train")
landings = load_dataset("juliensimon/gcat-deep-space", "planetary_landings", split="train")

ddf = deep.to_pandas()

# Spacecraft by destination
print(ddf["dest"].value_counts().head(10))

# Payloads only (exclude rocket bodies and components)
payloads = ddf[ddf["type"].str.startswith("P", na=False)]
print(f"{len(payloads)} payload objects")

# Planetary landings by world
ldf = landings.to_pandas()

# Plot landing sites on the Moon
import matplotlib.pyplot as plt
lunar = ldf[(ldf["world"] == "Luna") & ldf["lon"].notna()]
plt.scatter(lunar["lon"], lunar["lat"], c="steelblue", alpha=0.7, s=20)
plt.xlabel("Longitude")
plt.ylabel("Latitude")
plt.title("Lunar Landing and Impact Sites")
plt.show()
```"""

    # ── Build multi-config dataset ───────────────────────────────────────
    with Pipeline(
        repo=HF_REPO,
        pretty_name="GCAT Deep Space Objects and Planetary Landings",
        description="",  # custom README below
        tags=[],
        source_url="https://planet4589.org/space/gcat/",
        collection_url="https://huggingface.co/collections/juliensimon/space-probe-and-mission-datasets-69c3fe82d410a42b1e313167",
        banner={
            "url": "https://images-assets.nasa.gov/image/PIA14111/PIA14111~small.jpg",
            "alt": "Voyager spacecraft artist concept",
            "credit": "NASA/JPL-Caltech",
        },
    ) as p:
        write_parquet(deep, p.data_dir / "deep_space_objects.parquet")
        write_parquet(landers, p.data_dir / "planetary_landings.parquet")

        # Banner
        banner_file = download_banner(p.banner["url"], p.tmp_dir)
        banner_md = render_banner(
            p.banner["alt"], p.banner["credit"], filename=banner_file,
        ) if banner_file else ""

        deep_schema = _schema_section("Deep space objects schema", DEEP_COLUMN_DESCRIPTIONS)
        lander_schema = _schema_section("Planetary landings schema", LANDER_COLUMN_DESCRIPTIONS)

        readme = f"""---
license: cc-by-4.0
pretty_name: "GCAT Deep Space Objects and Planetary Landings"
language:
  - en
description: "Interplanetary spacecraft and planetary/lunar landings from GCAT. {total_rows:,} records across two tables."
task_categories:
  - tabular-classification
tags:
  - space
  - deep-space
  - interplanetary
  - planetary-landings
  - lunar-landings
  - gcat
  - solar-system
  - spacecraft
  - open-data
  - tabular-data
  - parquet
size_categories:
  - {_size_category(total_rows)}
configs:
  - config_name: deep_space_objects
    data_files:
      - split: train
        path: data/deep_space_objects.parquet
    default: true
  - config_name: planetary_landings
    data_files:
      - split: train
        path: data/planetary_landings.parquet
---

# GCAT Deep Space Objects and Planetary Landings
{banner_md}
*Part of a [dataset collection](https://huggingface.co/collections/juliensimon/space-probe-and-mission-datasets-69c3fe82d410a42b1e313167) on Hugging Face.*

## Dataset description

{DESCRIPTION}

## Configs

| Config | Records | Description |
|--------|---------|-------------|
| `deep_space_objects` | **{len(deep):,}** | Every spacecraft and component that has traveled beyond Earth orbit |
| `planetary_landings` | **{len(landers):,}** | Lunar and planetary landings and impacts |

{deep_schema}

{lander_schema}

## Quick stats

{quick_stats}

## Usage

{usage}

## Data source

[GCAT](https://planet4589.org/space/gcat/) (General Catalog of Artificial Space Objects)
by Jonathan McDowell, Harvard-Smithsonian Center for Astrophysics.

## Related datasets

- [juliensimon/space-missions](https://huggingface.co/datasets/juliensimon/space-missions)
- [juliensimon/spacecraft-database](https://huggingface.co/datasets/juliensimon/spacecraft-database)
- [juliensimon/gcat-satellite-catalog](https://huggingface.co/datasets/juliensimon/gcat-satellite-catalog)
- [juliensimon/deep-space-probes](https://huggingface.co/datasets/juliensimon/deep-space-probes)

## Citation

{_citation_bibtex(HF_REPO, "GCAT Deep Space Objects and Planetary Landings")}

## License

[CC-BY-4.0](https://creativecommons.org/licenses/by/4.0/)
"""
        (p.tmp_dir / "README.md").write_text(readme)

        upload_to_hf(
            HF_REPO, p.tmp_dir,
            f"Update GCAT deep space: {len(deep):,} objects, {len(landers):,} landings",
        )

    emit_output(rows=total_rows)
    print(f"Done. {total_rows:,} total rows.")


if __name__ == "__main__":
    main()
