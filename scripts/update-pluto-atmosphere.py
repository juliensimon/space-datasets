#!/usr/bin/env python3
"""Fetch New Horizons Pluto atmospheric profiles from PDS and upload to HF."""

import io
import sys

import pandas as pd
import requests

from hf_dataset_utils import Pipeline
from hf_dataset_utils.banner import banner_markdown as render_banner
from hf_dataset_utils.banner import download_banner
from hf_dataset_utils.github import emit_output
from hf_dataset_utils.readme import _citation_bibtex
from hf_dataset_utils.upload import upload_to_hf, write_parquet
from hf_dataset_utils.validation import check_dataset

PDS_BASE = "https://pds-smallbodies.astro.umd.edu/holdings/pds4-nh_derived:plutosystem_atmospherics-v1.0"

# REX radio occultation temperature/pressure profiles
REX_FILES = {
    f"{PDS_BASE}/rexatmos/nh_pluto_rex_profile_entry.tab": "rex_entry",
    f"{PDS_BASE}/rexatmos/nh_pluto_rex_profile_exit.tab": "rex_exit",
}

# Alice UV atmospheric composition (abundance mixing ratios)
ALICE_FILES = {
    f"{PDS_BASE}/atmoscomp/pocc_abund_pds.csv": "alice_abundance",
    f"{PDS_BASE}/atmoscomp/pocc_dens_pds.csv": "alice_density",
}

# Haze brightness profiles
HAZE_FILES = {
    f"{PDS_BASE}/haze/azimuthal_average_profile.tab": "haze_azimuthal_avg",
}

HF_REPO = "juliensimon/pluto-atmosphere"

# REX column names (from PDS label)
REX_COLS = [
    "altitude_km", "radius_km", "longitude_deg", "latitude_deg",
    "local_solar_time_hr", "solar_zenith_angle_deg",
    "number_density_1e19_m3", "sigma_number_density",
    "pressure_pa", "sigma_pressure",
    "temperature_k", "sigma_temperature",
]

# ── Column descriptions per config ──────────────────────────────────
REX_COLUMN_DESCRIPTIONS = {
    "altitude_km": "Altitude above Pluto's surface in km; derived from radius minus reference surface radius (~1,190 km); profiles span 0-115 km",
    "radius_km": "Distance from Pluto's center in km; Pluto's mean radius is 1,188.3 km; radius = altitude + surface reference",
    "longitude_deg": "Planetocentric longitude of the occultation ray tangent point in degrees East; varies along the profile as the radio beam sweeps the limb",
    "latitude_deg": "Planetocentric latitude of the occultation ray tangent point in degrees North; entry and exit profiles sample different hemispheres",
    "local_solar_time_hr": "Local solar time at the tangent point in hours (0-24); indicates day/night side sampling; affects photochemistry-driven temperature gradients",
    "solar_zenith_angle_deg": "Angle between the Sun direction and local vertical at the tangent point in degrees; controls UV heating rate; 90 deg = terminator",
    "number_density_1e19_m3": "Atmospheric number density in units of 10^19 molecules per m^3; dominated by N2; decreases exponentially with altitude",
    "sigma_number_density": "1-sigma uncertainty on number density in same units; increases at higher altitudes where signal-to-noise decreases",
    "pressure_pa": "Atmospheric pressure in pascals; surface pressure ~1.1 Pa (11 microbar), ~10^5 times thinner than Earth's atmosphere",
    "sigma_pressure": "1-sigma uncertainty on pressure in pascals; derived from the Abel inversion of refractivity data",
    "temperature_k": "Atmospheric temperature in kelvins; ranges ~38-110 K; shows a strong temperature inversion above the surface",
    "sigma_temperature": "1-sigma uncertainty on temperature in kelvins; typically 1-5 K near the surface, increasing at higher altitudes",
    "profile": "Occultation geometry identifier: 'rex_entry' (ingress) or 'rex_exit' (egress); entry and exit probe different locations on Pluto's limb",
    "instrument": "Instrument name: 'REX' (Radio Science Experiment); uses X-band (7.18 GHz) uplink radio occultation",
    "measurement_type": "Type of measurement: 'temperature_pressure' for REX profiles; distinguishes from composition or haze data",
}

ALICE_COLUMN_DESCRIPTIONS = {
    "profile": "Data product identifier: 'alice_abundance' (mixing ratios) or 'alice_density' (number densities); from solar and stellar occultations",
    "instrument": "Instrument name: 'Alice' UV imaging spectrometer; covers 52-187 nm; performs solar and stellar occultation measurements",
}

HAZE_COLUMN_DESCRIPTIONS = {
    "radius_km": "Distance from Pluto's center in km at which the haze brightness is measured; haze extends from surface to ~350 km altitude",
    "i_over_f": "Haze brightness as I/F (intensity relative to solar flux); dimensionless; measures scattered sunlight by photochemical haze particles",
    "uncertainty": "1-sigma uncertainty on I/F; derived from pixel-to-pixel scatter in the azimuthal average; increases at low altitudes",
    "profile": "Profile identifier: 'haze_azimuthal_avg'; azimuthally averaged to improve signal-to-noise over single radial cuts",
    "instrument": "Instrument name: 'LORRI/MVIC'; Long Range Reconnaissance Imager and Multispectral Visible Imaging Camera",
    "measurement_type": "Type of measurement: 'haze_brightness'; scattered sunlight from Pluto's extensive photochemical haze layers",
}

# ── Dataset description ──────────────────────────────────────────────
DESCRIPTION = """\
The only direct measurements of Pluto's atmosphere, obtained during NASA's New Horizons \
flyby on July 14, 2015. Includes vertical profiles of temperature, pressure, and number \
density from the REX radio occultation experiment, atmospheric composition (N2, CH4, C2H2, \
C2H4, C2H6, haze) from the Alice UV spectrometer, and haze brightness profiles from imaging.

When New Horizons flew past Pluto at 13.78 km/s, it performed two critical atmospheric \
experiments. The REX instrument used radio occultation to derive temperature and pressure \
as a function of altitude. The Alice UV spectrometer observed solar and stellar occultations, \
measuring absorption signatures of nitrogen, methane, acetylene, ethylene, ethane, and \
photochemical haze.

Pluto's atmosphere is tenuous (surface pressure ~1 Pa, vs. Earth's 101,325 Pa) and primarily \
composed of nitrogen, with trace methane and carbon monoxide. It undergoes dramatic seasonal \
changes as Pluto's eccentric orbit causes surface ices to sublime and refreeze over its \
248-year orbital period.
"""


def fetch_tab(url, name, columns=None):
    """Fetch a PDS .tab or .csv file."""
    print(f"  Fetching {name}...")
    resp = requests.get(url, timeout=60, headers={"User-Agent": "space-datasets/1.0"})
    resp.raise_for_status()
    text = resp.text.strip()
    if not text:
        return pd.DataFrame()

    first_line = text.split("\n")[0]
    has_header = any(c.isalpha() for c in first_line.split(",")[0])
    if has_header:
        df = pd.read_csv(io.StringIO(text))
    else:
        df = pd.read_csv(io.StringIO(text), header=None)

    if columns and len(df.columns) == len(columns):
        df.columns = columns

    df = df.loc[:, df.columns.notna()]
    df["profile"] = name
    print(f"    {len(df)} rows, {len(df.columns)} columns")
    return df


def main():
    print("Fetching New Horizons Pluto atmospheric profiles from PDS...")

    # ── REX temperature/pressure profiles ─────────────────────────────
    rex_frames = []
    for url, name in REX_FILES.items():
        try:
            df = fetch_tab(url, name, columns=REX_COLS)
            if len(df) > 0:
                rex_frames.append(df)
        except Exception as e:
            print(f"    Failed {name}: {e}")

    if rex_frames:
        df_rex = pd.concat(rex_frames, ignore_index=True)
        df_rex["instrument"] = "REX"
        df_rex["measurement_type"] = "temperature_pressure"
        print(f"  REX: {len(df_rex)} total rows")
    else:
        df_rex = pd.DataFrame()

    # ── Alice composition profiles ────────────────────────────────────
    alice_frames = []
    for url, name in ALICE_FILES.items():
        try:
            df = fetch_tab(url, name)
            if len(df) > 0:
                alice_frames.append(df)
        except Exception as e:
            print(f"    Failed {name}: {e}")

    if alice_frames:
        df_alice = pd.concat(alice_frames, ignore_index=True)
        df_alice["instrument"] = "Alice"
        print(f"  Alice: {len(df_alice)} total rows")
    else:
        df_alice = pd.DataFrame()

    # ── Haze profiles ─────────────────────────────────────────────────
    haze_frames = []
    for url, name in HAZE_FILES.items():
        try:
            df = fetch_tab(url, name)
            if len(df) > 0:
                haze_frames.append(df)
        except Exception as e:
            print(f"    Failed {name}: {e}")

    if haze_frames:
        df_haze = pd.concat(haze_frames, ignore_index=True)
        df_haze["instrument"] = "LORRI/MVIC"
        df_haze["measurement_type"] = "haze_brightness"
        print(f"  Haze: {len(df_haze)} total rows")
    else:
        df_haze = pd.DataFrame()

    # ── Write parquet files and build README ─────────────────────────
    with Pipeline(
        repo=HF_REPO,
        pretty_name="Pluto Atmospheric Profiles (New Horizons)",
        description=DESCRIPTION,
        tags=["space", "pluto", "atmosphere", "new-horizons",
              "planetary-science", "nasa", "pds",
              "open-data", "tabular-data", "parquet"],
        source_url="https://doi.org/10.26007/z5wm-yt67",
        task_categories=["tabular-regression"],
        collection_url="https://huggingface.co/collections/juliensimon/solar-system-datasets-69c6fa681978de62dff2f347",
        banner={
            "url": "https://images-assets.nasa.gov/image/PIA19952/PIA19952~small.jpg",
            "alt": "Pluto in enhanced color, captured by NASA's New Horizons spacecraft",
            "credit": "NASA/Johns Hopkins APL/SwRI",
        },
        related_datasets=[
            "juliensimon/huygens-titan-atmosphere",
            "juliensimon/galileo-jupiter-atmosphere",
            "juliensimon/solar-system-moons",
        ],
    ) as p:
        total_rows = 0
        configs_yaml = ""
        config_table_rows = ""
        n_rex = n_alice = n_haze = 0

        if len(df_rex) > 0:
            # Clean REX: replace fill values
            for col in df_rex.select_dtypes(include=["float64", "int64"]).columns:
                df_rex.loc[df_rex[col] >= 1e29, col] = None

            write_parquet(df_rex, p.data_dir / "rex_profiles.parquet")
            n_rex = len(df_rex)
            total_rows += n_rex
            configs_yaml += """  - config_name: rex_profiles
    data_files:
      - split: train
        path: data/rex_profiles.parquet
    default: true
"""
            config_table_rows += f"| `rex_profiles` | {n_rex} | Temperature, pressure, and number density vs. altitude (entry + exit occultations) |\n"

        if len(df_alice) > 0:
            for col in df_alice.select_dtypes(include=["float64", "int64"]).columns:
                df_alice.loc[df_alice[col] >= 1e29, col] = None

            df_alice.columns = (
                df_alice.columns.str.strip()
                .str.lower()
                .str.replace(r"[() /]", "_", regex=True)
                .str.replace(r"_+", "_", regex=True)
                .str.strip("_")
            )

            write_parquet(df_alice, p.data_dir / "alice_composition.parquet")
            n_alice = len(df_alice)
            total_rows += n_alice
            configs_yaml += """  - config_name: alice_composition
    data_files:
      - split: train
        path: data/alice_composition.parquet
"""
            config_table_rows += f"| `alice_composition` | {n_alice} | Atmospheric mixing ratios and number densities of N2, CH4, C2H2, C2H4, C2H6, haze |\n"

        if len(df_haze) > 0:
            data_cols = [c for c in df_haze.columns if c not in ("profile", "instrument", "measurement_type")]
            if len(data_cols) == 3:
                col_map = dict(zip(data_cols, ["radius_km", "i_over_f", "uncertainty"]))
                df_haze = df_haze.rename(columns=col_map)

            for col in df_haze.select_dtypes(include=["float64", "int64"]).columns:
                df_haze.loc[df_haze[col] >= 1e29, col] = None

            write_parquet(df_haze, p.data_dir / "haze_profiles.parquet")
            n_haze = len(df_haze)
            total_rows += n_haze
            configs_yaml += """  - config_name: haze_profiles
    data_files:
      - split: train
        path: data/haze_profiles.parquet
"""
            config_table_rows += f"| `haze_profiles` | {n_haze} | Azimuthally averaged haze I/F brightness vs. altitude |\n"

        if total_rows == 0:
            print("::error::No data fetched")
            sys.exit(1)

        print(f"  Total: {total_rows} rows across tables")

        # Validate all configs
        if n_rex > 0:
            check_dataset(
                df_rex,
                dataset_name="pluto-atmosphere/rex",
                min_rows=10,
                expected_columns=["altitude_km", "temperature_k", "pressure_pa"],
                critical_columns=["altitude_km"],
            )
        if n_alice > 0:
            check_dataset(
                df_alice,
                dataset_name="pluto-atmosphere/alice",
                min_rows=5,
                expected_columns=["profile", "instrument"],
                critical_columns=["profile"],
            )
        if n_haze > 0:
            check_dataset(
                df_haze,
                dataset_name="pluto-atmosphere/haze",
                min_rows=5,
                expected_columns=["radius_km", "i_over_f"],
                critical_columns=["radius_km"],
            )

        # Banner
        banner_file = download_banner(p.banner["url"], p.tmp_dir)
        banner_md = render_banner(
            p.banner["alt"], p.banner["credit"],
            filename=banner_file,
        ) if banner_file else ""

        # REX stats for quick_stats
        rex_alt_min = df_rex["altitude_km"].min() if n_rex > 0 else 0
        rex_alt_max = df_rex["altitude_km"].max() if n_rex > 0 else 0
        rex_temp_min = df_rex["temperature_k"].min() if n_rex > 0 else 0
        rex_temp_max = df_rex["temperature_k"].max() if n_rex > 0 else 0

        # Schema sections
        rex_schema_rows = "\n".join(
            f"| `{col}` | {df_rex[col].dtype} | {REX_COLUMN_DESCRIPTIONS.get(col, '')} |"
            for col in df_rex.columns
            if col in REX_COLUMN_DESCRIPTIONS
        ) if n_rex > 0 else ""

        alice_schema_rows = "\n".join(
            f"| `{col}` | {df_alice[col].dtype} | {ALICE_COLUMN_DESCRIPTIONS.get(col, '')} |"
            for col in df_alice.columns
            if col in ALICE_COLUMN_DESCRIPTIONS
        ) if n_alice > 0 else ""

        haze_schema_rows = "\n".join(
            f"| `{col}` | {df_haze[col].dtype} | {HAZE_COLUMN_DESCRIPTIONS.get(col, '')} |"
            for col in df_haze.columns
            if col in HAZE_COLUMN_DESCRIPTIONS
        ) if n_haze > 0 else ""

        readme = f"""---
license: cc-by-4.0
pretty_name: "Pluto Atmospheric Profiles (New Horizons)"
language:
  - en
description: "Pluto atmospheric profiles from the New Horizons flyby (July 2015). Temperature, pressure, composition (N2, CH4, C2H2), and haze from REX and Alice."
task_categories:
  - tabular-regression
tags:
  - space
  - pluto
  - atmosphere
  - new-horizons
  - planetary-science
  - nasa
  - pds
  - open-data
  - tabular-data
  - parquet
size_categories:
  - n<1K
configs:
{configs_yaml}---

# Pluto Atmospheric Profiles (New Horizons)
{banner_md}
*Part of the [Solar System Datasets](https://huggingface.co/collections/juliensimon/solar-system-datasets-69c6fa681978de62dff2f347) collection on Hugging Face.*

{DESCRIPTION.strip()}

## Data tables

| Config | Rows | Description |
|--------|-----:|-------------|
{config_table_rows.strip()}

## REX profile schema

| Column | Type | Description |
|--------|------|-------------|
{rex_schema_rows}

## Alice composition schema

| Column | Type | Description |
|--------|------|-------------|
{alice_schema_rows}

## Haze profile schema

| Column | Type | Description |
|--------|------|-------------|
{haze_schema_rows}

## Quick stats (REX)

- Altitude range: {rex_alt_min:.0f} -- {rex_alt_max:.0f} km above surface
- Temperature range: {rex_temp_min:.0f} -- {rex_temp_max:.0f} K
- Two profiles: entry (ingress) and exit (egress) occultation

## Usage

```python
from datasets import load_dataset

# Load REX temperature/pressure profiles
rex = load_dataset("juliensimon/pluto-atmosphere", "rex_profiles", split="train")
df = rex.to_pandas()

# Plot Pluto's atmospheric temperature profile
import matplotlib.pyplot as plt
entry = df[df["profile"] == "rex_entry"]
exit_ = df[df["profile"] == "rex_exit"]
plt.plot(entry["temperature_k"], entry["altitude_km"], label="Entry")
plt.plot(exit_["temperature_k"], exit_["altitude_km"], label="Exit")
plt.xlabel("Temperature (K)")
plt.ylabel("Altitude (km)")
plt.title("Pluto Atmospheric Temperature Profile (New Horizons REX)")
plt.legend()
plt.show()

# Load composition data
alice = load_dataset("juliensimon/pluto-atmosphere", "alice_composition", split="train")
```

## Data source

New Horizons Derived Pluto System Atmospherics, PDS Small Bodies Node:
[doi:10.26007/z5wm-yt67](https://doi.org/10.26007/z5wm-yt67)

- Hinson et al. (2017), *Radio occultation measurements of Pluto's neutral atmosphere with New Horizons*, Icarus 290.
- Young et al. (2018), *Structure and composition of Pluto's atmosphere from the New Horizons solar ultraviolet occultation*, Icarus 300.

## Related datasets

- [Huygens Titan Atmosphere](https://huggingface.co/datasets/juliensimon/huygens-titan-atmosphere)
- [Galileo Jupiter Atmosphere](https://huggingface.co/datasets/juliensimon/galileo-jupiter-atmosphere)
- [Solar System Moons](https://huggingface.co/datasets/juliensimon/solar-system-moons)

## Pipeline

Source code: [juliensimon/space-datasets](https://github.com/juliensimon/space-datasets)

{_citation_bibtex(HF_REPO, "Pluto Atmospheric Profiles (New Horizons)")}

## License

[CC-BY-4.0](https://creativecommons.org/licenses/by/4.0/)
"""
        (p.tmp_dir / "README.md").write_text(readme)

        upload_to_hf(
            HF_REPO, p.tmp_dir,
            f"Update Pluto atmosphere: {total_rows} measurements from New Horizons",
        )

    emit_output(rows=total_rows)
    print("Done.")


if __name__ == "__main__":
    main()
