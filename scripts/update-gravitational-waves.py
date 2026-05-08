#!/usr/bin/env python3
"""Fetch gravitational wave events from GWOSC and upload to HF.

Source: Gravitational-Wave Open Science Center (GWOSC)
All confirmed events from LIGO/Virgo/KAGRA observing runs.
https://gwosc.org/eventapi/
"""

import sys
import time

import pandas as pd
import requests

from hf_dataset_utils import Pipeline

GWOSC_URL = "https://gwosc.org/eventapi/json/allevents/"
HF_REPO = "juliensimon/gravitational-wave-events"

# Map catalog prefixes to observing runs
CATALOG_TO_RUN = {
    "O1_O2": "O1/O2",
    "Initial_LIGO": "Initial",
    "GWTC-1": "O1/O2",
    "GWTC-2": "O3a",
    "GWTC-3": "O3b",
    "GWTC-4": "O4a",
    "IAS-O3a": "O3a",
    "O3_": "O3",
    "O4_": "O4",
}

# ── Column descriptions for README schema table ─────────────────────
COLUMN_DESCRIPTIONS = {
    "name": "Event identifier encoding the detection date; 'GW' prefix for confident detections (e.g. 'GW150914' = Sep 14 2015); some sub-threshold candidates use an 'S' prefix",
    "gps": "Detection time in GPS seconds (seconds since GPS epoch Jan 6 1980 00:00:00 UTC); GPS time does not include leap seconds; use astropy.time for accurate UTC conversion",
    "catalog": "Source catalog identifier (e.g. 'GWTC-1', 'GWTC-2', 'GWTC-3'); later catalogs supersede earlier ones for the same event with improved parameter estimates",
    "run": "LIGO/Virgo/KAGRA observing run derived from catalog (e.g. 'O1/O2', 'O3a', 'O3b', 'O4a'); later runs use more sensitive detectors",
    "mass_1": "Source-frame mass of the heavier compact object in solar masses; mass_1 >= mass_2 by convention; BBH typical range 5-100, BNS range 1.1-2.5",
    "mass_1_lower": "Lower 90% credible interval bound on mass_1 (signed negative offset from median)",
    "mass_1_upper": "Upper 90% credible interval bound on mass_1 (signed positive offset from median)",
    "mass_2": "Source-frame mass of the lighter compact object in solar masses; always <= mass_1 by convention; distinguishes BBH, NSBH, and BNS merger types",
    "mass_2_lower": "Lower 90% credible interval bound on mass_2 (signed negative offset from median)",
    "mass_2_upper": "Upper 90% credible interval bound on mass_2 (signed positive offset from median)",
    "chirp_mass": "Chirp mass in solar masses: M_c = (m1*m2)^(3/5) / (m1+m2)^(1/5); the best-constrained mass combination from gravitational wave phase evolution",
    "chirp_mass_lower": "Lower 90% credible interval bound on chirp_mass (signed negative offset from median)",
    "chirp_mass_upper": "Upper 90% credible interval bound on chirp_mass (signed positive offset from median)",
    "luminosity_distance": "Luminosity distance to the source in Megaparsecs (1 Mpc = 3.26 Mly); inferred from signal amplitude; uncertain by ~50% due to sky-localization degeneracy",
    "luminosity_distance_lower": "Lower 90% credible interval bound on luminosity_distance (signed negative offset from median)",
    "luminosity_distance_upper": "Upper 90% credible interval bound on luminosity_distance (signed positive offset from median)",
    "redshift": "Cosmological redshift z corresponding to the luminosity distance; null when distance is not well-constrained",
    "redshift_lower": "Lower 90% credible interval bound on redshift (signed negative offset from median)",
    "redshift_upper": "Upper 90% credible interval bound on redshift (signed positive offset from median)",
    "chi_eff": "Effective inspiral spin parameter: mass-weighted projection of both component spins onto the orbital angular momentum axis; ranges from -1 (anti-aligned) to +1 (fully aligned)",
    "chi_eff_lower": "Lower 90% credible interval bound on chi_eff (signed negative offset from median)",
    "chi_eff_upper": "Upper 90% credible interval bound on chi_eff (signed positive offset from median)",
    "network_snr": "Coherent network matched-filter signal-to-noise ratio across all active detectors; confident detections typically have SNR > 8",
    "network_snr_lower": "Lower 90% credible interval bound on network_snr (signed negative offset from median)",
    "network_snr_upper": "Upper 90% credible interval bound on network_snr (signed positive offset from median)",
    "p_astro": "Posterior probability that the trigger is of astrophysical origin rather than noise; catalog inclusion requires p_astro > 0.5; flagship events have p_astro > 0.99",
    "far": "False alarm rate in Hz (events per second of observation); quantifies how often random noise would produce a trigger of equal or greater significance",
    "far_lower": "Lower 90% credible interval bound on far (signed negative offset from median)",
    "far_upper": "Upper 90% credible interval bound on far (signed positive offset from median)",
    "final_mass": "Source-frame mass of the post-merger remnant in solar masses; less than mass_1 + mass_2 because ~5% of total mass is radiated as gravitational wave energy; null for events where remnant mass is not estimated",
    "final_mass_lower": "Lower 90% credible interval bound on final_mass (signed negative offset from median)",
    "final_mass_upper": "Upper 90% credible interval bound on final_mass (signed positive offset from median)",
    "final_spin": "Dimensionless spin magnitude of the post-merger remnant (Kerr parameter a = J/M^2*c); ranges 0 (non-spinning) to <1 (extremal Kerr limit); BBH remnants typically 0.6-0.8",
    "final_spin_lower": "Lower 90% credible interval bound on final_spin (signed negative offset from median)",
    "final_spin_upper": "Upper 90% credible interval bound on final_spin (signed positive offset from median)",
}

# ── Dataset description ──────────────────────────────────────────────
DESCRIPTION = """\
All confirmed gravitational wave events from the Gravitational-Wave Open Science Center \
(GWOSC), covering LIGO, Virgo, and KAGRA observing runs.

Gravitational waves are ripples in spacetime generated by the acceleration of massive objects, \
predicted by Einstein's general theory of relativity in 1916 and first directly detected on \
September 14, 2015, by the LIGO detectors. That event, GW150914, was produced by the merger of \
two black holes and earned the 2017 Nobel Prize in Physics.

Each row represents one gravitational wave event (merger of compact objects such as black holes \
and/or neutron stars). Parameters include component masses, distance, spins, signal-to-noise \
ratio, and astrophysical probability. The catalog spans multiple observing runs of increasing \
sensitivity, from the initial O1/O2 runs through O3 and into O4.

The vast majority of events are binary black hole (BBH) mergers, but the catalog also includes \
binary neutron star (BNS) mergers -- most notably GW170817, the first event with an \
electromagnetic counterpart -- and neutron star-black hole (NSBH) systems. This dataset enables \
research into the mass distribution of stellar-mass black holes, the equation of state of \
neutron star matter, the expansion rate of the universe via standard siren cosmology, and the \
formation channels of compact binary systems.
"""


def _infer_run(catalog: str | None) -> str | None:
    """Infer the observing run from the catalog name."""
    if not catalog:
        return None
    for prefix, run in CATALOG_TO_RUN.items():
        if catalog.startswith(prefix):
            return run
    return None


def main():
    print("Fetching gravitational wave events from GWOSC...")
    for attempt in range(3):
        try:
            resp = requests.get(GWOSC_URL, timeout=120)
            resp.raise_for_status()
            if resp.text.strip().startswith("<"):
                raise ValueError(f"GWOSC returned HTML (likely error page): {resp.text[:200]}")
            break
        except Exception as exc:
            print(f"  Attempt {attempt + 1}/3 failed: {exc}")
            if attempt == 2:
                print("All retries exhausted.")
                sys.exit(1)
            time.sleep(30 * (attempt + 1))

    data = resp.json()

    events_dict = data.get("events", data)
    if isinstance(events_dict, list):
        events_dict = {str(i): e for i, e in enumerate(events_dict)}
    print(f"  {len(events_dict):,} event versions in API response")

    if not events_dict:
        print("No events returned from GWOSC — aborting.")
        sys.exit(1)

    # Deduplicate: keep latest version of each commonName
    seen: dict[str, tuple[dict, int]] = {}
    for event_key, e in events_dict.items():
        common = e.get("commonName", event_key)
        version = e.get("version", 0) or 0
        if common not in seen or version > seen[common][1]:
            seen[common] = (e, version)

    rows = []
    for common_name, (e, _version) in seen.items():
        row = {
            "name": common_name,
            "gps": e.get("GPS"),
            "catalog": e.get("catalog.shortName"),
            "run": _infer_run(e.get("catalog.shortName")),
            "mass_1": e.get("mass_1_source"),
            "mass_1_lower": e.get("mass_1_source_lower"),
            "mass_1_upper": e.get("mass_1_source_upper"),
            "mass_2": e.get("mass_2_source"),
            "mass_2_lower": e.get("mass_2_source_lower"),
            "mass_2_upper": e.get("mass_2_source_upper"),
            "chirp_mass": e.get("chirp_mass_source"),
            "chirp_mass_lower": e.get("chirp_mass_source_lower"),
            "chirp_mass_upper": e.get("chirp_mass_source_upper"),
            "luminosity_distance": e.get("luminosity_distance"),
            "luminosity_distance_lower": e.get("luminosity_distance_lower"),
            "luminosity_distance_upper": e.get("luminosity_distance_upper"),
            "redshift": e.get("redshift"),
            "redshift_lower": e.get("redshift_lower"),
            "redshift_upper": e.get("redshift_upper"),
            "chi_eff": e.get("chi_eff"),
            "chi_eff_lower": e.get("chi_eff_lower"),
            "chi_eff_upper": e.get("chi_eff_upper"),
            "network_snr": e.get("network_matched_filter_snr"),
            "network_snr_lower": e.get("network_matched_filter_snr_lower"),
            "network_snr_upper": e.get("network_matched_filter_snr_upper"),
            "p_astro": e.get("p_astro"),
            "far": e.get("far"),
            "far_lower": e.get("far_lower"),
            "far_upper": e.get("far_upper"),
            "final_mass": e.get("final_mass_source"),
            "final_mass_lower": e.get("final_mass_source_lower"),
            "final_mass_upper": e.get("final_mass_source_upper"),
            "final_spin": e.get("final_spin"),
            "final_spin_lower": e.get("final_spin_lower"),
            "final_spin_upper": e.get("final_spin_upper"),
        }
        rows.append(row)

    df = pd.DataFrame(rows)

    # Sort by GPS time
    df = df.sort_values("gps", na_position="last").reset_index(drop=True)
    print(f"  {len(df):,} unique events after deduplication")

    # Drop columns that are entirely null
    all_null = [c for c in df.columns if df[c].isna().all()]
    if all_null:
        print(f"  Dropping {len(all_null)} all-null columns: {all_null}")
        df = df.drop(columns=all_null)

    # Keep only described columns (drop any unexpected columns)
    df = df[[c for c in df.columns if c in COLUMN_DESCRIPTIONS]]

    # ── Domain-specific stats for README ─────────────────────────────
    n_events = len(df)
    catalogs = df["catalog"].dropna().unique()
    catalog_list = ", ".join(sorted(catalogs))
    n_catalogs = len(catalogs)
    runs = df["run"].dropna().unique()
    run_list = ", ".join(sorted(runs))
    median_mass1 = df["mass_1"].median()
    median_dist = df["luminosity_distance"].median()

    quick_stats = f"""\
- **{n_events:,}** gravitational wave events
- **{n_catalogs}** catalogs: {catalog_list}
- Observing runs: {run_list}
- Median primary mass: **{median_mass1:.1f}** solar masses
- Median luminosity distance: **{median_dist:.0f}** Mpc"""

    usage = """\
```python
from datasets import load_dataset

ds = load_dataset("juliensimon/gravitational-wave-events", split="train")
df = ds.to_pandas()

# Binary black hole mergers (both masses > 3 solar masses)
bbh = df[(df["mass_1"] > 3) & (df["mass_2"] > 3)]
print(f"{len(bbh)} binary black hole events")

# Closest events
closest = df.nsmallest(5, "luminosity_distance")[["name", "luminosity_distance", "mass_1", "mass_2"]]

# Mass distribution
import matplotlib.pyplot as plt
df["mass_1"].dropna().hist(bins=30, alpha=0.7, label="Primary mass")
df["mass_2"].dropna().hist(bins=30, alpha=0.7, label="Secondary mass")
plt.xlabel("Mass (solar masses)")
plt.ylabel("Count")
plt.legend()
plt.title("Gravitational Wave Event Mass Distribution")
plt.show()
```"""

    # All numeric columns for p.clean()
    numeric_cols = [
        "gps", "mass_1", "mass_1_lower", "mass_1_upper",
        "mass_2", "mass_2_lower", "mass_2_upper",
        "chirp_mass", "chirp_mass_lower", "chirp_mass_upper",
        "luminosity_distance", "luminosity_distance_lower", "luminosity_distance_upper",
        "redshift", "redshift_lower", "redshift_upper",
        "chi_eff", "chi_eff_lower", "chi_eff_upper",
        "network_snr", "network_snr_lower", "network_snr_upper",
        "p_astro", "far", "far_lower", "far_upper",
        "final_mass", "final_mass_lower", "final_mass_upper",
        "final_spin", "final_spin_lower", "final_spin_upper",
    ]
    # Only include columns that still exist after dropping all-null ones
    numeric_cols = [c for c in numeric_cols if c in df.columns]

    with Pipeline(
        repo=HF_REPO,
        pretty_name="Gravitational Wave Events (GWOSC)",
        description=DESCRIPTION,
        tags=["space", "gravitational-waves", "ligo", "virgo", "kagra",
              "gwosc", "black-hole", "neutron-star", "astronomy",
              "open-data", "tabular-data", "parquet"],
        source_url="https://gwosc.org/eventapi/",
        task_categories=["tabular-classification"],
        collection_url="https://huggingface.co/collections/juliensimon/physics-datasets-69c2d4682d37dfdb77447bd7",
        banner={
            "url": "https://images-assets.nasa.gov/image/GSFC_20171208_Archive_e000415/GSFC_20171208_Archive_e000415~orig.jpg",
            "alt": "Artist illustration of two merging black holes emitting gravitational waves",
            "credit": "NASA/CXC/A. Hobart",
        },
    ) as p:
        df = p.clean(
            df,
            numeric=numeric_cols,
            drop_mostly_null_threshold=0.95,
        )
        p.publish(
            df,
            filename="gravitational_wave_events.parquet",
            min_rows=100,
            expected_columns=["name", "gps", "catalog"],
            critical_columns=["name", "gps"],
            column_descriptions=COLUMN_DESCRIPTIONS,
            quick_stats=quick_stats,
            usage=usage,
            commit_message=f"Update gravitational wave events: {n_events:,} events",
        )
    print("Done.")


if __name__ == "__main__":
    main()
