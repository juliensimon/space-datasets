#!/usr/bin/env python3
"""Fetch AAVSO Variable Star Index (VSX) bulk dump and upload to HF."""

import tempfile
from pathlib import Path

import pandas as pd
import requests

from hf_dataset_utils import Pipeline

HF_REPO = "juliensimon/aavso-vsx-variable-stars"
SOURCE_URL = "https://vsx.aavso.org/external/vsx_csv.dat.gz"

# -- Column mapping --------------------------------------------------------
RENAME = {
    "#OID": "aavso_uid",
    "Name": "name",
    "VarFlag": "var_flag",
    "RAdeg": "ra_deg",
    "DEdeg": "dec_deg",
    "Type": "variable_type",
    "LimitFlagOnMax": "limit_flag_max",
    "MagMax": "mag_max",
    "MaxUncertaintyFlag": "mag_max_uncertainty_flag",
    "MaxPassband": "mag_max_passband",
    "MinIsAmplitude": "min_is_amplitude",
    "LimitFlagOnMin": "limit_flag_min",
    "MagMin": "mag_min",
    "MinUncertaintyFlag": "mag_min_uncertainty_flag",
    "MinPassband": "mag_min_passband",
    "Epoch": "epoch_jd",
    "EpochUncertaintyFlag": "epoch_uncertainty_flag",
    "LimitFlagOnPeriod": "limit_flag_period",
    "Period": "period_days",
    "PeriodUncertaintyFlag": "period_uncertainty_flag",
    "SpectralType": "spectral_type",
}

# -- Column descriptions for README schema table ---------------------------
COLUMN_DESCRIPTIONS = {
    "aavso_uid": "VSX internal object ID; stable across catalog updates and cross-survey merges -- use this as the primary join key",
    "name": "Primary star designation (common name or catalog ID such as V* R Lyr or OGLE-BLG-RRLYR-00001)",
    "var_flag": "Variability confirmation status: 0 = confirmed variable, 1 = suspected variable only",
    "ra_deg": "Right ascension in the ICRS J2000.0 frame, decimal degrees (0-360)",
    "dec_deg": "Declination in the ICRS J2000.0 frame, decimal degrees (-90 to +90)",
    "variable_type": "VSX variability type code; over 100 types defined -- e.g. 'DCEP' (classical Cepheid), 'MIRA' (long-period AGB pulsator), 'EA' (Algol-type eclipsing binary), 'EB' (Beta Lyrae), 'EW' (W UMa contact binary), 'RRAB'/'RRC' (RR Lyrae subtypes), 'SR' (semiregular pulsator), 'N' (nova), 'CV' (cataclysmic variable); null if unclassified",
    "limit_flag_max": "Limit flag on maximum magnitude (e.g. '<' or '>' indicating the value is an upper/lower bound)",
    "mag_max": "Brightness at maximum light (brightest state) in the band given by mag_max_passband; lower number = brighter; null if maximum not measured",
    "mag_max_uncertainty_flag": "Uncertainty flag on maximum magnitude indicating the value is approximate or uncertain",
    "mag_max_passband": "Photometric band for mag_max (e.g. 'V', 'B', 'R', 'I', 'g', 'r')",
    "min_is_amplitude": "'Y' if mag_min stores the variability amplitude (delta-mag) rather than the absolute faint-state magnitude; check this flag before computing amplitude",
    "limit_flag_min": "Limit flag on minimum magnitude (e.g. '<' or '>' indicating the value is an upper/lower bound)",
    "mag_min": "Brightness at minimum light or, when min_is_amplitude = 'Y', the peak-to-peak amplitude (mag_min - mag_max); null if minimum not measured",
    "mag_min_uncertainty_flag": "Uncertainty flag on minimum magnitude indicating the value is approximate or uncertain",
    "mag_min_passband": "Photometric band for mag_min; usually matches mag_max_passband but may differ for some catalog entries",
    "epoch_jd": "Reference epoch of maximum or minimum brightness in Julian Date (JD); used together with period_days to predict phase at any time; null when period is unknown",
    "epoch_uncertainty_flag": "Uncertainty flag on the epoch value indicating the value is approximate",
    "limit_flag_period": "Limit flag on period (e.g. '<' or '>' indicating the value is an upper/lower bound)",
    "period_days": "Pulsation, rotation, or orbital period in days; null for irregular variables or objects without a well-determined period; range: ~0.0001 d (ultrashort Delta Sct) to thousands of days (Mira variables)",
    "period_uncertainty_flag": "Uncertainty flag on the period value indicating the value is approximate",
    "spectral_type": "MK spectral classification where available (e.g. 'M6e' for a Mira, 'A7V' for a Delta Scuti star); null for most entries not covered by spectroscopic surveys",
    "mag_range": "Derived variability amplitude in magnitudes (mag_min - mag_max when min_is_amplitude = 'N'); positive value; larger values indicate more strongly varying stars",
}

# -- Dataset description ----------------------------------------------------
DESCRIPTION = """\
The AAVSO Variable Star Index (VSX) is the most comprehensive catalog of variable stars, \
containing classifications, photometric properties, periods, and spectral types. VSX is \
maintained by the American Association of Variable Star Observers and is the standard \
reference for variable star research.

VSX aggregates variable star data from hundreds of surveys and catalogs worldwide including \
OGLE, ASAS-SN, ZTF, Gaia, and AAVSO observer submissions. Each entry represents a unique \
variable or suspected variable star with its variability type, brightness range, period (if \
known), epoch, and spectral classification.

Stellar variability is one of the richest observational windows into astrophysics. Variable \
stars span an enormous range of physical mechanisms: pulsating variables (Cepheids, RR Lyrae, \
Miras, Delta Scuti) arise from opacity-driven instabilities in stellar envelopes and obey \
period-luminosity relations that serve as standard candles for distance measurement. Eclipsing \
binaries (Algol, Beta Lyrae, W UMa types) provide the most direct method of measuring stellar \
masses and radii to percent-level precision. Eruptive variables include young T Tauri stars \
still accreting from circumstellar disks, FU Orionis outbursts, and cataclysmic variables -- \
white dwarfs accreting from close companions through Roche lobe overflow, producing dwarf \
novae and classical novae.

The diversity of variability types in VSX makes it a foundational resource for time-domain \
astronomy. Pulsating variables trace Galactic structure: RR Lyrae stars map the old halo and \
bulge populations, while classical Cepheids delineate the young disk and spiral arms. \
Long-period variables (Miras and semi-regulars) on the AGB are key tracers of intermediate-age \
populations and mass-loss processes. Rotational variables reveal starspot activity and magnetic \
cycles analogous to the solar cycle. With the advent of large time-domain surveys -- LSST/Rubin \
Observatory, TESS, and ZTF -- the number of known variables is growing rapidly, and VSX serves \
as the authoritative cross-matched index that unifies discoveries across surveys.
"""


def main():
    print("Downloading AAVSO VSX bulk dump...")
    resp = requests.get(SOURCE_URL, timeout=300, stream=True)
    resp.raise_for_status()

    # Write to temp file then read with pandas (avoids holding full response in memory)
    with tempfile.NamedTemporaryFile(suffix=".csv.gz", delete=False) as f:
        tmp_gz = f.name
        for chunk in resp.iter_content(chunk_size=8 * 1024 * 1024):
            f.write(chunk)
    print(f"  Downloaded {Path(tmp_gz).stat().st_size / 1024 / 1024:.0f} MB")

    print("Reading CSV...")
    df = pd.read_csv(
        tmp_gz,
        compression="gzip",
        dtype=str,
        keep_default_na=False,
        low_memory=False,
    )
    Path(tmp_gz).unlink()
    print(f"  {len(df):,} raw rows, {len(df.columns)} columns")

    # Rename columns
    df = df.rename(columns=RENAME)

    # Type conversions -- integer
    for col in ["aavso_uid", "var_flag"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").astype("Int64")

    # Clean up string columns -- replace empty strings with NaN
    str_cols = ["name", "variable_type", "spectral_type", "mag_max_passband",
                "mag_min_passband", "limit_flag_max", "limit_flag_min",
                "limit_flag_period", "mag_max_uncertainty_flag",
                "mag_min_uncertainty_flag", "epoch_uncertainty_flag",
                "period_uncertainty_flag", "min_is_amplitude"]
    for col in str_cols:
        if col in df.columns:
            df[col] = df[col].replace("", pd.NA).astype("string")

    # Strip surrounding quotes from spectral_type (source has e.g. "K")
    if "spectral_type" in df.columns:
        df["spectral_type"] = df["spectral_type"].str.strip('"')
        df["spectral_type"] = df["spectral_type"].replace("", pd.NA)

    # Derived: magnitude range (amplitude)
    df["mag_range"] = (df["mag_min"] - df["mag_max"]).round(3)

    # Keep only described columns
    df = df[[c for c in df.columns if c in COLUMN_DESCRIPTIONS]]

    # Sort by RA for spatial locality in parquet
    df = df.sort_values("ra_deg", na_position="last").reset_index(drop=True)

    # Stats
    n_total = len(df)
    n_with_period = int(df["period_days"].notna().sum())
    n_with_type = int(df["variable_type"].notna().sum())
    top_types = df["variable_type"].value_counts().head(10)

    print(f"  {n_with_period:,} stars with period, {n_with_type:,} with variable type")

    top_types_md = "\n".join(f"- `{t}`: {c:,}" for t, c in top_types.items())

    quick_stats = f"""\
- **{n_total:,}** variable star entries
- **{n_with_period:,}** with measured period ({n_with_period / n_total * 100:.1f}%)
- **{n_with_type:,}** with variability classification ({n_with_type / n_total * 100:.1f}%)

### Top variability types

{top_types_md}"""

    usage = """\
```python
from datasets import load_dataset

ds = load_dataset("juliensimon/aavso-vsx-variable-stars", split="train")
df = ds.to_pandas()

# Eclipsing binaries with known periods
eclipsing = df[df["variable_type"].str.startswith("E", na=False) & df["period_days"].notna()]
print(f"Eclipsing binaries with periods: {len(eclipsing):,}")

# Period-amplitude diagram for RR Lyrae
rrab = df[df["variable_type"] == "RRAB"]
import matplotlib.pyplot as plt
plt.scatter(rrab["period_days"], rrab["mag_range"], s=0.5, alpha=0.3)
plt.xlabel("Period (days)")
plt.ylabel("Amplitude (mag)")
plt.title("RR Lyrae (RRAB) Period-Amplitude Diagram")
plt.show()

# Sky distribution
plt.hexbin(df["ra_deg"], df["dec_deg"], gridsize=200, mincnt=1)
plt.colorbar(label="Star count")
plt.xlabel("RA (deg)")
plt.ylabel("Dec (deg)")
plt.title("VSX Variable Stars Sky Density")
plt.show()
```"""

    with Pipeline(
        repo=HF_REPO,
        pretty_name="AAVSO Variable Star Index (VSX)",
        description=DESCRIPTION,
        tags=["space", "variable-stars", "aavso", "vsx", "astronomy",
              "open-data", "tabular-data", "parquet"],
        source_url="https://www.aavso.org/vsx/",
        task_categories=["tabular-classification", "tabular-regression"],
        collection_url="https://huggingface.co/collections/juliensimon/astronomy-datasets-69c24caf2f17e36128946743",
        banner={
            "url": "https://images-assets.nasa.gov/image/PIA03606/PIA03606~small.jpg",
            "alt": "The Crab Nebula, a supernova remnant",
            "credit": "NASA/ESA/Hubble",
        },
        related_datasets=[
            "juliensimon/gcvs-variable-stars",
            "juliensimon/gaia-dr3-eclipsing-binaries",
            "juliensimon/gaia-dr3-young-stellar-objects",
        ],
    ) as p:
        df = p.clean(
            df,
            numeric=["ra_deg", "dec_deg", "mag_max", "mag_min", "epoch_jd",
                      "period_days", "mag_range"],
            drop_mostly_null_threshold=0.95,
        )
        p.publish(
            df,
            filename="aavso_vsx_variable_stars.parquet",
            min_rows=1_500_000,
            expected_columns=["aavso_uid", "name", "ra_deg", "dec_deg",
                              "variable_type", "mag_max", "period_days"],
            critical_columns=["aavso_uid", "name", "ra_deg", "dec_deg"],
            column_descriptions=COLUMN_DESCRIPTIONS,
            quick_stats=quick_stats,
            usage=usage,
            commit_message=f"Update AAVSO VSX: {n_total:,} variable stars",
        )
    print("Done.")


if __name__ == "__main__":
    main()
