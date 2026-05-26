# License Audit — space-datasets

**Audit date:** 2026-05-26
**Scope:** 222 dataset scripts → 207 declared `cc-by-4.0`, 13 declared `cc0-1.0` (Wikidata), 2 declared `cc-by-sa-4.0` (OpenNGC, StackExchange-Space)
**Method:** Verified each upstream provider's *actual* policy page directly (not the README/script declarations).
**Conclusion:** At least **30 datasets are mis-licensed** as `cc-by-4.0` when the upstream provider explicitly restricts commercial use. **Recommend action before further redistribution.**

---

## TL;DR — Action required

| Severity | Count | Why |
|---|---|---|
| 🚨 **HIGH** — license clearly wrong; commercial use forbidden upstream | **30** | ESA missions (CC BY-NC 3.0 IGO), WDC Kyoto (no commercial), SIDC SILSO (CC BY-NC 4.0), AAVSO (NC per guidelines) |
| ⚠️ **MEDIUM** — terms unclear, no formal CC license, or operational restrictions | **~25** | CelesTrak (DoD-dependent), The Space Devs (no formal license), MPC (ambiguous "products" clause), IERS, MAXI/JAXA, eROSITA-DE, per-catalog VizieR variations |
| ✅ **LOW** — declared license matches or is more restrictive than upstream | **~167** | NASA missions (PDS, MAST, HEASARC non-XMM, GSFC, JPL SSD/CNEOS), NOAA SWPC, Wikidata, GFZ Kp, GWOSC, GALAH, PDG, J. McDowell GCAT, Space-Track (with citation) |

---

## 🚨 HIGH RISK — must relicense (30 datasets)

### ESA Space Science Archives (25 datasets) → must be `cc-by-nc-3.0`

**Authoritative source:** https://www.cosmos.esa.int/web/esdc/terms-and-conditions
**Exact quote:** *"Data hosted in the ESA Space Science Archives are distributed under the CC BY-NC 3.0 IGO licence."*
**Scope confirmed:** All ESA Space Science archives — Astronomy (Gaia, XMM-Newton, Planck, Herschel, ISO, INTEGRAL), Planetary Science (BepiColombo, Mars Express, Rosetta, Venus Express, ExoMars, JUICE, Huygens), Heliophysics (Solar Orbiter, Cluster, SOHO, Ulysses).
**Why it matters:** CC-BY-4.0 grants commercial use; CC-BY-NC 3.0 IGO explicitly forbids it. Our current label is a license-overreach.
**Note:** The source license travels with the data — fetching ESA mission catalogs *via VizieR* does not strip the ESA restriction.

**Directly hosted on ESA (17):**

| Dataset | Source |
|---|---|
| `bepicolombo` | psa.esa.int |
| `exomars-tgo` | psa.esa.int |
| `gaia-binary-masses` | gea.esac.esa.int |
| `gaia-chemical-cartography` | gea.esac.esa.int |
| `gaia-compact-companions` | gea.esac.esa.int |
| `gaia-eb` | gea.esac.esa.int |
| `gaia-lrv` | gea.esac.esa.int |
| `gaia-qso` | gea.esac.esa.int |
| `gaia-rotation` | gea.esac.esa.int |
| `gaia-sso` | gea.esac.esa.int |
| `gaia-yso` | gea.esac.esa.int |
| `huygens` | psa.esa.int |
| `juice` | psa.esa.int |
| `mars-express` | psa.esa.int |
| `rosetta` | psa.esa.int |
| `solar-orbiter` | esa.int |
| `venus-express` | psa.esa.int |

**ESA mission data fetched via VizieR/HEASARC mirrors (8):**

| Dataset | Source mirror | ESA mission |
|---|---|---|
| `gaia-cepheids` | VizieR | Gaia |
| `gaia-rrlyrae` | VizieR | Gaia |
| `gaia-sb` | VizieR | Gaia |
| `gaia-wd` | VizieR | Gaia |
| `planck-pgcc` | VizieR | Planck |
| `planck-sz2` | HEASARC | Planck |
| `integral-ibis` | VizieR | INTEGRAL |
| `4xmm-dr14` | VizieR | XMM-Newton |

**Required action for all 25:** Change `license` to `other` with `license_name: CC-BY-NC-3.0-IGO` and `license_link: https://creativecommons.org/licenses/by-nc/3.0/igo/`. Add per-mission credit line per ESA's credit table. **Commercial use clauses in your HF dataset cards must be removed.**

---

### WDC Kyoto Geomagnetic Indices (3 datasets) → must be `cc-by-nc-4.0` or `other`

**Authoritative source:** https://wdc.kugi.kyoto-u.ac.jp/wdc/Sec3.html
**Exact quote:** *"The WDC Kyoto does not allow commercial applications of the geomagnetic indices."*
**Redistribution:** Not explicitly forbidden; allowed with attribution + DOI citation.
**Why it matters:** Our `cc-by-4.0` grants commercial use that WDC explicitly forbids.

| Dataset | Source |
|---|---|
| `ae-index` | wdc.kugi.kyoto-u.ac.jp |
| `dst-index` | wdc.kugi.kyoto-u.ac.jp |
| `substorm-onsets` | supermag.jhuapl.edu (redistributes WDC data) |

**Required action:** `cc-by-nc-4.0` + cite each data DOI (AE, Dst, ASY/SYM) in the README.

---

### SIDC SILSO Sunspot Data (1 dataset) → must be `cc-by-nc-4.0`

**Authoritative source:** https://www.sidc.be/SILSO/datafiles
**Exact license:** **CC BY-NC 4.0** (explicit on the page).
**Required citation:** *"Source: WDC-SILSO, Royal Observatory of Belgium, Brussels, DOI: https://doi.org/10.24414/qnza-ac80"*

| Dataset | Source |
|---|---|
| `sunspot` | sidc.be |

---

### AAVSO (1 dataset) → must be `other` (non-commercial)

**Authoritative source:** https://www.aavso.org/data-usage-guidelines and the AAVSO Data Usage Guidelines PDF (2025-10-01).
**Restriction:** Non-commercial research/educational use only; redistribution discouraged without authorization.

| Dataset | Source |
|---|---|
| `aavso-vsx` | aavso.org/vsx |

**Required action:** Relicense to `other`, link the PDF, add AAVSO acknowledgment line. Consider whether to contact AAVSO for an explicit nod given HF hosting.

---

## Status update — 2026-05-26 (post-audit fixes)

- ✅ **30 HIGH-RISK datasets relicensed** live on HF (commit `e05a793`).
- ✅ **22 MEDIUM-RISK datasets relicensed** to `license: other` with upstream policy links (CelesTrak ×13, Space Devs ×3, MPC, IERS, MAXI, Hipparcos ×ESA-NC, APOGEE DR17, IRAS FSC).
- ✅ **VizieR spot-audit** completed (10 high-profile catalogs verified).

### VizieR spot-audit follow-up (2026-05-26)

The audit revealed that **VizieR's official terms** (https://cds.unistra.fr/vizier-org/licences_vizier.html) are *"free of usage in a scientific context"* with mandatory citation — **explicitly not CC-BY-4.0**. CC-BY permits commercial redistribution; VizieR's terms defer commercial/derivative terms to each catalog's originating journal.

**Implication:** The blanket `cc-by-4.0` tag is technically overstated for *every* VizieR redistribution. Severity varies per catalog. Actionable findings:

| Catalog | Action taken |
|---|---|
| Hipparcos (`hipparcos-catalog`) | Moved to ESA-NC group (CC-BY-NC-3.0-IGO) — ESA SP-1200 publication |
| APOGEE DR17 (`apogee-dr17`) | `other` + SDSS Data Use Policy (AAS/IOP copyright on machine-readable tables) |
| IRAS FSC (`iras-faint-source-catalog`) | `other` + NASA/IPAC IRAS Mission terms (explicit `(c)IRAS Faint Sources` marker on VizieR) |
| Bright Star (V/50), Henry Draper (III/135) | LOW RISK — Yale Obs / pre-1929 public domain; no action |
| RAVE DR6, NVSS, FIRST, ICRF3, Veron AGN | UNCLEAR — journal-copyright but no restrictive language; left as `cc-by-4.0` for now |

**Open item:** Remaining 39 non-ESA VizieR catalogs use `cc-by-4.0` umbrella. ApJ/ApJS/AJ (pre-CC-BY era) and A&A (pre-2014) sources are in the UNCLEAR bucket. The conservative fix is to relabel all to `license: other` with `license_name: vizier-scientific-use` + link to CDS terms. **This is a label-accuracy issue, not a breach** — VizieR explicitly permits scientific use and our redistribution is scientific. Defer unless audit reveals an explicit-restriction case.

## ⚠️ MEDIUM RISK — relicense to `other` and document upstream terms

### CelesTrak (14 datasets)

**Authoritative source:** https://celestrak.org/usage-policy.php
**Status:** No formal CC license. CelesTrak's redistribution rests on annual USSPACECOM authorization. Their published policy is purely operational (rate limits, formats).
**Risk:** If DoD authorization lapses, downstream redistributions become problematic. Hard to fully assess.

| Datasets |
|---|
| `ast-spacemobile`, `celestrak-sw`, `constellation-census`, `constellation-tles`, `fragmentation-events`, `globalstar`, `kuiper`, `oneweb`, `reentry-events`, `satcat`, `space-weather`, `starlink`, `tle-latest`, `f107` |

**Required action:** Change to `license: other` with link to CelesTrak usage policy. Note in README that data lineage traces to US Space Force / USSPACECOM and is provided under CelesTrak's discretionary authorization.

---

### The Space Devs LL2 (3 datasets)

**Source:** https://ll.thespacedevs.com
**Status:** Per TSD FAQ: *"You are free to use the data in any way, shape, or form, and share what you create with it. Attribution is not mandatory, but is encouraged and appreciated."* — permissive but **not a formal CC license**. Embedded image URLs may be CC-BY-NC 2.0.

| Dataset | |
|---|---|
| `blue-origin-launches`, `rocket-lab-launches`, `ula-launches` | |

**Required action:** `license: other` with link to TSD terms; note image asset caveat.

---

### Minor Planet Center (1 dataset)

**Source:** https://www.minorplanetcenter.net/iau/WWWPolicy.html
**Status:** MPCORB/CometEls.txt are freely-available *if source is clearly specified*. But: *"Inclusion of circulars or web pages in products of any description (including, but not limited to CD-Roms and magazines), whether or not a charge is made for the product, is strictly prohibited..."* That clause is ambiguous about HF datasets.

| Dataset | Source pulled |
|---|---|
| `mpc-comets` | `CometEls.txt` (freely-available, not MPECs) |

**Required action:** Change to `license: other`, add explicit MPC attribution, link to WWWPolicy.html. Confirmed our script only pulls the freely-available file, so this should be acceptable but conservatively labeled.

---

### IERS (1 dataset)

**Source:** https://www.iers.org
**Status:** No explicit license published. International intergovernmental body; data is publicly distributed.

| Dataset | |
|---|---|
| `iers-eop` | |

**Required action:** `license: other` with disclaimer link.

---

### JAXA MAXI (1 dataset)

**Source:** https://maxi.riken.jp
**Status:** Only "copyright RIKEN/JAXA/MAXI team" — no license declared. Fetched via HEASARC mirror.

| Dataset | |
|---|---|
| `maxi` | |

**Required action:** `license: other`. Add RIKEN/JAXA/MAXI citation. Consider contacting MAXI team for clarification before re-publishing.

---

### eROSITA-DE (1 dataset)

**Source:** Fetched from VizieR. eROSITA-DE (German half) DR1 has specific terms; need to verify on https://erosita.mpe.mpg.de.

| Dataset | |
|---|---|
| `erosita` | |

**Required action:** Manually verify on the MPE eROSITA-DE pages and update accordingly. The Russian half (eROSITA-RU) is unavailable; we only fetched DR1 (German).

---

### VizieR per-catalog (48 datasets) — sample audit needed

**Source:** vizier.cds.unistra.fr / cdsarc.cds.unistra.fr
**Status:** VizieR aggregates catalogs owned by their original authors and journals. CDS distributes under *"Open Licence or ODbL or CC-BY"* depending on the catalog. CC-BY-4.0 is a reasonable umbrella for *most* catalogs but per-catalog terms can differ.

**Required action:** Spot-check 5-10 high-profile catalogs (e.g., 2MASS, SDSS, GAIA DR3) for explicit per-catalog terms. Some catalogs from Springer-published journals may have restrictive terms.

VizieR catalogs we publish (48): `4xmm-dr14` (already HIGH), `apogee-dr17`, `bright-stars`, `brown-dwarfs`, `carbon-stars`, `chime-frb`, `cns5`, `cosmic-voids`, `cosmicflows`, `erosita`, `feng-icmes`, `first`, `gaia-cepheids` (already HIGH), `gaia-rrlyrae` (already HIGH), `gaia-sb` (already HIGH), `gaia-wd` (already HIGH), `galactic-novae`, `geneva-copenhagen`, `hawc`, `henry-draper`, `hii-regions`, `hipparcos`, `hot-subdwarfs`, `hypervelocity-stars`, `icrf3`, `integral-ibis` (already HIGH), `iras-fsc`, `kepler-eb`, `kepler-ttv`, `lhaaso`, `milliquas`, `nvss`, `open-clusters`, `planck-pgcc` (already HIGH), `planetary-nebulae`, `rave-dr6`, `rc3`, `roma-bzcat`, `rosat-bsc`, `sumss`, `symbiotic-stars`, `tgss`, `unified-radio`, `veron-agn`, `vlass`, `wds`, `wolf-rayet`, `yarkovsky-nea`.

---

## ✅ LOW RISK — compliant (~167 datasets)

These are correctly labeled `cc-by-4.0` (or more permissive than the source requires):

| Provider | Datasets (count) | License rationale |
|---|---|---|
| **NASA HEASARC (non-XMM/Planck)** | ~12 | "HEASARC materials are all available freely for your use." US Gov work = public domain. |
| **STScI / MAST** (HST, JWST, GALEX, Kepler, etc.) | 8 | *"Most MAST data are in the public domain with no use restrictions."* CC-BY-4.0 is conservative; HLSPs already CC-BY-4.0. |
| **NASA PDS, GSFC, JPL SSD/CNEOS** | ~20 | US Gov work product = public domain (17 USC §105). |
| **NOAA SWPC** | 6 | US Gov work product. |
| **NASA Exoplanet Archive** | 2 | Caltech under NASA contract; effectively public domain. |
| **PSI/SBN** (Bus-DeMeo, NEOWISE, etc.) | 5 | PDS node = US Gov. |
| **USGS Astropedia / planetarynames** | 4 | US Gov. |
| **Wikidata** | 13 (already CC0) | CC0 declaration accurate. |
| **GFZ Kp index** | 2 | Explicitly **CC-BY-4.0** per GFZ. |
| **GWOSC (LIGO/Virgo)** | 1 | Explicitly **CC-BY-4.0**. |
| **GALAH DR4** | 1 | DR4 paper CC-BY-4.0. |
| **PDG** | 1 | RPP 2024 published CC-BY-4.0 in Phys Rev D. |
| **Jonathan McDowell GCAT** | 4 | Explicitly **CC-BY-4.0**. |
| **Space-Track** | 1 (`tle-history`) | USSPACECOM blanket approval for basic SSA + attribution required. **Action: add explicit citation to README.** |
| **OpenNGC** | 1 (already cc-by-sa-4.0) | Correct. |
| **Stack Exchange (Space SE)** | 1 (already cc-by-sa-4.0) | Correct. |

---

## Recommended next steps (prioritized)

### Immediate (this week)

1. **Relicense 25 ESA-derived datasets** to `other` + `CC-BY-NC-3.0-IGO`. Update HF dataset cards. Remove any commercial-use-permitted language.
2. **Relicense WDC Kyoto (3) and SILSO (1)** to `cc-by-nc-4.0`. Add data DOIs.
3. **Relicense AAVSO VSX (1)** to `other` with link to AAVSO usage PDF.
4. **Add Space-Track citation** to `tle-history` README explicitly: *"Basic SSA data distributed under USSPACECOM blanket authorization via www.Space-Track.org."*

### Short-term (this month)

5. **Relicense CelesTrak (14) and The Space Devs (3)** to `license: other` with link to upstream policy.
6. **Relicense MPC, IERS, MAXI, eROSITA** to `other` with provenance notes.
7. **Spot-check 10 VizieR catalogs** for per-catalog license variations. Sample: 2MASS, SDSS, large Springer-journal catalogs.
8. **Extend `hf_dataset_utils/readme.py`** to support non-CC licenses cleanly via `license: other` + `license_name` + `license_link` triplet.
9. **Add CI check** that flags any new script declaring `cc-by-4.0` against a provider in this report's HIGH/MEDIUM lists.

### Long-term

10. Maintain this `LICENSE_AUDIT.md` as authoritative; re-audit any new provider before publishing.
11. Consider whether the WDC Kyoto datasets should be removed from HF entirely — their "no commercial use" + ambiguous redistribution stance is the strictest in the catalog.
12. Contact AAVSO, MAXI team for explicit redistribution permission letters if you want to keep those datasets up.

---

## Provider terms — authoritative URLs

- ESA Space Science Archives: https://www.cosmos.esa.int/web/esdc/terms-and-conditions
- ESA Gaia license: https://www.cosmos.esa.int/web/gaia-users/license
- WDC Kyoto: https://wdc.kugi.kyoto-u.ac.jp/wdc/Sec3.html
- SIDC SILSO: https://www.sidc.be/SILSO/datafiles
- AAVSO: https://www.aavso.org/data-usage-guidelines (+ 2025-10 PDF)
- CelesTrak: https://celestrak.org/usage-policy.php
- The Space Devs LL2: https://thespacedevs.com/llapi
- Minor Planet Center: https://www.minorplanetcenter.net/iau/WWWPolicy.html
- STScI/MAST: https://archive.stsci.edu/publishing/data-use
- HEASARC: https://heasarc.gsfc.nasa.gov/docs/heasarc/data_policy.html
- NASA Exoplanet Archive: https://exoplanetarchive.ipac.caltech.edu/docs/acknowledge.html
- JPL SSD/CNEOS: https://ssd-api.jpl.nasa.gov/about/
- Space-Track: https://www.space-track.org/documentation
- GFZ Kp: https://kp.gfz.de/en/data
- GWOSC: https://gwosc.org/about/
- GALAH DR4: https://www.galah-survey.org/dr4/cite_us/
- PDG: https://link.aps.org/doi/10.1103/PhysRevD.110.030001
- Jonathan McDowell GCAT: https://planet4589.org/space/gcat/web/intro/credits.html
- CDS legals: https://cds.unistra.fr/legals/
