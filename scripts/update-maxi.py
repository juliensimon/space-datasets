#!/usr/bin/env python3
"""Fetch MAXI source catalog from HEASARC and upload to HF.

Source: HEASARC `maxissccat` — Monitor of All-sky X-ray Image (MAXI) Source Catalog.
MAXI is a JAXA-led X-ray monitor on the International Space Station, continuously
scanning the soft and hard X-ray sky (0.5-30 keV) since August 2009. The Source
Catalog lists the persistent and transient X-ray sources MAXI has detected and
characterized — predominantly X-ray binaries, active galactic nuclei, and
cataclysmic variables.
"""

import pandas as pd

from hf_dataset_utils import Pipeline
from hf_dataset_utils.tap import heasarc_query

HF_REPO = "juliensimon/maxi-xray-sources"

ADQL = "SELECT * FROM maxissccat"

COLUMN_DESCRIPTIONS = {
    "source_number": "MAXI source catalog sequence number (integer); identifies the source within the SSC release",
    "name": "Primary MAXI source designation in the '1MAXIS Jhhmm+ddmm' format following IAU conventions for transient X-ray monitor catalogs",
    "ra": "Right ascension (degrees, J2000, 0-360)",
    "dec": "Declination (degrees, J2000, -90 to +90)",
    "lii": "Galactic longitude (degrees, 0-360); concentration near the Galactic plane traces the X-ray binary population",
    "bii": "Galactic latitude (degrees, -90 to +90); off-plane sources are predominantly AGN",
    "sb_significance": "Detection significance in the MAXI soft band (2-4 keV) in standard deviations; values above 5 indicate a robust detection",
    "hb_significance": "Detection significance in the MAXI hard band (4-10 keV) in standard deviations",
    "sb_flux": "Average source flux in the soft band (2-4 keV) in erg cm^-2 s^-1; computed from long-term GSC scanning data",
    "hb_flux": "Average source flux in the hard band (4-10 keV) in erg cm^-2 s^-1",
    "alt_name": "Alternative source identifier from cross-matching with established X-ray catalogs (e.g. 'SMC X-1', 'LMC X-2', 'Cyg X-3')",
    "source_type": "Astrophysical source classification (e.g. 'Binary pulsar', 'Binary NS', 'Binary BH', 'CV', 'AGN', 'Galaxy cluster')",
    "maxi_gsc_name": "Designation in the parallel MAXI/GSC long-term survey catalog (e.g. '2MAXI J0117-734'); links the SSC entry to the time-resolved photometry product",
    "class": "Numeric source-class code corresponding to source_type",
}

DESCRIPTION = """\
The MAXI (Monitor of All-sky X-ray Image) Source Catalog from HEASARC — the persistent and \
transient X-ray sources detected by the JAXA-led MAXI instrument continuously scanning the \
sky from the International Space Station since August 2009.

MAXI's Gas Slit Camera (GSC) provides daily all-sky coverage at 2-30 keV with the largest \
field of view of any operating X-ray instrument, making it the workhorse monitor for \
detecting X-ray novae, transient outbursts of black-hole and neutron-star binaries, and \
gamma-ray burst afterglows. The Source Catalog (SSC) compiles the persistent source \
population MAXI has characterized over long baselines: X-ray binaries dominated by the \
Galactic plane, plus a substantial AGN component at high Galactic latitudes. Each row \
records the source designation, J2000 sky position, soft- and hard-band detection \
significance and average fluxes, an alternative identifier from cross-matching, and a \
physical type classification.

This dataset is the natural companion to juliensimon/swift-bat-hard-xray-survey (hard X-ray \
all-sky survey from Swift/BAT), juliensimon/chandra-x-ray-sources (focused-pointing Chandra \
catalog), and juliensimon/4xmm-dr14-xray-sources (XMM-Newton serendipitous catalog), \
covering complementary energy bands and observation modes for the X-ray sky.\
"""


def main():
    print("Fetching MAXI source catalog from HEASARC...")
    df = heasarc_query("maxissccat", ADQL)
    print(f"  {len(df):,} sources fetched")

    df.columns = [c.strip().lower() for c in df.columns]

    for col in df.select_dtypes(include=["object"]).columns:
        df[col] = df[col].astype(str).str.strip().replace(
            {"": pd.NA, "None": pd.NA, "nan": pd.NA, "null": pd.NA, "NULL": pd.NA}
        )

    df = df[[c for c in df.columns if c in COLUMN_DESCRIPTIONS]]

    n_total = len(df)
    n_typed = int(df["source_type"].notna().sum()) if "source_type" in df.columns else 0

    type_breakdown = ""
    if "source_type" in df.columns:
        top = df["source_type"].dropna().value_counts().head(6)
        type_breakdown = "\n- Top source types: " + ", ".join(
            f"**{t}** ({n})" for t, n in top.items()
        )

    soft_line = ""
    if "sb_significance" in df.columns:
        sig = pd.to_numeric(df["sb_significance"], errors="coerce").dropna()
        if len(sig):
            soft_line = f"\n- Soft-band (2-4 keV) detection significance ranges from **{sig.min():.1f}** to **{sig.max():.1f}** sigma"

    flux_line = ""
    if "hb_flux" in df.columns:
        flux = pd.to_numeric(df["hb_flux"], errors="coerce").dropna()
        if len(flux):
            flux_line = (
                f"\n- Hard-band (4-10 keV) fluxes span **{flux.min():.2e}** to **{flux.max():.2e}** "
                "erg cm^-2 s^-1 — six orders of magnitude across the persistent X-ray sky"
            )

    quick_stats = f"""\
- **{n_total}** MAXI X-ray sources detected by the all-sky GSC monitor on the ISS
- **{n_typed}** sources with assigned astrophysical classifications{type_breakdown}{soft_line}{flux_line}"""

    usage = """\
```python
from datasets import load_dataset
import matplotlib.pyplot as plt

ds = load_dataset("juliensimon/maxi-xray-sources", split="train").to_pandas()

# Hardness-flux diagram colored by source class
fig, ax = plt.subplots(figsize=(8, 6))
for src_type, sub in ds.dropna(subset=["sb_flux", "hb_flux"]).groupby("source_type"):
    ax.scatter(sub["sb_flux"], sub["hb_flux"], label=src_type, s=40, alpha=0.7)
ax.set_xscale("log")
ax.set_yscale("log")
ax.set_xlabel("Soft band flux (2-4 keV) [erg cm$^{-2}$ s$^{-1}$]")
ax.set_ylabel("Hard band flux (4-10 keV) [erg cm$^{-2}$ s$^{-1}$]")
ax.set_title("MAXI all-sky X-ray monitor — persistent source population")
ax.legend(fontsize=8, loc="lower right")
plt.tight_layout()
plt.show()
```"""

    with Pipeline(
        repo=HF_REPO,
        pretty_name="MAXI X-ray Source Catalog",
        description=DESCRIPTION,
        tags=["space", "astronomy", "x-ray", "maxi", "iss", "jaxa", "heasarc",
              "all-sky-monitor", "x-ray-binaries", "agn", "open-data",
              "tabular-data", "parquet"],
        source_url="https://heasarc.gsfc.nasa.gov/W3Browse/all/maxissccat.html",
        task_categories=["tabular-classification"],
        update_schedule="Quarterly",
        collection_url="https://huggingface.co/collections/juliensimon/astronomy-datasets-69c24caf2f17e36128946743",
        banner={
            "url": "https://images-assets.nasa.gov/image/PIA21085/PIA21085~small.jpg",
            "alt": "Pulsar artist concept — typical MAXI source class",
            "credit": "NASA/JPL-Caltech",
        },
        related_datasets=[
            "juliensimon/swift-bat-hard-xray-survey",
            "juliensimon/chandra-x-ray-sources",
            "juliensimon/4xmm-dr14-xray-sources",
            "juliensimon/nicer-observations",
            "juliensimon/xray-binary-catalog",
            "juliensimon/integral-ibis-hard-xray",
        ],
    ) as p:
        df_clean = p.clean(
            df,
            numeric=["ra", "dec", "lii", "bii", "source_number",
                     "sb_significance", "hb_significance", "sb_flux", "hb_flux",
                     "class"],
            drop_mostly_null_threshold=0.95,
        )
        p.publish(
            df_clean,
            filename="maxi_xray_sources.parquet",
            min_rows=100,
            expected_columns=["name", "ra", "dec", "sb_flux", "hb_flux"],
            critical_columns=["name", "ra", "dec"],
            column_descriptions=COLUMN_DESCRIPTIONS,
            quick_stats=quick_stats,
            usage=usage,
            commit_message=f"Update MAXI source catalog: {n_total} X-ray sources",
        )
    print("Done.")


if __name__ == "__main__":
    main()
