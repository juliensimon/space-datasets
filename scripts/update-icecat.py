#!/usr/bin/env python3
"""Fetch ICECAT-1 (IceCube Event Catalog of Alert Tracks) from Harvard Dataverse
and upload to HF.

Static dataset -- no GitHub Actions workflow.

Source: https://dataverse.harvard.edu/dataset.xhtml?persistentId=doi:10.7910/DVN/SCRUCD
Paper: IceCube Collaboration, ICECAT-1 catalog of neutrino alert tracks.
"""

import io

import pandas as pd
import requests

from hf_dataset_utils import Pipeline

# Harvard Dataverse file ID for IceCube_Gold_Bronze_Tracks.tab (TSV summary)
DATAVERSE_FILE_ID = 7502710
DATAVERSE_URL = f"https://dataverse.harvard.edu/api/access/datafile/{DATAVERSE_FILE_ID}"
HF_REPO = "juliensimon/icecat-neutrino-alerts"

# ── Column mapping ───────────────────────────────────────────────────
RENAME = {
    "NAME": "event_name",
    "RUNID": "run_id",
    "EVENTID": "event_id",
    "START": "event_utc",
    "EVENTMJD": "event_mjd",
    "I3TYPE": "alert_type",
    "RA": "ra_deg",
    "DEC": "dec_deg",
    "RA_ERR_PLUS": "ra_err_plus",
    "RA_ERR_MINUS": "ra_err_minus",
    "DEC_ERR_PLUS": "dec_err_plus",
    "DEC_ERR_MINUS": "dec_err_minus",
    "ENERGY": "energy_tev",
    "FAR": "false_alarm_rate_per_yr",
    "SIGNAL": "signalness",
    "CASCADE_SCR": "score_cascade",
    "SKIMMING_SCR": "score_skimming",
    "START_SCR": "score_starting",
    "STOP_SCR": "score_stopping",
    "THRGOING_SCR": "score_throughgoing",
    "CR_VETO": "cosmic_ray_veto",
    "OTHER_I3TYPES": "other_alert_types",
}

# ── Column descriptions for README schema table ─────────────────────
COLUMN_DESCRIPTIONS = {
    "event_name": "IceCube event identifier (e.g., IC110514A); encodes date and sequence",
    "run_id": "IceCube DAQ run identifier; used internally for event reconstruction and calibration",
    "event_id": "IceCube DAQ event identifier within the run; unique when combined with run_id",
    "event_utc": "Event trigger time as a UTC datetime; used for multi-messenger coincidence searches with gamma-ray, optical, and gravitational-wave observatories",
    "event_mjd": "Event trigger time as Modified Julian Date (MJD = JD - 2400000.5); MJD 55000 ~ 2009, MJD 60000 ~ 2023",
    "alert_type": "Event selection type: gfu-gold (highest-confidence track), gfu-bronze (lower-confidence track), ehe-gold (extremely high energy), hese-gold (high-energy starting event, gold), hese-bronze (high-energy starting event, bronze)",
    "ra_deg": "Best-fit right ascension in degrees (J2000.0 ICRS, 0-360); muon track angular resolution is typically ~0.5 deg at these energies",
    "dec_deg": "Best-fit declination in degrees (J2000.0 ICRS, -90 to +90); IceCube is most sensitive to the Northern sky (upgoing neutrinos) for track events",
    "ra_err_plus": "Positive 90% confidence level error on right ascension (degrees); asymmetric errors reflect the non-Gaussian reconstruction uncertainty",
    "ra_err_minus": "Negative 90% confidence level error on right ascension (degrees)",
    "dec_err_plus": "Positive 90% confidence level error on declination (degrees)",
    "dec_err_minus": "Negative 90% confidence level error on declination (degrees)",
    "energy_tev": "Most probable neutrino energy in TeV, assuming an E^(-2.19) astrophysical flux; typical range 100 TeV to several PeV for alert-quality events",
    "false_alarm_rate_per_yr": "Background false-alarm rate in events per year; lower values indicate higher significance of the astrophysical hypothesis",
    "signalness": "Probability that the event originates from an astrophysical neutrino rather than atmospheric background; gold alerts have signalness > 0.5",
    "score_cascade": "CNN topology classifier score for cascade-like morphology (electromagnetic or hadronic showers); range 0-1",
    "score_skimming": "CNN topology classifier score for Earth-skimming tau neutrino morphology; range 0-1",
    "score_starting": "CNN topology classifier score for starting track morphology (neutrino interacts inside the detector); range 0-1",
    "score_stopping": "CNN topology classifier score for stopping track morphology (muon stops inside the detector); range 0-1",
    "score_throughgoing": "CNN topology classifier score for throughgoing track morphology (best angular resolution, ~0.5 deg); range 0-1",
    "cosmic_ray_veto": "True if the IceTop surface array flagged coincident cosmic-ray air shower activity; used to reject atmospheric muon backgrounds",
    "other_alert_types": "Additional alert categories this event passed beyond its primary alert_type; null for most events",
}

# ── Dataset description ──────────────────────────────────────────────
DESCRIPTION = """\
Catalog of high-energy neutrino events from the IceCube Neutrino Observatory at the \
South Pole, selected as astrophysical candidates by the Gold and Bronze track alert \
program. ICECAT-1 is the first systematic catalog of neutrino alert tracks.

The IceCube Neutrino Observatory is a cubic-kilometer particle detector buried in the \
Antarctic ice. Each event is a high-energy (>~100 TeV) muon track with significant \
probability of astrophysical origin. The catalog includes best-fit sky coordinates \
(RA/Dec with asymmetric errors), energy estimates, signalness (probability of \
astrophysical origin), false-alarm rates, and CNN-based topology classification scores.

High-energy neutrinos are uniquely powerful messengers for probing the non-thermal \
universe. Unlike photons, they travel undeflected by magnetic fields and unabsorbed by \
intervening matter, pointing directly back to their production sites. The 2017 \
coincidence of IceCube-170922A with the flaring blazar TXS 0506+056 provided the first \
compelling evidence for an extragalactic neutrino point source and inaugurated the era \
of multi-messenger astronomy with neutrinos.
"""


def fetch_catalog() -> pd.DataFrame:
    """Download TSV summary table from Harvard Dataverse."""
    print("Fetching ICECAT-1 catalog from Harvard Dataverse...")
    resp = requests.get(DATAVERSE_URL, timeout=120)
    resp.raise_for_status()

    df = pd.read_csv(io.StringIO(resp.text), sep="\t")
    print(f"  Downloaded {len(df):,} rows, {len(df.columns)} columns")
    return df


def main():
    df = fetch_catalog()

    # ── Clean up quoted string columns ───────────────────────────────
    for col in df.select_dtypes(include=["object"]).columns:
        df[col] = df[col].astype(str).str.strip().str.strip('"')
        df[col] = df[col].replace({"": pd.NA, "None": pd.NA, "nan": pd.NA, "null": pd.NA})

    # ── Rename columns to snake_case ─────────────────────────────────
    df = df.rename(columns=RENAME)

    # ── Parse event_utc as datetime ──────────────────────────────────
    if "event_utc" in df.columns:
        df["event_utc"] = pd.to_datetime(df["event_utc"], errors="coerce")

    # ── Coerce boolean cosmic_ray_veto ───────────────────────────────
    if "cosmic_ray_veto" in df.columns:
        df["cosmic_ray_veto"] = df["cosmic_ray_veto"].astype(str).str.upper().map(
            {"TRUE": True, "FALSE": False}
        )

    # ── Sort by MJD (chronological) ─────────────────────────────────
    df = df.sort_values("event_mjd").reset_index(drop=True)

    # Keep only described columns
    df = df[[c for c in df.columns if c in COLUMN_DESCRIPTIONS]]

    print(f"  {len(df):,} neutrino alert events")

    # ── Domain-specific stats for README ─────────────────────────────
    n_total = len(df)
    n_gold = int((df["alert_type"].str.contains("gold", case=False, na=False)).sum())
    n_bronze = int((df["alert_type"].str.contains("bronze", case=False, na=False)).sum())
    median_energy = df["energy_tev"].median()
    median_signalness = df["signalness"].median()
    year_min = df["event_utc"].dt.year.min()
    year_max = df["event_utc"].dt.year.max()

    type_counts = df["alert_type"].value_counts()
    type_lines = [f"- **{count:,}** {atype}" for atype, count in type_counts.items()]
    type_summary = "\n".join(type_lines)

    quick_stats = f"""\
- **{n_total:,}** neutrino alert events ({year_min}-{year_max})
- **{n_gold:,}** gold alerts, **{n_bronze:,}** bronze alerts
- Median energy: **{median_energy:.0f} TeV**
- Median signalness: **{median_signalness:.3f}**
- Alert type breakdown:
{type_summary}"""

    usage = """\
```python
from datasets import load_dataset

ds = load_dataset("juliensimon/icecat-neutrino-alerts", split="train")
df = ds.to_pandas()

print(f"{len(df):,} neutrino events")

# Gold alerts only
gold = df[df["alert_type"].str.contains("gold")]
print(f"{len(gold):,} gold alerts, median signalness={gold['signalness'].median():.3f}")

# Sky map
import matplotlib.pyplot as plt
import numpy as np
fig, ax = plt.subplots(subplot_kw={"projection": "aitoff"})
ra_rad = np.deg2rad(df["ra_deg"] - 180)
dec_rad = np.deg2rad(df["dec_deg"])
ax.scatter(ra_rad, dec_rad, s=8, alpha=0.6, c=df["energy_tev"],
           cmap="plasma", norm=plt.matplotlib.colors.LogNorm())
ax.set_title("ICECAT-1 Neutrino Sky Map")
ax.grid(True)
plt.show()
```"""

    with Pipeline(
        repo=HF_REPO,
        pretty_name="ICECAT-1 -- IceCube Event Catalog of Alert Tracks",
        description=DESCRIPTION,
        tags=["space", "neutrinos", "icecube", "multi-messenger",
              "astronomy", "physics", "open-data", "tabular-data", "parquet"],
        source_url="https://doi.org/10.7910/DVN/SCRUCD",
        task_categories=["tabular-classification"],
        collection_url="https://huggingface.co/collections/juliensimon/physics-datasets-69c2d4682d37dfdb77447bd7",
        banner={
            "url": "https://images-assets.nasa.gov/image/PIA23006/PIA23006~small.jpg",
            "alt": "Aurora australis seen from the International Space Station above Antarctica",
            "credit": "NASA",
        },
        related_datasets=[
            "juliensimon/gamma-ray-bursts",
            "juliensimon/tevcat-tev-gamma-ray",
            "juliensimon/auger-cosmic-rays",
        ],
    ) as p:
        df = p.clean(
            df,
            numeric=[
                "event_mjd", "ra_deg", "dec_deg",
                "ra_err_plus", "ra_err_minus", "dec_err_plus", "dec_err_minus",
                "energy_tev", "false_alarm_rate_per_yr", "signalness",
                "score_cascade", "score_skimming", "score_starting",
                "score_stopping", "score_throughgoing",
            ],
            integer=["run_id", "event_id"],
        )
        p.publish(
            df,
            filename="icecat.parquet",
            min_rows=200,
            expected_columns=["event_name", "ra_deg", "dec_deg", "energy_tev", "signalness"],
            critical_columns=["ra_deg", "dec_deg", "energy_tev"],
            column_descriptions=COLUMN_DESCRIPTIONS,
            quick_stats=quick_stats,
            usage=usage,
            commit_message=f"Update ICECAT-1: {n_total:,} neutrino alert events",
        )
    print("Done.")


if __name__ == "__main__":
    main()
