#!/usr/bin/env python3
"""Build launch-cost-to-LEO dataset and upload to HF.

Static dataset of historical and current launch vehicle costs per kg to LEO,
compiled from public sources (NASA, FAA/AST, Bryce Tech, CSIS Aerospace Security,
SpaceX published pricing, ESA, JAXA press releases).

All costs are in 2024 USD unless noted. Sources for each vehicle are cited in the
'source' column.
"""

import pandas as pd

from hf_dataset_utils import Pipeline

HF_REPO = "juliensimon/launch-cost-to-leo"

# fmt: off
# Each entry: (vehicle, operator, country, first_flight_year, payload_leo_kg,
#              cost_per_launch_usd, reusable, status, source)
RAW_DATA = [
    # ── United States: historical ──────────────────────────────────────────
    ("Saturn V",               "NASA",              "USA",    1967, 140000, 1_160_000_000, False, "retired",     "NASA Historical Reference, inflation-adjusted"),
    ("Saturn IB",              "NASA",              "USA",    1966,  21000,   350_000_000, False, "retired",     "NASA Historical Reference, inflation-adjusted"),
    ("Space Shuttle",          "NASA",              "USA",    1981,  27500, 1_500_000_000, True,  "retired",     "NASA OIG reports, inflation-adjusted"),
    ("Titan IV",               "Lockheed Martin",   "USA",    1989,  21680,   432_000_000, False, "retired",     "USAF budget documents, inflation-adjusted"),
    ("Titan IIIE",             "Martin Marietta",   "USA",    1974,  15400,   280_000_000, False, "retired",     "NASA LSP historical data, inflation-adjusted"),
    ("Titan II GLV",           "Martin Marietta",   "USA",    1964,   3580,   170_000_000, False, "retired",     "NASA Gemini program records, inflation-adjusted"),
    ("Delta II",               "Boeing / ULA",      "USA",    1989,   6100,   137_000_000, False, "retired",     "NASA LSP, FAA/AST Annual Compendium"),
    ("Delta IV Heavy",         "ULA",               "USA",    2004,  28790,   400_000_000, False, "retired",     "ULA published pricing, GAO reports"),
    ("Delta IV Medium",        "ULA",               "USA",    2002,  12980,   164_000_000, False, "retired",     "ULA/GAO reports"),
    ("Atlas V 401",            "ULA",               "USA",    2002,   9800,   110_000_000, False, "active",      "ULA pricing, FAA/AST Compendium"),
    ("Atlas V 551",            "ULA",               "USA",    2002,  18850,   153_000_000, False, "active",      "ULA pricing, FAA/AST Compendium"),
    ("Pegasus XL",             "Northrop Grumman",  "USA",    1994,    443,    56_000_000, False, "active",      "Northrop Grumman published pricing"),
    ("Minotaur I",             "Northrop Grumman",  "USA",    2000,    580,    50_000_000, False, "active",      "Northrop Grumman / USAF contracts"),
    ("Minotaur IV",            "Northrop Grumman",  "USA",    2010,   1735,    55_000_000, False, "active",      "Northrop Grumman / USAF contracts"),

    # ── United States: SpaceX ──────────────────────────────────────────────
    ("Falcon 1",               "SpaceX",            "USA",    2006,    670,     7_000_000, False, "retired",     "SpaceX published pricing (2009)"),
    ("Falcon 9 (expendable)",  "SpaceX",            "USA",    2010,  22800,    67_000_000, False, "active",      "SpaceX website (2024)"),
    ("Falcon 9 (reusable)",    "SpaceX",            "USA",    2010,  17400,    67_000_000, True,  "active",      "SpaceX website (2024), reduced LEO for reuse margin"),
    ("Falcon Heavy (expendable)", "SpaceX",         "USA",    2018,  63800,    97_000_000, False, "active",      "SpaceX website (2024)"),
    ("Falcon Heavy (reusable)","SpaceX",            "USA",    2018,  50000,    97_000_000, True,  "active",      "SpaceX website (2024), reduced LEO for reuse"),
    ("Starship (target)",      "SpaceX",            "USA",    2023, 150000,    10_000_000, True,  "in development", "SpaceX stated goal, Elon Musk presentations"),

    # ── United States: other new entrants ──────────────────────────────────
    ("Electron",               "Rocket Lab",        "USA/NZ", 2017,    300,     7_500_000, False, "active",      "Rocket Lab published pricing"),
    ("Electron (Neutron kick stage)", "Rocket Lab",  "USA/NZ", 2017,    320,     7_500_000, True,  "active",      "Rocket Lab published pricing"),
    ("Vulcan Centaur",         "ULA",               "USA",    2024,  27200,   110_000_000, False, "active",      "ULA/Tory Bruno statements, estimated"),
    ("Firefly Alpha",          "Firefly Aerospace", "USA",    2021,   1030,    15_000_000, False, "active",      "Firefly published pricing"),
    ("LauncherOne",            "Virgin Orbit",      "USA",    2021,    500,    12_000_000, False, "retired",     "Virgin Orbit published pricing (pre-bankruptcy)"),
    ("New Glenn",              "Blue Origin",       "USA",    2025,  45000,    68_000_000, True,  "active",      "Blue Origin estimates, industry analysis"),
    ("Terran R",               "Relativity Space",  "USA",    2026,  20000,    55_000_000, True,  "in development", "Relativity Space public statements"),

    # ── Europe ─────────────────────────────────────────────────────────────
    ("Ariane 5 ECA",           "Arianespace",       "Europe", 1996,  21000,   178_000_000, False, "retired",     "Arianespace / ESA published pricing"),
    ("Ariane 5 G",             "Arianespace",       "Europe", 1996,  18000,   165_000_000, False, "retired",     "Arianespace pricing, inflation-adjusted"),
    ("Ariane 6 A62",           "Arianespace",       "Europe", 2024,  10350,    77_000_000, False, "active",      "ESA/Arianespace published target pricing"),
    ("Ariane 6 A64",           "Arianespace",       "Europe", 2024,  21650,   119_000_000, False, "active",      "ESA/Arianespace published target pricing"),
    ("Ariane 4",               "Arianespace",       "Europe", 1988,  10200,   130_000_000, False, "retired",     "Arianespace historical, inflation-adjusted"),
    ("Vega",                   "Arianespace",       "Europe", 2012,   1500,    37_000_000, False, "active",      "Arianespace published pricing"),
    ("Vega-C",                 "Arianespace",       "Europe", 2022,   2300,    45_000_000, False, "active",      "Arianespace published pricing"),

    # ── Russia / Soviet Union ──────────────────────────────────────────────
    ("Soyuz-2.1a",             "Roscosmos",         "Russia", 2004,   7020,    50_000_000, False, "active",      "Roscosmos / Starsem published pricing"),
    ("Soyuz-2.1b",             "Roscosmos",         "Russia", 2006,   8200,    50_000_000, False, "active",      "Roscosmos / Starsem published pricing"),
    ("Soyuz-FG",               "Roscosmos",         "Russia", 2001,   7200,    50_000_000, False, "retired",     "Roscosmos published pricing"),
    ("Proton-M",               "Khrunichev",        "Russia", 2001,  23000,    65_000_000, False, "active",      "ILS published pricing"),
    ("Angara A5",              "Khrunichev",        "Russia", 2014,  24500,    80_000_000, False, "active",      "Russian government budget estimates"),
    ("Energia",                "NPO Energia",       "USSR",   1987, 100000, 1_100_000_000, False, "retired",     "Soviet-era estimates, inflation-adjusted"),
    ("N1",                     "OKB-1",             "USSR",   1969,  95000, 1_300_000_000, False, "retired",     "Soviet-era estimates, never successful, inflation-adj"),
    ("Zenit-2",                "Yuzhnoye",          "Ukraine",1985,  13740,    55_000_000, False, "retired",     "Sea Launch pricing"),
    ("Dnepr",                  "ISC Kosmotras",     "Russia", 1999,   4500,    30_000_000, False, "retired",     "ISC Kosmotras published pricing"),
    ("Rockot",                 "Eurockot",          "Russia", 2000,   1950,    35_000_000, False, "retired",     "Eurockot published pricing"),

    # ── China ──────────────────────────────────────────────────────────────
    ("Long March 5",           "CASC",              "China",  2016,  25000,    60_000_000, False, "active",      "CASC / industry estimates"),
    ("Long March 5B",          "CASC",              "China",  2020,  22000,    55_000_000, False, "active",      "CASC / industry estimates"),
    ("Long March 3B",          "CASC",              "China",  1996,  12000,    40_000_000, False, "active",      "CASC commercial pricing"),
    ("Long March 2D",          "CASC",              "China",  1992,   3500,    30_000_000, False, "active",      "CASC commercial pricing"),
    ("Long March 2F",          "CASC",              "China",  1999,   8400,    45_000_000, False, "active",      "CASC published pricing"),
    ("Long March 11",          "CASC",              "China",  2015,    700,    12_000_000, False, "active",      "CASC published pricing"),
    ("Kuaizhou-1A",            "ExPace",            "China",  2017,    300,     6_000_000, False, "active",      "ExPace published pricing"),
    ("Ceres-1",                "Galactic Energy",   "China",  2020,    350,     4_500_000, False, "active",      "Galactic Energy published pricing"),
    ("Zhuque-2",               "Landspace",         "China",  2023,   6000,    25_000_000, False, "active",      "Landspace public statements"),

    # ── Japan ──────────────────────────────────────────────────────────────
    ("H-IIA",                  "JAXA / MHI",        "Japan",  2001,  10000,    90_000_000, False, "active",      "JAXA / MHI published pricing"),
    ("H3",                     "JAXA / MHI",        "Japan",  2024,  13000,    50_000_000, False, "active",      "JAXA target pricing"),
    ("Epsilon",                "JAXA / IHI",        "Japan",  2013,   1200,    38_000_000, False, "active",      "JAXA published cost"),

    # ── India ──────────────────────────────────────────────────────────────
    ("PSLV",                   "ISRO",              "India",  1993,   3250,    15_000_000, False, "active",      "ISRO published cost"),
    ("GSLV Mk III (LVM3)",    "ISRO",              "India",  2017,  10000,    35_000_000, False, "active",      "ISRO published cost"),
    ("GSLV Mk II",             "ISRO",              "India",  2001,   5000,    25_000_000, False, "active",      "ISRO published cost"),
    ("SSLV",                   "ISRO",              "India",  2022,    500,     5_000_000, False, "active",      "ISRO published cost"),

    # ── Other ──────────────────────────────────────────────────────────────
    ("Nuri (KSLV-II)",         "KARI",              "South Korea", 2021, 1500,  30_000_000, False, "active",     "KARI budget data"),
    ("Shavit",                 "IAI",               "Israel", 1988,    350,    30_000_000, False, "active",      "IAI / Israeli MoD estimates"),
    ("KSLV-1 (Naro)",         "KARI / Khrunichev", "South Korea", 2009, 100,  200_000_000, False, "retired",    "KARI program cost"),
]
# fmt: on

# ── Column descriptions for README schema table ─────────────────────
COLUMN_DESCRIPTIONS = {
    "vehicle": "Launch vehicle name and variant (e.g. 'Falcon 9 (reusable)', 'Saturn V', 'Ariane 5 ECA'); includes configuration detail where pricing differs between expendable and reusable modes",
    "operator": "Primary operator or manufacturer (e.g. 'SpaceX', 'ULA', 'Arianespace', 'ISRO'); reflects the entity that sets launch pricing or operated the vehicle",
    "country": "Country or region of origin (e.g. 'USA', 'Europe', 'Russia', 'China', 'India'); 'Europe' used for ESA/Arianespace vehicles with multi-nation heritage",
    "first_flight_year": "Year the vehicle first flew; ranges from 1964 (Titan II GLV) to 2026 (vehicles in development); used to track cost evolution over decades",
    "payload_leo_kg": "Manufacturer-stated maximum payload capacity to low Earth orbit (~400 km, 28 deg) in kilograms; for reusable configurations, reflects reduced capacity due to propellant reserved for booster recovery",
    "cost_per_launch_usd": "Estimated or published cost per launch in 2024 USD; combines government list prices, commercial pricing sheets, and analyst estimates; historical costs inflation-adjusted using NASA/government indices",
    "cost_per_kg_usd": "Derived cost per kilogram to LEO = cost_per_launch_usd / payload_leo_kg, rounded to nearest dollar; the primary comparison metric across vehicles and eras; ranges from ~$67/kg (Starship target) to >$100,000/kg (small launchers)",
    "reusable": "True if the vehicle recovers and re-flies at least its first stage (e.g. Falcon 9, Space Shuttle); False for fully expendable vehicles; reusability is the key driver of recent cost reductions",
    "status": "Current operational status: 'active' (currently flying), 'retired' (no longer operating), or 'in development' (not yet operational); reflects status as of 2024",
    "source": "Citation for the cost estimate (e.g. 'NASA OIG reports, inflation-adjusted', 'SpaceX website (2024)', 'FAA/AST Annual Compendium'); allows traceability and inflation-adjustment context",
}

# ── Dataset description ──────────────────────────────────────────────
DESCRIPTION = """\
Historical and current launch vehicle costs per kilogram to low Earth orbit (LEO). \
Covers vehicles from the Saturn V era to Starship, with costs normalized to 2024 USD.

The cost of delivering payload to low Earth orbit is the single most important economic \
parameter in spaceflight. It determines the viability of satellite constellations, space \
station resupply, deep-space exploration architectures, and emerging industries like \
orbital manufacturing and space tourism. For decades, launch costs hovered around \
$10,000-$20,000 per kilogram, a figure that constrained space activity to government \
agencies and large defense contractors. The advent of reusable first stages -- pioneered \
by SpaceX's Falcon 9 -- broke this paradigm, driving costs below $3,000/kg and enabling \
mega-constellations like Starlink that would have been economically impossible a \
generation earlier.

This dataset normalizes all costs to 2024 USD, enabling fair comparison across eras. \
Historical costs are adjusted using NASA and government inflation indices. For vehicles \
with both expendable and reusable configurations (Falcon 9, Falcon Heavy), separate \
entries capture the payload penalty of propellant reserved for booster recovery. The \
dataset spans the full range of lift capacity, from small solid-fuel rockets carrying \
a few hundred kilograms to super-heavy-lift vehicles designed for 100+ tonnes.
"""


def build_dataframe():
    """Construct the launch cost DataFrame from embedded data."""
    columns = [
        "vehicle", "operator", "country", "first_flight_year",
        "payload_leo_kg", "cost_per_launch_usd", "reusable", "status", "source",
    ]
    df = pd.DataFrame(RAW_DATA, columns=columns)

    # Derived column: cost per kg
    df["cost_per_kg_usd"] = (df["cost_per_launch_usd"] / df["payload_leo_kg"]).round(0).astype(int)

    # Reorder so cost_per_kg is next to cost_per_launch
    df = df[
        ["vehicle", "operator", "country", "first_flight_year",
         "payload_leo_kg", "cost_per_launch_usd", "cost_per_kg_usd",
         "reusable", "status", "source"]
    ]

    df = df.sort_values("cost_per_kg_usd").reset_index(drop=True)
    return df


def main():
    print("Building launch cost to LEO dataset...")
    df = build_dataframe()
    print(f"  {len(df):,} launch vehicles")

    # Keep only described columns
    df = df[[c for c in df.columns if c in COLUMN_DESCRIPTIONS]]

    # ── Stats for README ──────────────────────────────────────────────────
    n = len(df)
    n_countries = df["country"].nunique()
    n_active = int((df["status"] == "active").sum())
    n_retired = int((df["status"] == "retired").sum())
    n_reusable = int(df["reusable"].sum())
    cheapest = df.iloc[0]
    most_expensive = df.iloc[-1]
    median_cost_kg = int(df["cost_per_kg_usd"].median())

    quick_stats = f"""\
- **{n}** launch vehicles ({n_active} active, {n_retired} retired)
- **{n_countries}** countries/regions
- **{n_reusable}** reusable vehicles
- Cost per kg range: **${cheapest["cost_per_kg_usd"]:,.0f}** ({cheapest["vehicle"]}) to **${most_expensive["cost_per_kg_usd"]:,.0f}** ({most_expensive["vehicle"]})
- Median cost per kg: **${median_cost_kg:,}**"""

    usage = """\
```python
from datasets import load_dataset

ds = load_dataset("juliensimon/launch-cost-to-leo", split="train")
df = ds.to_pandas()

# Cheapest vehicles by cost per kg
print(df.nsmallest(10, "cost_per_kg_usd")[["vehicle", "cost_per_kg_usd", "payload_leo_kg"]])

# Active vehicles only
active = df[df["status"] == "active"]
print(f"{len(active)} active vehicles")

# Cost evolution over time
import matplotlib.pyplot as plt
fig, ax = plt.subplots(figsize=(10, 6))
for reusable, group in df.groupby("reusable"):
    label = "Reusable" if reusable else "Expendable"
    ax.scatter(group["first_flight_year"], group["cost_per_kg_usd"], label=label, alpha=0.7)
ax.set_xlabel("First Flight Year")
ax.set_ylabel("Cost per kg to LEO (2024 USD)")
ax.set_yscale("log")
ax.legend()
ax.set_title("Launch Cost Evolution")
plt.show()
```"""

    with Pipeline(
        repo=HF_REPO,
        pretty_name="Launch Cost to LEO",
        description=DESCRIPTION,
        tags=["space", "rockets", "launch-cost", "economics",
              "orbital-mechanics", "open-data", "tabular-data", "parquet"],
        source_url="https://aerospace.csis.org/data/space-launch-to-low-earth-orbit-how-much-does-it-cost/",
        task_categories=["tabular-classification"],
        collection_url="https://huggingface.co/collections/juliensimon/orbital-mechanics-datasets-69c24caca4ab3934c9856994",
        banner={
            "url": "https://images-assets.nasa.gov/image/iss071e439624/iss071e439624~medium.jpg",
            "alt": "An orbital sunrise illuminates the Earth's atmosphere, seen from the ISS",
            "credit": "NASA",
        },
        related_datasets=[
            "juliensimon/gcat-launch-vehicles",
            "juliensimon/space-launch-log",
            "juliensimon/space-track-satcat",
        ],
    ) as p:
        df = p.clean(
            df,
            numeric=["first_flight_year", "payload_leo_kg",
                     "cost_per_launch_usd", "cost_per_kg_usd"],
            drop_mostly_null_threshold=0.95,
        )
        p.publish(
            df,
            filename="launch_cost_to_leo.parquet",
            min_rows=30,
            expected_columns=[
                "vehicle", "operator", "country", "first_flight_year",
                "payload_leo_kg", "cost_per_launch_usd", "cost_per_kg_usd",
                "reusable", "status",
            ],
            critical_columns=["vehicle", "cost_per_kg_usd"],
            column_descriptions=COLUMN_DESCRIPTIONS,
            quick_stats=quick_stats,
            usage=usage,
            commit_message=f"Update launch cost to LEO: {n} vehicles",
        )
    print("Done.")


if __name__ == "__main__":
    main()
