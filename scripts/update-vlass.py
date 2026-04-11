#!/usr/bin/env python3
"""Fetch VLASS Epoch 1 Quick Look component catalog from VizieR and upload to HF.

Source: Gordon et al. (2021, ApJS 255, 30) — VLASS Epoch 1 Quick Look
component catalog processed by CIRADA, S-band (2-4 GHz).
VizieR catalog: J/ApJS/255/30
"""

import pandas as pd

from hf_dataset_utils import Pipeline
from hf_dataset_utils.tap import vizier_query

HF_REPO = "juliensimon/vlass-radio-sources"

# ── Source query ────────────────────────────────────────────────────
ADQL = """SELECT * FROM "J/ApJS/255/30/comp" """

# ── Column mapping ──────────────────────────────────────────────────
RENAME = {
    "CompName": "component_name",
    "CompId": "component_id",
    "IslId": "island_id",
    "RAJ2000": "ra_deg",
    "DEJ2000": "dec_deg",
    "e_RAJ2000": "ra_error_deg",
    "e_DEJ2000": "dec_error_deg",
    "Ftot": "total_flux_mjy",
    "e_Ftot": "total_flux_error_mjy",
    "Fpeak": "peak_flux_mjy_beam",
    "e_Fpeak": "peak_flux_error_mjy_beam",
    "Maj": "major_axis_arcsec",
    "e_Maj": "major_axis_error_arcsec",
    "Min": "minor_axis_arcsec",
    "e_Min": "minor_axis_error_arcsec",
    "PA": "position_angle_deg",
    "e_PA": "position_angle_error_deg",
    "FtotIsl": "island_total_flux_mjy",
    "e_FtotIsl": "island_total_flux_error_mjy",
    "Islrms": "island_rms_mjy_beam",
    "Islmean": "island_mean_mjy_beam",
    "ResIdIslrms": "residual_island_rms_mjy_beam",
    "ResidIslmean": "residual_island_mean_mjy_beam",
    "RAMdeg": "peak_ra_deg",
    "DEMdeg": "peak_dec_deg",
    "e_RAMdeg": "peak_ra_error_deg",
    "e_DEMdeg": "peak_dec_error_deg",
    "SCode": "source_code",
    "Xposn": "x_pixel",
    "e_Xposn": "x_pixel_error",
    "Yposn": "y_pixel",
    "e_Yposn": "y_pixel_error",
    "XposnMax": "peak_x_pixel",
    "e_XposnMax": "peak_x_pixel_error",
    "YposnMax": "peak_y_pixel",
    "e_YposnMax": "peak_y_pixel_error",
    "MajImgPlane": "major_axis_imgplane_arcsec",
    "e_MajImgPlane": "major_axis_imgplane_error_arcsec",
    "MinImgPlane": "minor_axis_imgplane_arcsec",
    "e_MinImgPlane": "minor_axis_imgplane_error_arcsec",
    "PAImgPlane": "pa_imgplane_deg",
    "e_PAImgPlane": "pa_imgplane_error_deg",
    "DCMaj": "deconv_major_arcsec",
    "e_DCMaj": "deconv_major_error_arcsec",
    "DCMin": "deconv_minor_arcsec",
    "e_DCMin": "deconv_minor_error_arcsec",
    "DCPA": "deconv_pa_deg",
    "e_DCPA": "deconv_pa_error_deg",
    "DCMajImgPlane": "deconv_major_imgplane_arcsec",
    "e_DCMajImgPlane": "deconv_major_imgplane_error_arcsec",
    "DCMinImgPlane": "deconv_minor_imgplane_arcsec",
    "e_DCMinImgPlane": "deconv_minor_imgplane_error_arcsec",
    "DCPAImgPlane": "deconv_pa_imgplane_deg",
    "e_DCPAImgPlane": "deconv_pa_imgplane_error_deg",
    "Tile": "tile",
    "Subtile": "subtile",
    "RASdeg": "subtile_ra_deg",
    "DESdeg": "subtile_dec_deg",
    "NVSSdist": "nvss_distance_arcsec",
    "FIRSTdist": "first_distance_arcsec",
    "PeakToRing": "peak_to_ring_ratio",
    "DupFlag": "duplicate_flag",
    "QualFlag": "quality_flag",
    "NNdist": "nearest_neighbor_arcsec",
    "BMaj": "beam_major_arcsec",
    "BMin": "beam_minor_arcsec",
    "BPA": "beam_pa_deg",
    "MainSample": "main_sample",
    "QLcutout": "ql_cutout_url",
}

# ── Column descriptions for README schema table ────────────────────
COLUMN_DESCRIPTIONS = {
    "component_name": "IAU component name in the format 'VLASS1QLCIR JHHMMSS.ss+DDMMSS.s'; encodes J2000 position and survey epoch",
    "component_id": "Unique integer identifier for this Gaussian component within the CIRADA catalog",
    "island_id": "Identifier of the emission island this component belongs to; multiple components may share an island for complex sources",
    "ra_deg": "Right ascension J2000 in degrees (0-360) from the Gaussian component fit; typical astrometric accuracy ~0.5 arcsec for bright sources",
    "dec_deg": "Declination J2000 in degrees (-90 to +90); survey covers declination > -40 deg (~33,885 sq deg)",
    "ra_error_deg": "1-sigma uncertainty on right ascension in degrees from the Gaussian fit",
    "dec_error_deg": "1-sigma uncertainty on declination in degrees from the Gaussian fit",
    "total_flux_mjy": "Integrated flux density at S-band (2-4 GHz, central ~3 GHz) in mJy; sum of the fitted Gaussian component",
    "total_flux_error_mjy": "1-sigma uncertainty on integrated flux density in mJy",
    "peak_flux_mjy_beam": "Peak surface brightness at S-band in mJy/beam; best flux estimator for unresolved point sources at ~2.5 arcsec resolution",
    "peak_flux_error_mjy_beam": "1-sigma uncertainty on peak flux density in mJy/beam",
    "major_axis_arcsec": "Fitted (beam-convolved) major axis FWHM in arcseconds; includes the ~2.5 arcsec synthesized beam",
    "major_axis_error_arcsec": "1-sigma uncertainty on the fitted major axis in arcseconds",
    "minor_axis_arcsec": "Fitted (beam-convolved) minor axis FWHM in arcseconds",
    "minor_axis_error_arcsec": "1-sigma uncertainty on the fitted minor axis in arcseconds",
    "position_angle_deg": "Fitted position angle of the major axis in degrees east from north",
    "position_angle_error_deg": "1-sigma uncertainty on the fitted position angle in degrees",
    "island_total_flux_mjy": "Total integrated flux of the parent emission island in mJy; equals total_flux_mjy for single-component islands",
    "island_total_flux_error_mjy": "1-sigma uncertainty on the island total flux in mJy",
    "island_rms_mjy_beam": "Local rms noise in mJy/beam measured in the island region; indicates detection sensitivity at this sky position",
    "island_mean_mjy_beam": "Mean background level in the island region in mJy/beam; should be near zero for well-calibrated images",
    "residual_island_rms_mjy_beam": "Rms of the residual image after component subtraction in mJy/beam; high values indicate poor fit",
    "residual_island_mean_mjy_beam": "Mean of the residual image after component subtraction in mJy/beam",
    "peak_ra_deg": "Right ascension of the peak pixel in degrees; may differ from Gaussian center for asymmetric sources",
    "peak_dec_deg": "Declination of the peak pixel in degrees",
    "peak_ra_error_deg": "1-sigma uncertainty on peak pixel right ascension in degrees",
    "peak_dec_error_deg": "1-sigma uncertainty on peak pixel declination in degrees",
    "source_code": "PyBDSF source structure code: S (single isolated component), C (component of a complex source), M (multiple-Gaussian island), E (extended emission)",
    "x_pixel": "X pixel coordinate of the Gaussian center in the image plane",
    "x_pixel_error": "1-sigma uncertainty on x pixel coordinate",
    "y_pixel": "Y pixel coordinate of the Gaussian center in the image plane",
    "y_pixel_error": "1-sigma uncertainty on y pixel coordinate",
    "peak_x_pixel": "X pixel coordinate of the peak brightness pixel",
    "peak_x_pixel_error": "1-sigma uncertainty on peak x pixel coordinate",
    "peak_y_pixel": "Y pixel coordinate of the peak brightness pixel",
    "peak_y_pixel_error": "1-sigma uncertainty on peak y pixel coordinate",
    "major_axis_imgplane_arcsec": "Major axis FWHM in arcseconds measured in the image plane before deconvolution",
    "major_axis_imgplane_error_arcsec": "1-sigma uncertainty on image-plane major axis in arcseconds",
    "minor_axis_imgplane_arcsec": "Minor axis FWHM in arcseconds measured in the image plane before deconvolution",
    "minor_axis_imgplane_error_arcsec": "1-sigma uncertainty on image-plane minor axis in arcseconds",
    "pa_imgplane_deg": "Position angle in degrees measured in the image plane",
    "pa_imgplane_error_deg": "1-sigma uncertainty on image-plane position angle in degrees",
    "deconv_major_arcsec": "Deconvolved major axis FWHM in arcseconds after removing the synthesized beam; null or zero for unresolved sources",
    "deconv_major_error_arcsec": "1-sigma uncertainty on deconvolved major axis in arcseconds",
    "deconv_minor_arcsec": "Deconvolved minor axis FWHM in arcseconds; nonzero confirms the source is spatially resolved",
    "deconv_minor_error_arcsec": "1-sigma uncertainty on deconvolved minor axis in arcseconds",
    "deconv_pa_deg": "Deconvolved position angle of the major axis in degrees east from north",
    "deconv_pa_error_deg": "1-sigma uncertainty on deconvolved position angle in degrees",
    "deconv_major_imgplane_arcsec": "Deconvolved major axis in arcseconds from image-plane fitting",
    "deconv_major_imgplane_error_arcsec": "1-sigma uncertainty on image-plane deconvolved major axis in arcseconds",
    "deconv_minor_imgplane_arcsec": "Deconvolved minor axis in arcseconds from image-plane fitting",
    "deconv_minor_imgplane_error_arcsec": "1-sigma uncertainty on image-plane deconvolved minor axis in arcseconds",
    "deconv_pa_imgplane_deg": "Deconvolved position angle in degrees from image-plane fitting",
    "deconv_pa_imgplane_error_deg": "1-sigma uncertainty on image-plane deconvolved position angle in degrees",
    "tile": "VLASS survey tile identifier; maps to a specific sky region in the observing grid",
    "subtile": "Subtile identifier within the parent tile; finer spatial subdivision for image processing",
    "subtile_ra_deg": "Right ascension of the subtile center in degrees",
    "subtile_dec_deg": "Declination of the subtile center in degrees",
    "nvss_distance_arcsec": "Angular separation from the nearest NVSS (1.4 GHz) source in arcseconds; useful for cross-matching and variability studies",
    "first_distance_arcsec": "Angular separation from the nearest FIRST (1.4 GHz) source in arcseconds; useful for high-resolution cross-matching",
    "peak_to_ring_ratio": "Ratio of peak flux to median flux in a surrounding ring; high values indicate reliable detections, low values may flag artifacts",
    "duplicate_flag": "Duplicate detection flag: 0 = unique detection, nonzero = overlapping tile duplicate that should be excluded from main analyses",
    "quality_flag": "Quality flag: 0 = good quality, nonzero = potential issues with calibration or imaging artifacts",
    "nearest_neighbor_arcsec": "Angular distance to the nearest catalog neighbor in arcseconds; useful for source density and confusion studies",
    "beam_major_arcsec": "Synthesized beam major axis FWHM in arcseconds at this sky position; typically ~2.5 arcsec in B-configuration",
    "beam_minor_arcsec": "Synthesized beam minor axis FWHM in arcseconds; varies with declination and hour angle coverage",
    "beam_pa_deg": "Synthesized beam position angle in degrees east from north",
    "main_sample": "Main sample membership flag: 1 = curated quality-filtered duplicate-free subset recommended for most analyses; 0 = excluded",
    "ql_cutout_url": "URL to the Quick Look image cutout centered on this source; provides visual context for source morphology and environment",
    "is_resolved": "True if the deconvolved major axis > 0, indicating the source is spatially resolved at ~2.5 arcsec resolution; derived flag",
}

# ── Dataset description ─────────────────────────────────────────────
DESCRIPTION = """\
The Very Large Array Sky Survey (VLASS) Epoch 1 Quick Look component catalog from \
CIRADA, containing radio source detections at S-band (2-4 GHz) with ~2.5 arcsecond \
resolution, covering the sky north of declination -40 degrees. VLASS is the modern \
successor to NVSS and FIRST, offering higher resolution and multi-epoch coverage.

VLASS is a synoptic all-sky radio survey using the Karl G. Jansky Very Large Array \
(VLA) in its B-configuration at S-band (2-4 GHz). The survey covers the entire sky \
visible to the VLA (declination > -40 deg, ~33,885 sq. deg.) in three epochs. This \
catalog contains Quick Look component detections from Epoch 1, processed by the \
Canadian Initiative for Radio Astronomy Data Analysis (CIRADA). Each row is a \
Gaussian component fitted to a radio detection using PyBDSF.

VLASS represents a generational leap over its predecessors NVSS and FIRST, combining \
NVSS-like sky coverage with FIRST-like angular resolution at a higher frequency \
(3 GHz vs. 1.4 GHz). The survey's three-epoch design, with observations spanning \
2017 to 2024, enables systematic studies of radio variability and transient phenomena \
on timescales of months to years. The S-band frequency coverage (2-4 GHz) provides \
sensitivity to flat-spectrum and inverted-spectrum sources such as compact AGN cores, \
while still detecting the steep-spectrum synchrotron emission from radio lobes and jets.
"""


def main():
    print("Fetching VLASS Epoch 1 Quick Look component catalog from VizieR...")
    df = vizier_query(ADQL)
    print(f"  {len(df):,} raw rows")

    # Rename columns
    df = df.rename(columns={k: v for k, v in RENAME.items() if k in df.columns})

    # Integer columns
    for col in ["component_id", "island_id", "duplicate_flag", "quality_flag", "main_sample"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").astype("Int32")

    # Derived column: resolved flag
    if "deconv_major_arcsec" in df.columns:
        df["is_resolved"] = df["deconv_major_arcsec"] > 0

    # Sort by RA
    df = df.sort_values("ra_deg").reset_index(drop=True)

    # Drop VizieR internal columns
    for col in ["recno"]:
        if col in df.columns:
            df = df.drop(columns=[col])

    # Keep only described columns
    df = df[[c for c in df.columns if c in COLUMN_DESCRIPTIONS]]

    # ── Domain-specific stats for README ─────────────────────────────
    n_total = len(df)
    n_main = int(df["main_sample"].sum()) if "main_sample" in df.columns else 0
    n_resolved = int(df["is_resolved"].sum()) if "is_resolved" in df.columns else 0
    flux_median = df["peak_flux_mjy_beam"].median()
    dec_min, dec_max = df["dec_deg"].min(), df["dec_deg"].max()

    quick_stats = f"""\
- **{n_total:,}** total component detections at S-band (2-4 GHz)
- **{n_main:,}** main sample sources (quality-filtered, duplicate-free)
- **{n_resolved:,}** resolved sources ({n_resolved / n_total * 100:.1f}%)
- Median peak flux: {flux_median:.2f} mJy/beam
- Declination range: {dec_min:.1f} to {dec_max:.1f} degrees
- Frequency: S-band (2-4 GHz), ~2.5 arcsec resolution"""

    usage = """\
```python
from datasets import load_dataset

ds = load_dataset("juliensimon/vlass-radio-sources", split="train")
df = ds.to_pandas()

# Main sample only (quality-filtered)
main = df[df["main_sample"] == 1]
print(f"Main sample: {len(main):,} sources")

# Flux distribution
import matplotlib.pyplot as plt
df["peak_flux_mjy_beam"].clip(upper=100).hist(bins=200, log=True)
plt.xlabel("Peak flux (mJy/beam)")
plt.ylabel("Count")
plt.title("VLASS Source Flux Distribution")
plt.show()

# Sky density map
plt.hexbin(df["ra_deg"], df["dec_deg"], gridsize=100, mincnt=1)
plt.colorbar(label="Source count")
plt.xlabel("RA (deg)")
plt.ylabel("Dec (deg)")
plt.title("VLASS Epoch 1 Sky Density")
plt.show()

# Cross-match proximity to NVSS/FIRST
has_nvss = df["nvss_distance_arcsec"] < 10
print(f"Within 10 arcsec of NVSS source: {has_nvss.sum():,}")
```"""

    with Pipeline(
        repo=HF_REPO,
        pretty_name="VLASS Radio Sources (Epoch 1)",
        description=DESCRIPTION,
        tags=["space", "radio", "vlass", "vla", "nrao", "astronomy",
              "open-data", "tabular-data", "parquet"],
        source_url="https://vizier.cds.unistra.fr/viz-bin/VizieR-3?-source=J/ApJS/255/30",
        task_categories=["tabular-classification"],
        collection_url="https://huggingface.co/collections/juliensimon/astronomy-datasets-69c24caf2f17e36128946743",
        banner={
            "url": "https://images-assets.nasa.gov/image/PIA13277/PIA13277~small.jpg",
            "alt": "Deep Space Network antenna at Goldstone",
            "credit": "NASA/JPL-Caltech",
        },
        related_datasets=[
            "juliensimon/nvss-radio-catalog",
            "juliensimon/first-radio-catalog",
            "juliensimon/unified-radio-catalog",
        ],
    ) as p:
        df = p.clean(
            df,
            numeric=[
                "ra_deg", "dec_deg", "ra_error_deg", "dec_error_deg",
                "total_flux_mjy", "total_flux_error_mjy",
                "peak_flux_mjy_beam", "peak_flux_error_mjy_beam",
                "major_axis_arcsec", "major_axis_error_arcsec",
                "minor_axis_arcsec", "minor_axis_error_arcsec",
                "position_angle_deg", "position_angle_error_deg",
                "island_total_flux_mjy", "island_total_flux_error_mjy",
                "island_rms_mjy_beam", "island_mean_mjy_beam",
                "residual_island_rms_mjy_beam", "residual_island_mean_mjy_beam",
                "peak_ra_deg", "peak_dec_deg", "peak_ra_error_deg", "peak_dec_error_deg",
                "subtile_ra_deg", "subtile_dec_deg",
                "nvss_distance_arcsec", "first_distance_arcsec",
                "peak_to_ring_ratio", "nearest_neighbor_arcsec",
                "beam_major_arcsec", "beam_minor_arcsec", "beam_pa_deg",
                "deconv_major_arcsec", "deconv_major_error_arcsec",
                "deconv_minor_arcsec", "deconv_minor_error_arcsec",
                "deconv_pa_deg", "deconv_pa_error_deg",
                "x_pixel", "x_pixel_error", "y_pixel", "y_pixel_error",
                "peak_x_pixel", "peak_x_pixel_error", "peak_y_pixel", "peak_y_pixel_error",
                "major_axis_imgplane_arcsec", "major_axis_imgplane_error_arcsec",
                "minor_axis_imgplane_arcsec", "minor_axis_imgplane_error_arcsec",
                "pa_imgplane_deg", "pa_imgplane_error_deg",
                "deconv_major_imgplane_arcsec", "deconv_major_imgplane_error_arcsec",
                "deconv_minor_imgplane_arcsec", "deconv_minor_imgplane_error_arcsec",
                "deconv_pa_imgplane_deg", "deconv_pa_imgplane_error_deg",
            ],
            drop_mostly_null_threshold=0.95,
        )
        p.publish(
            df,
            filename="vlass_radio_sources.parquet",
            min_rows=500_000,
            expected_columns=["component_name", "ra_deg", "dec_deg", "total_flux_mjy", "peak_flux_mjy_beam"],
            critical_columns=["component_name", "ra_deg", "dec_deg", "peak_flux_mjy_beam"],
            column_descriptions=COLUMN_DESCRIPTIONS,
            quick_stats=quick_stats,
            usage=usage,
            commit_message=f"Update VLASS radio sources: {n_total:,} components",
        )
    print("Done.")


if __name__ == "__main__":
    main()
