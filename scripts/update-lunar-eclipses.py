#!/usr/bin/env python3
"""Fetch NASA Five Millennium Catalog of Lunar Eclipses and upload to HF.

Static dataset — uploaded once. No GitHub Actions workflow.

Source: Fred Espenak's Five Millennium Canon of Lunar Eclipses (-1999 to +3000),
hosted by NASA GSFC. The site exposes ~50 century-by-century HTML pages; we
scrape all of them and assemble a single ~12,000-row DataFrame.
"""

import re
import time

import pandas as pd
import requests
from bs4 import BeautifulSoup

from hf_dataset_utils import Pipeline

BASE_URL = "https://eclipse.gsfc.nasa.gov/LEcat5"
INDEX_URL = f"{BASE_URL}/LEcatalog.html"
HF_REPO = "juliensimon/lunar-eclipse-catalog"

MONTH_MAP = {
    "Jan": 1, "Feb": 2, "Mar": 3, "Apr": 4, "May": 5, "Jun": 6,
    "Jul": 7, "Aug": 8, "Sep": 9, "Oct": 10, "Nov": 11, "Dec": 12,
}

# Eclipse type: first letter determines base category
ECLIPSE_TYPE_NAMES = {
    "T": "Total",
    "P": "Partial",
    "N": "Penumbral",
}

# ── Column descriptions for README schema table ──────────────────────
COLUMN_DESCRIPTIONS = {
    "catalog_number": "Sequential catalog number (1 to ~12,000), monotonically increasing with time",
    "date": "Date of greatest eclipse in ISO format (YYYY-MM-DD); negative year values indicate BCE dates",
    "year": "Calendar year; negative for BCE (e.g., -500 = 500 BCE); range -1999 to +3000",
    "td_greatest_eclipse": "Time of greatest eclipse in Terrestrial Dynamical Time (TDT), format HH:MM:SS",
    "delta_t": "Difference between Terrestrial Dynamical Time and Universal Time (TDT - UT) in seconds; large and uncertain for ancient dates (>10,000 s before 1000 CE)",
    "luna_number": "Lunation count in Brown's series (consecutive full-moon numbering since 1923-01-17)",
    "saros_number": "Saros series number; each series repeats every 18 years 11 days 8 hours and produces ~70-80 eclipses over ~1,300 years",
    "eclipse_type": "Eclipse type code: T (total), P (partial), N (penumbral); may include + or - suffix for exceptional duration, or x/b/e suffix for subtype",
    "eclipse_type_name": "Full English name of eclipse type corresponding to the eclipse_type code",
    "is_total": "True if the eclipse is a total lunar eclipse (Moon fully within Earth's umbra)",
    "gamma": "Signed minimum distance of the Moon's center from Earth's shadow axis in Earth equatorial radii; |gamma| < 0.9972 for total, < 1.0260 for partial, < 1.0620 for penumbral",
    "umbral_magnitude": "Eclipse magnitude in the umbral shadow: >1.0 for total, 0 to 1.0 for partial, negative for penumbral-only eclipses",
    "penumbral_magnitude": "Eclipse magnitude in the penumbral shadow; always >= umbral_magnitude; >1.0 triggers easily visible penumbral shading",
    "partial_duration": "Duration of partial phases (first/last umbral contact) in minutes; null for penumbral-only eclipses",
    "total_duration": "Duration of totality (both umbral contacts) in minutes; null for partial and penumbral eclipses",
    "penumbral_duration": "Total duration of penumbral contact in minutes from first to last penumbral contact",
    "latitude": "Geographic latitude at the point of greatest eclipse in decimal degrees (+ = North, - = South)",
    "longitude": "Geographic longitude at the point of greatest eclipse in decimal degrees (+ = East, - = West)",
    "century": "Derived century computed as year // 100; useful for aggregating eclipses by historical period",
}

# ── Dataset description ───────────────────────────────────────────────
DESCRIPTION = """\
Complete catalog of lunar eclipses spanning five millennia (-1999 to +3000), \
computed by Fred Espenak as part of NASA's Five Millennium Canon of Lunar Eclipses.

A lunar eclipse occurs when the Moon passes through Earth's shadow. The Moon can \
enter the faint penumbral shadow (producing a subtle darkening), the darker umbral \
shadow (producing a clearly visible partial eclipse), or become fully immersed in \
the umbra (a total lunar eclipse, often dramatically colored red by sunlight refracted \
through Earth's atmosphere). Unlike solar eclipses, lunar eclipses are visible from \
the entire night side of Earth simultaneously, making them historically important for \
synchronizing calendars across civilizations.

This catalog is derived from Fred Espenak's Five Millennium Canon of Lunar Eclipses, \
using the same computational foundation as the companion solar eclipse catalog: \
Besselian elements with polynomial expressions from Chapront, Chapront-Touze, and \
Francou for lunar and solar coordinates, with corrections for the secular acceleration \
of the Moon and variable Earth rotation via Delta-T.

The **gamma** parameter measures the signed minimum distance of the Moon's center from \
Earth's shadow axis. When gamma is between -0.9972 and +0.9972, the Moon is fully \
immersed in the umbra (total eclipse); between ±1.0260 it is partially in the umbra \
(partial eclipse); and between ±1.0620 only the penumbra is intersected. The \
**umbral_magnitude** gives the fraction of the Moon's diameter immersed in the umbra — \
values above 1.0 indicate a total eclipse. Red coloring during totality depends on \
Earth's atmospheric transparency at the time, described qualitatively by the Danjon \
scale (0 = very dark, 4 = bright copper-red).
"""


def get_century_page_urls(session):
    """Fetch the catalog index and extract all century page URLs."""
    resp = session.get(INDEX_URL, timeout=60)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    urls = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        # Century pages look like "LE-1999--1900.html" or "LE2001-2100.html"
        if re.match(r"LE[-0-9]+-[-0-9]+\.html$", href):
            urls.append(f"{BASE_URL}/{href}")

    # Deduplicate preserving order
    seen = set()
    unique = []
    for u in urls:
        if u not in seen:
            seen.add(u)
            unique.append(u)
    return unique


def parse_lat_lng(lat_str, lng_str):
    """Convert '22N'/'57E' → (22.0, 57.0); '22S'/'57W' → (-22.0, -57.0)."""
    if lat_str == "-" or lng_str == "-":
        return None, None
    try:
        lat_val = float(lat_str[:-1])
        if lat_str.endswith("S"):
            lat_val = -lat_val
        lng_val = float(lng_str[:-1])
        if lng_str.endswith("W"):
            lng_val = -lng_val
        return lat_val, lng_val
    except (ValueError, IndexError):
        return None, None


def parse_duration(val):
    """Return float minutes or None if val is '-'."""
    if val == "-":
        return None
    try:
        return float(val)
    except ValueError:
        return None


def parse_data_line(text):
    """Parse one fixed-width eclipse data line (anchor tags already stripped).

    Expected fields after split():
      0  catalog_number
      1  year
      2  month_abbr
      3  day
      4  HH:MM:SS
      5  delta_t
      6  luna_number
      7  saros_number
      8  eclipse_type
      9  qse  (quincena solar eclipse parameter — not kept)
     10  gamma
     11  penumbral_magnitude
     12  umbral_magnitude
     13  penumbral_duration
     14  partial_duration
     15  total_duration
     16  lat_str
     17  lng_str
    """
    parts = text.split()
    if len(parts) != 18:
        return None
    try:
        cat_num = int(parts[0])
        year = int(parts[1])
        month = MONTH_MAP.get(parts[2])
        if month is None:
            return None
        day = int(parts[3])
        td_time = parts[4]
        delta_t = float(parts[5])
        luna_num = int(parts[6])
        saros_num = int(parts[7])
        eclipse_type = parts[8]
        # parts[9] = QSE — skip
        gamma = float(parts[10])
        pen_mag = float(parts[11])
        um_mag = float(parts[12])
        pen_dur = parse_duration(parts[13])
        par_dur = parse_duration(parts[14])
        tot_dur = parse_duration(parts[15])
        lat, lng = parse_lat_lng(parts[16], parts[17])

        # Build ISO date string (negative year = BCE)
        if year < 0:
            date_str = f"{year:05d}-{month:02d}-{day:02d}"
        else:
            date_str = f"{year:04d}-{month:02d}-{day:02d}"

        return {
            "catalog_number": cat_num,
            "date": date_str,
            "year": year,
            "td_greatest_eclipse": td_time,
            "delta_t": delta_t,
            "luna_number": luna_num,
            "saros_number": saros_num,
            "eclipse_type": eclipse_type,
            "gamma": gamma,
            "penumbral_magnitude": pen_mag,
            "umbral_magnitude": um_mag,
            "penumbral_duration": pen_dur,
            "partial_duration": par_dur,
            "total_duration": tot_dur,
            "latitude": lat,
            "longitude": lng,
        }
    except (ValueError, IndexError):
        return None


def scrape_century_page(session, url):
    """Return list of eclipse dicts from one century HTML page."""
    for attempt in range(3):
        try:
            resp = session.get(url, timeout=60)
            resp.raise_for_status()
            break
        except requests.RequestException as exc:
            if attempt == 2:
                raise
            print(f"    Retry {attempt + 1}/3 for {url}: {exc}")
            time.sleep(2 ** attempt)

    soup = BeautifulSoup(resp.text, "html.parser")

    records = []
    # Data rows appear inside <pre> blocks as <a>NNNNN</a> ... text
    for pre in soup.find_all("pre"):
        # Get raw text with anchor tags converted to just their text content
        text = pre.get_text()
        for raw_line in text.splitlines():
            stripped = raw_line.strip()
            if not stripped:
                continue
            # Data lines start with a 5-digit catalog number
            if re.match(r"^\d{5}\s", stripped):
                rec = parse_data_line(stripped)
                if rec is not None:
                    records.append(rec)

    return records


def main():
    session = requests.Session()
    session.headers.update({"User-Agent": "space-datasets/1.0"})

    print("Fetching Five Millennium Lunar Eclipse Catalog index from NASA GSFC...")
    century_urls = get_century_page_urls(session)
    print(f"  Found {len(century_urls)} century pages")

    all_records = []
    for i, url in enumerate(century_urls, 1):
        page_name = url.split("/")[-1]
        print(f"  [{i:2d}/{len(century_urls)}] {page_name}", end="", flush=True)
        records = scrape_century_page(session, url)
        print(f" → {len(records)} eclipses")
        all_records.extend(records)
        # Be polite — small delay between requests
        if i < len(century_urls):
            time.sleep(0.5)

    print(f"\n  Total raw records: {len(all_records):,}")

    df = pd.DataFrame(all_records)

    # Deduplicate on catalog_number (should be none, but just in case)
    before = len(df)
    df = df.drop_duplicates(subset=["catalog_number"], keep="last")
    if len(df) < before:
        print(f"  Deduped: {before - len(df)} duplicate catalog numbers removed")

    # Sort chronologically
    df = df.sort_values("catalog_number", ascending=True).reset_index(drop=True)

    # ── Derived columns ──────────────────────────────────────────────
    # eclipse_type_name: use first letter for the base category
    df["eclipse_type_name"] = df["eclipse_type"].str[0].map(ECLIPSE_TYPE_NAMES).fillna("Unknown")

    # is_total
    df["is_total"] = df["eclipse_type"].str.startswith("T")

    # century (year // 100 using integer floor division)
    df["century"] = (df["year"] // 100).astype("Int64")

    # ── Reorder columns ──────────────────────────────────────────────
    col_order = [
        "catalog_number", "date", "year", "td_greatest_eclipse", "delta_t",
        "luna_number", "saros_number",
        "eclipse_type", "eclipse_type_name", "is_total",
        "gamma", "umbral_magnitude", "penumbral_magnitude",
        "partial_duration", "total_duration", "penumbral_duration",
        "latitude", "longitude", "century",
    ]
    col_order = [c for c in col_order if c in df.columns]
    df = df[col_order]

    print(f"  {len(df):,} lunar eclipses ({df['year'].min()} to {df['year'].max()})")

    # ── Domain-specific stats for README ─────────────────────────────
    n_total_eclipses = len(df)
    n_total = int(df["is_total"].sum())
    n_partial = int((df["eclipse_type"].str.startswith("P")).sum())
    n_penumbral = int((df["eclipse_type"].str.startswith("N")).sum())
    year_min = int(df["year"].min())
    year_max = int(df["year"].max())

    total_df = df[df["is_total"] & df["total_duration"].notna()]
    avg_total_dur = total_df["total_duration"].mean() if len(total_df) > 0 else 0.0
    max_total_dur = total_df["total_duration"].max() if len(total_df) > 0 else 0.0

    quick_stats = f"""\
- **{n_total_eclipses:,}** lunar eclipses ({year_min} to {year_max})
- **{n_total:,}** total ({n_total / n_total_eclipses * 100:.1f}%), \
**{n_partial:,}** partial ({n_partial / n_total_eclipses * 100:.1f}%), \
**{n_penumbral:,}** penumbral ({n_penumbral / n_total_eclipses * 100:.1f}%)
- Average totality duration for total eclipses: **{avg_total_dur:.1f} min**
- Longest total eclipse in catalog: **{max_total_dur:.1f} min** (~{max_total_dur / 60:.2f} h)"""

    usage = """\
```python
from datasets import load_dataset

ds = load_dataset("juliensimon/lunar-eclipse-catalog", split="train")
df = ds.to_pandas()

# Filter by eclipse type
total = df[df["is_total"] == True]
print(f"{len(total):,} total lunar eclipses across 5 millennia")

# Longest total eclipses (Blood Moons)
longest = total.nlargest(5, "total_duration")[["date", "total_duration", "gamma"]]
print(longest)

# Eclipses per century
import matplotlib.pyplot as plt
by_century = df.groupby("century")["eclipse_type_name"].value_counts().unstack(fill_value=0)
by_century.plot.bar(stacked=True, figsize=(14, 5), colormap="Set2")
plt.xlabel("Century")
plt.ylabel("Number of Eclipses")
plt.title("Lunar Eclipse Types by Century")
plt.tight_layout()
plt.show()
```"""

    with Pipeline(
        repo=HF_REPO,
        pretty_name="Five Millennium Catalog of Lunar Eclipses",
        description=DESCRIPTION,
        tags=["space", "lunar-eclipse", "eclipse", "moon", "astronomy",
              "nasa", "planetary-science", "open-data", "tabular-data", "parquet"],
        source_url="https://eclipse.gsfc.nasa.gov/LEcat5/LEcatalog.html",
        task_categories=["tabular-classification"],
        collection_url="https://huggingface.co/collections/juliensimon/astronomy-datasets-69c24caf2f17e36128946743",
        banner={
            "url": "https://images-assets.nasa.gov/image/as08-14-2506/as08-14-2506~small.jpg",
            "alt": "The Moon seen from Apollo 8, showing craters and surface detail",
            "credit": "NASA/Apollo 8",
        },
        related_datasets=[
            "juliensimon/solar-eclipse-catalog",
            "juliensimon/lunar-craters-robbins",
            "juliensimon/iers-earth-orientation",
        ],
    ) as p:
        df = p.clean(
            df,
            numeric=["gamma", "umbral_magnitude", "penumbral_magnitude",
                     "partial_duration", "total_duration", "penumbral_duration",
                     "latitude", "longitude", "delta_t"],
            integer=["catalog_number", "luna_number", "saros_number", "year"],
        )
        p.publish(
            df,
            filename="lunar_eclipses.parquet",
            min_rows=10000,
            expected_columns=["catalog_number", "date", "eclipse_type", "gamma", "umbral_magnitude"],
            critical_columns=["catalog_number", "date", "eclipse_type"],
            column_descriptions=COLUMN_DESCRIPTIONS,
            quick_stats=quick_stats,
            usage=usage,
            commit_message=f"Upload lunar eclipse catalog: {n_total_eclipses:,} eclipses",
        )
    print("Done.")


if __name__ == "__main__":
    main()
