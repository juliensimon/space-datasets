#!/usr/bin/env python3
"""Fetch NOAA/NCEI Solar Proton Events list and upload to HF.

Source: NOAA NCEI Solar Proton Events Affecting the Earth Environment
https://www.ngdc.noaa.gov/stp/space-weather/interplanetary-data/solar-proton-events/
Static dataset (no workflow).
"""

import re

import pandas as pd
import requests
from bs4 import BeautifulSoup

from hf_dataset_utils import Pipeline

SOURCE_URL = (
    "https://www.ngdc.noaa.gov/stp/space-weather/interplanetary-data/"
    "solar-proton-events/SEP%20page%20code.html"
)
HF_REPO = "juliensimon/solar-proton-events"

# ── Column descriptions for README schema table ─────────────────────
COLUMN_DESCRIPTIONS = {
    "start_datetime": "UTC time when the >10 MeV proton flux first exceeded 10 pfu (NOAA S1 storm threshold)",
    "peak_datetime": "UTC time of maximum >10 MeV proton flux during the event",
    "peak_flux_pfu": "Peak proton flux at energies >10 MeV in Particle Flux Units (1 PFU = 1 proton/cm2/s/sr); NOAA storm scale: S1 >= 10, S2 >= 100, S3 >= 1,000, S4 >= 10,000, S5 >= 100,000 PFU",
    "region_number": "NOAA active region number of the source sunspot group (e.g., '2673'); null if no associated active region was identified",
    "location": "Heliographic coordinates of the associated flare in Stonyhurst format (e.g., 'N05W88'); W = western hemisphere events have better magnetic connectivity to Earth",
    "flare_class": "GOES X-ray flare classification of the associated flare (e.g., 'X9.3', 'M5.8'); most large SPEs follow M5+ or X-class flares; null if no associated flare was identified",
    "flare_optical": "Optical (H-alpha) flare importance class (e.g., '2B', '3B', 'SF'); digit = area class (1-4), letter = brightness (F=faint, N=normal, B=bright); null if not observed optically",
    "type_ii_radio": "True if a Type II radio burst (metric wavelength, indicative of a CME-driven coronal shock) was observed during the event; strong predictor of energetic SEP events",
    "type_iv_radio": "True if a Type IV radio burst (post-flare broadband continuum from trapped electrons) was observed; associated with the most intense and prolonged SPEs",
    "cme_speed_km_s": "Linear plane-of-sky speed of the associated coronal mass ejection in km/s from LASCO coronagraph data; null if no CME was observed or measured; fast CMEs (>1000 km/s) are strongly correlated with major SPEs",
}

# ── Dataset description ──────────────────────────────────────────────
DESCRIPTION = """\
Solar proton events (SPEs) affecting the Earth environment from 1976 to present, \
compiled by NOAA's Space Weather Prediction Center. Includes peak proton flux, \
associated flare class, location, and CME data.

Solar proton events occur when protons are accelerated to high energies by solar \
flares or coronal mass ejections (CMEs). When these energetic particles reach Earth, \
they can disrupt satellite electronics, increase radiation doses for astronauts and \
high-altitude aviation, degrade HF radio communications, and affect GPS accuracy.

Solar energetic particles are accelerated by two distinct mechanisms. Impulsive SEP \
events are associated with solar flares, where magnetic reconnection accelerates \
electrons and ions over seconds to minutes. Gradual SEP events -- which account for \
most entries in this dataset -- are accelerated by CME-driven coronal and interplanetary \
shocks via diffusive shock acceleration. The largest gradual events (>10,000 pfu) are \
associated with fast, wide CMEs and western-hemisphere flares, where the magnetic \
connection along the Parker spiral provides early particle access to Earth.

The >10 MeV proton flux threshold of 10 pfu used to define SPEs corresponds to the \
NOAA S1 (minor) solar radiation storm level. At S3-S5 (>1,000 to >100,000 pfu), \
single-event upsets become a serious concern for satellite electronics, astronaut EVA \
activities must be curtailed, and HF radio is blacked out on the sunlit hemisphere.
"""


def parse_datetime(s):
    """Parse datetime strings like '1976 04/30 2120' or '2025 11/10 1125'."""
    if not s or not isinstance(s, str):
        return pd.NaT
    s = s.strip()
    if not s or s.lower() in ("n/a", "", "-"):
        return pd.NaT
    m = re.match(r"(\d{4})\s+(\d{1,2})/(\d{1,2})\s+(\d{3,4})", s)
    if not m:
        return pd.NaT
    year, month, day, hhmm = m.groups()
    hhmm = hhmm.zfill(4)
    hour, minute = int(hhmm[:2]), int(hhmm[2:])
    try:
        return pd.Timestamp(int(year), int(month), int(day), hour, minute)
    except (ValueError, OverflowError):
        return pd.NaT


def parse_flux(s):
    """Parse proton flux like '12', '1,000', '37,000'."""
    if not s or not isinstance(s, str):
        return None
    s = s.strip().replace(",", "")
    if not s or s.lower() in ("n/a", "-"):
        return None
    try:
        return int(s)
    except ValueError:
        try:
            return float(s)
        except ValueError:
            return None


def parse_flare_info(s):
    """Parse flare maximum field like 'X2/2B 4/30 2114'.

    Returns (flare_class, flare_optical).
    """
    if not s or not isinstance(s, str):
        return None, None
    s = s.strip()
    if not s or s.lower() in ("n/a", "-", ""):
        return None, None
    m = re.match(r"([XMCB]\d+\.?\d*)\s*/\s*(\S+)", s)
    if m:
        return m.group(1), m.group(2)
    m = re.match(r"([XMCB]\d+\.?\d*)", s)
    if m:
        return m.group(1), None
    return None, None


def clean_str(s):
    """Clean a string field, returning None for N/A-like values."""
    if not s or not isinstance(s, str):
        return None
    s = s.strip()
    if s.lower() in ("n/a", "-", ""):
        return None
    return s


def main():
    print("Fetching NOAA/NCEI Solar Proton Events list...")
    resp = requests.get(SOURCE_URL, timeout=120)
    resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "html.parser")
    table = soup.find("table", id="myTable")
    if table is None:
        table = soup.find("table")
    if table is None:
        raise RuntimeError("No table found on the page")

    rows = []
    tbody = table.find("tbody", recursive=False)
    trs = tbody.find_all("tr") if tbody else table.find_all("tr")[1:]
    for tr in trs:
        cells = [re.sub(r"\s+", " ", td.get_text(strip=True)) for td in tr.find_all("td")]
        if len(cells) < 6:
            continue
        rows.append(cells)

    print(f"  Parsed {len(rows)} rows from HTML table")

    records = []
    for cells in rows:
        begin_dt = parse_datetime(cells[0])
        max_dt = parse_datetime(cells[1])
        flux = parse_flux(cells[2])
        region = clean_str(cells[3])
        location = clean_str(cells[4])
        flare_class, flare_optical = parse_flare_info(cells[5])
        type_ii = clean_str(cells[6]) if len(cells) > 6 else None
        type_iv = clean_str(cells[7]) if len(cells) > 7 else None
        cme_speed = clean_str(cells[8]) if len(cells) > 8 else None

        cme_speed_val = None
        if cme_speed:
            m = re.search(r"(\d+)", cme_speed.replace(",", ""))
            if m:
                cme_speed_val = int(m.group(1))

        records.append({
            "start_datetime": begin_dt,
            "peak_datetime": max_dt,
            "peak_flux_pfu": flux,
            "region_number": region,
            "location": location,
            "flare_class": flare_class,
            "flare_optical": flare_optical,
            "type_ii_radio": type_ii is not None and type_ii.lower() not in ("no",),
            "type_iv_radio": type_iv is not None and type_iv.lower() not in ("no",),
            "cme_speed_km_s": cme_speed_val,
        })

    df = pd.DataFrame(records)

    # Coerce types
    df["peak_flux_pfu"] = pd.to_numeric(df["peak_flux_pfu"], errors="coerce").astype("Int64")
    df["cme_speed_km_s"] = pd.to_numeric(df["cme_speed_km_s"], errors="coerce").astype("Int64")
    df["start_datetime"] = pd.to_datetime(df["start_datetime"], errors="coerce")
    df["peak_datetime"] = pd.to_datetime(df["peak_datetime"], errors="coerce")

    # Drop rows with no start datetime
    df = df.dropna(subset=["start_datetime"]).reset_index(drop=True)
    df = df.sort_values("start_datetime").reset_index(drop=True)

    print(f"  {len(df):,} events after cleaning")

    # ── Domain-specific stats for README ─────────────────────────────
    n = len(df)
    date_min = df["start_datetime"].min().strftime("%Y-%m-%d")
    date_max = df["start_datetime"].max().strftime("%Y-%m-%d")
    flux_max = df["peak_flux_pfu"].max()
    flux_median = df["peak_flux_pfu"].median()
    flare_counts = df["flare_class"].dropna().str[0].value_counts().to_dict()
    flare_lines = "\n".join(
        f"  - {k}-class: **{v:,}**" for k, v in sorted(flare_counts.items())
    )

    quick_stats = f"""\
- **{n:,}** events ({date_min} to {date_max})
- Peak flux range: 10 to **{flux_max:,}** pfu (median: {flux_median:,.0f} pfu)
- Associated flares by X-ray class:
{flare_lines}"""

    usage = """\
```python
from datasets import load_dataset

ds = load_dataset("juliensimon/solar-proton-events", split="train")
df = ds.to_pandas()

# Largest proton events
top = df.nlargest(10, "peak_flux_pfu")
print(top[["start_datetime", "peak_flux_pfu", "flare_class", "location"]])

# Events with X-class flares
x_class = df[df["flare_class"].str.startswith("X", na=False)]
print(f"X-class associated events: {len(x_class)}")

# Peak flux distribution by flare class
import matplotlib.pyplot as plt
for cls in ["X", "M", "C"]:
    sub = df[df["flare_class"].str.startswith(cls, na=False)]
    if len(sub) > 0:
        plt.hist(sub["peak_flux_pfu"].dropna(), bins=30, alpha=0.6, label=f"{cls}-class")
plt.xscale("log")
plt.xlabel("Peak Flux (PFU)")
plt.ylabel("Count")
plt.legend()
plt.title("Solar Proton Event Flux by Flare Class")
plt.show()
```"""

    with Pipeline(
        repo=HF_REPO,
        pretty_name="Solar Proton Events",
        description=DESCRIPTION,
        tags=["space", "solar", "protons", "radiation", "space-weather",
              "noaa", "open-data", "tabular-data", "parquet"],
        source_url="https://www.ngdc.noaa.gov/stp/space-weather/interplanetary-data/solar-proton-events/",
        task_categories=["tabular-classification"],
        collection_url="https://huggingface.co/collections/juliensimon/space-weather-datasets-69c24cae98f1666f2101ca70",
        banner={
            "url": "https://images-assets.nasa.gov/image/iss072e159172/iss072e159172~medium.jpg",
            "alt": "Aurora borealis blankets the Earth, seen from the ISS",
            "credit": "NASA",
        },
        related_datasets=[
            "juliensimon/solar-flare-events",
            "juliensimon/donki-space-weather-events",
            "juliensimon/space-weather-indices",
        ],
    ) as p:
        df = p.clean(df)
        p.publish(
            df,
            filename="solar_proton_events.parquet",
            min_rows=200,
            expected_columns=["start_datetime", "peak_datetime", "peak_flux_pfu",
                              "flare_class", "location"],
            critical_columns=["start_datetime", "peak_flux_pfu"],
            column_descriptions=COLUMN_DESCRIPTIONS,
            quick_stats=quick_stats,
            usage=usage,
            commit_message=f"Upload solar proton events: {n:,} records",
        )
    print("Done.")


if __name__ == "__main__":
    main()
