#!/usr/bin/env python3
"""Fetch the IRAS Faint Source Catalog v2.0 from VizieR and upload to HF.

Source: Moshir et al. (1992), IRAS Faint Source Catalog version 2.0 — VizieR II/156A/main
Static dataset — mid-infrared all-sky survey (12, 25, 60, 100 μm).
"""

from hf_dataset_utils import Pipeline
from hf_dataset_utils.tap import vizier_query

HF_REPO = "juliensimon/iras-faint-source-catalog"

ADQL = 'SELECT * FROM "II/156A/main"'

RENAME = {
    "IRAS": "iras_name",
    "RA1950": "ra_1950_deg",
    "DE1950": "dec_1950_deg",
    "Major": "major_axis_arcsec",
    "Minor": "minor_axis_arcsec",
    "PosAng": "pos_angle_deg",
    "Fnu12": "flux_12um_jy",
    "e_Fnu12": "flux_12um_err_pct",
    "q_Fnu12": "flux_12um_quality",
    "Fnu25": "flux_25um_jy",
    "e_Fnu25": "flux_25um_err_pct",
    "q_Fnu25": "flux_25um_quality",
    "Fnu60": "flux_60um_jy",
    "e_Fnu60": "flux_60um_err_pct",
    "q_Fnu60": "flux_60um_quality",
    "Fnu100": "flux_100um_jy",
    "e_Fnu100": "flux_100um_err_pct",
    "q_Fnu100": "flux_100um_quality",
    "SNR12": "snr_12um",
    "SNR25": "snr_25um",
    "SNR60": "snr_60um",
    "SNR100": "snr_100um",
    "Rel": "reliability_pct",
    "nID": "num_associations",
    "Type": "source_type",
}

DROP_COLS = [
    "recno", "o_Fnu12", "o_Fnu25", "o_Fnu60", "o_Fnu100",
    "locSNR12", "locSNR25", "locSNR60", "locSNR100",
    "A12", "A25", "A60", "A100",
    "Ncat", "Nx12", "Nx25", "Nx60", "Nx100",
    "Cir1", "Conf",
    "NoisC12", "NoisC25", "NoisC60", "NoisC100",
    "NoisR12", "NoisR25", "NoisR60", "NoisR100",
]

COLUMN_DESCRIPTIONS = {
    "iras_name": "IRAS source designation in format FHHMM.m+DDMM (prefix F = faint catalog)",
    "ra_1950_deg": "Right ascension (B1950 epoch, degrees) — note: 1950 epoch, not J2000",
    "dec_1950_deg": "Declination (B1950 epoch, degrees) — note: 1950 epoch, not J2000",
    "major_axis_arcsec": "Semi-major axis of 95% confidence position ellipse (arcsec)",
    "minor_axis_arcsec": "Semi-minor axis of 95% confidence position ellipse (arcsec)",
    "pos_angle_deg": "Position angle of major axis east of north (degrees)",
    "flux_12um_jy": "Flux density at 12 μm in Jansky (1 Jy = 10⁻²⁶ W/m²/Hz)",
    "flux_12um_err_pct": "Percentage uncertainty on flux_12um_jy",
    "flux_12um_quality": "Flux quality at 12 μm: 1=high quality, 2=moderate, 3=uncertain, 0=upper limit",
    "flux_25um_jy": "Flux density at 25 μm in Jansky",
    "flux_25um_err_pct": "Percentage uncertainty on flux_25um_jy",
    "flux_25um_quality": "Flux quality at 25 μm: 1=high quality, 2=moderate, 3=uncertain, 0=upper limit",
    "flux_60um_jy": "Flux density at 60 μm in Jansky — dominant band for cool dust emission",
    "flux_60um_err_pct": "Percentage uncertainty on flux_60um_jy",
    "flux_60um_quality": "Flux quality at 60 μm: 1=high quality, 2=moderate, 3=uncertain, 0=upper limit",
    "flux_100um_jy": "Flux density at 100 μm in Jansky — dominant band for cold ISM dust",
    "flux_100um_err_pct": "Percentage uncertainty on flux_100um_jy",
    "flux_100um_quality": "Flux quality at 100 μm: 1=high quality, 2=moderate, 3=uncertain, 0=upper limit",
    "snr_12um": "Signal-to-noise ratio at 12 μm",
    "snr_25um": "Signal-to-noise ratio at 25 μm",
    "snr_60um": "Signal-to-noise ratio at 60 μm",
    "snr_100um": "Signal-to-noise ratio at 100 μm",
    "reliability_pct": "Source reliability percentage (0–99); ≥90 indicates high-confidence point source",
    "num_associations": "Number of counterpart associations in the IRAS Association File",
    "source_type": "Source type flag: 1=point source, 2=small extended, 0=no flux at any band",
}

DESCRIPTION = """\
The IRAS Faint Source Catalog (FSC), version 2.0, contains 173,044 infrared \
point sources detected by the Infrared Astronomical Satellite (IRAS) at \
12, 25, 60, and 100 micrometres. Published by Moshir et al. (1992), the FSC \
extends the IRAS Point Source Catalog to fainter flux levels by applying \
more stringent processing at the cost of sky coverage (~75% of sky, avoiding \
the galactic plane and regions of high infrared cirrus).

IRAS was a joint NASA/Netherlands/UK mission that performed the first sensitive \
all-sky survey in the mid-infrared (August 1983 – November 1983). Its four \
photometric bands — 12, 25, 60, and 100 μm — probed thermal emission from \
warm dust, revealing a zoo of previously hidden astronomical objects: \
ultraluminous infrared galaxies (ULIRGs) driven by starbursts and AGN, \
proto-planetary debris disks around main-sequence stars, asymptotic giant \
branch (AGB) stars with dust shells, and the large-scale structure of the \
interstellar medium through infrared cirrus emission.

The four IRAS bands trace progressively cooler dust: 12 μm traces hot dust and \
PAH emission from star-forming regions; 25 μm traces warm circumstellar dust \
around evolved stars; 60 μm traces cool dust in star-forming regions and \
starburst galaxies; 100 μm traces cold interstellar dust (T ~ 20–30 K). \
The colour ratios between bands (e.g., F60/F25, F100/F60) are powerful \
diagnostics for classifying the dominant heating source.

This dataset fills the mid-infrared gap in the collection: no other dataset \
covers all-sky mid-IR point sources across all source types. It serves as \
the reference catalog for identifying infrared counterparts of radio, optical, \
and X-ray sources, and for building multiwavelength SEDs."""

COLLECTION_URL = "https://huggingface.co/collections/juliensimon/astronomy-datasets-69c24caf2f17e36128946743"


def main():
    print("Fetching IRAS Faint Source Catalog from VizieR...")
    df = vizier_query(ADQL)
    print(f"  {len(df):,} rows fetched")

    df = df.drop(columns=[c for c in DROP_COLS if c in df.columns])
    df = df.rename(columns=RENAME)

    n = len(df)
    # Sources with good flux in each band
    q1_12 = int((df["flux_12um_quality"] == 1).sum())
    q1_60 = int((df["flux_60um_quality"] == 1).sum())
    n_galaxy = int((df["source_type"] == 1).sum())
    median_60 = round(df["flux_60um_jy"].median(), 3)

    quick_stats = f"""\
- **{n:,}** mid-infrared sources across 12, 25, 60 and 100 μm bands
- **{q1_12:,}** high-quality 12 μm detections; **{q1_60:,}** high-quality 60 μm detections
- Median 60 μm flux: **{median_60} Jy** — covers both galactic and extragalactic populations
- Coordinates in B1950 epoch; ~75% sky coverage (galactic plane excluded)"""

    usage = f"""\
```python
from datasets import load_dataset

ds = load_dataset("{HF_REPO}", split="train")
df = ds.to_pandas()

# Colour-colour diagram (F25/F12 vs F60/F25) to separate star-forming galaxies
# from evolved stars and cirrus
import matplotlib.pyplot as plt
import numpy as np

good = df[
    (df["flux_12um_quality"] >= 1) &
    (df["flux_25um_quality"] >= 1) &
    (df["flux_60um_quality"] >= 1) &
    (df["flux_12um_jy"] > 0) &
    (df["flux_25um_jy"] > 0) &
    (df["flux_60um_jy"] > 0)
]
log_f25_f12 = np.log10(good["flux_25um_jy"] / good["flux_12um_jy"])
log_f60_f25 = np.log10(good["flux_60um_jy"] / good["flux_25um_jy"])

plt.figure(figsize=(8, 7))
plt.hexbin(log_f25_f12, log_f60_f25, gridsize=60, cmap="YlOrRd", bins="log")
plt.colorbar(label="log(count)")
plt.xlabel("log(F25/F12)")
plt.ylabel("log(F60/F25)")
plt.title("IRAS FSC colour-colour diagram")
plt.show()
```"""

    with Pipeline(
        repo=HF_REPO,
        pretty_name="IRAS Faint Source Catalog",
        description=DESCRIPTION,
        tags=["space", "infrared", "astronomy", "iras", "mid-infrared", "sky-survey",
              "open-data", "tabular-data", "parquet"],
        source_url="https://vizier.cds.unistra.fr/viz-bin/VizieR-3?-source=II/156A/main",
        license="other",
        license_name="iras-mission-terms",
        license_link="https://irsa.ipac.caltech.edu/Missions/iras.html",
        task_categories=["tabular-classification"],
        collection_url=COLLECTION_URL,
        banner={
            "url": "https://images-assets.nasa.gov/image/GSFC_20171208_Archive_e002215/GSFC_20171208_Archive_e002215~medium.jpg",
            "alt": "All-sky infrared survey mosaic showing the Milky Way in infrared light",
            "credit": "NASA/GSFC",
        },
        related_datasets=[
            "juliensimon/neowise-asteroid-catalog",
            "juliensimon/4xmm-dr14-xray-sources",
            "juliensimon/rosat-bright-source-catalog",
        ],
    ) as p:
        numeric_cols = [k for k in COLUMN_DESCRIPTIONS.keys() if k != "iras_name"]
        df = p.clean(df, numeric=numeric_cols, drop_mostly_null_threshold=0.95)
        p.publish(
            df,
            filename="iras_fsc.parquet",
            min_rows=170_000,
            expected_columns=["iras_name", "ra_1950_deg", "dec_1950_deg"],
            critical_columns=["iras_name"],
            column_descriptions=COLUMN_DESCRIPTIONS,
            quick_stats=quick_stats,
            usage=usage,
            commit_message=f"Upload IRAS FSC v2.0: {n:,} mid-IR sources",
        )
    print("Done.")


if __name__ == "__main__":
    main()
