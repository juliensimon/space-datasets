#!/usr/bin/env python3
"""Fetch FCC NGSO satellite filings metadata from the IBFS public record.

Source: FCC International Bureau Filing System (IBFS), accessed via the third-party
fcc.report mirror which provides structured HTML per file number. Covers the major
NGSO satellite constellation applications (Starlink, Kuiper, OneWeb, Telesat Lightspeed,
etc.) — the authoritative public record of who has asked the FCC for permission to
launch and operate which constellations.

The hand-curated seed file at scripts/data/fcc_ngso_seed.json supplies the IBFS file
number, operator family, human-readable system name, requested satellite count, and
orbital shell breakdown (since these live in filing PDF attachments, not the HTML
landing page). Everything else is scraped from fcc.report per filing.
"""

import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import requests
from bs4 import BeautifulSoup

from hf_dataset_utils import Pipeline

SEED_PATH = Path(__file__).parent / "data" / "fcc_ngso_seed.json"
BASE_URL = "https://fcc.report/IBFS"
HF_REPO = "juliensimon/fcc-ngso-filings"

USER_AGENT = "juliensimon-space-datasets/1.0 (fcc-ngso-filings pipeline; +https://huggingface.co/datasets/juliensimon/fcc-ngso-filings)"
REQUEST_SLEEP_SEC = 2.0

VALID_OPERATOR_FAMILIES = {
    "spacex", "amazon", "oneweb", "blue_origin", "telesat", "ast",
    "boeing", "viasat", "globalstar", "iridium", "other",
}

COLUMN_DESCRIPTIONS = {
    "file_number": "FCC IBFS file number in the form PREFIX-TYPE-YYYYMMDD-NNNNN (e.g. SAT-LOA-20190704-00057)",
    "applicant": "Filing applicant legal entity (e.g. Kuiper Systems LLC, Space Exploration Holdings, LLC)",
    "operator_family": "Normalized operator group (spacex, amazon, oneweb, blue_origin, telesat, ast, boeing, viasat, globalstar, iridium, other)",
    "system_name": "Human-readable constellation name (Starlink Gen2, Project Kuiper, OneWeb Gen1, etc.)",
    "filing_type": "IBFS filing type extracted from the file number: LOA (Launch and Operate), MOD (Modification), MPL (Market-Access Petition), AMD (Amendment), LOI (Letter of Intent), PDR (Petition for Declaratory Ruling)",
    "nature_of_service": "FCC service classification (Fixed Satellite Service, Mobile Satellite Service, etc.)",
    "status": "Current processing status (Action Complete, Pending, Dismissed, etc.)",
    "last_action": "Most recent action taken (Grant of Authority, Application Filed, etc.)",
    "date_filed": "Date the filing was submitted to the FCC",
    "date_granted": "Date authorization was granted (null for pending or denied applications)",
    "last_action_date": "Date of the most recent action on the filing",
    "requested_satellites": "Total satellite count requested in the filing, as disclosed in filing attachments",
    "orbital_shells_json": "JSON array of shell descriptors (altitude_km, inclination_deg, satellite_count) — structure of the requested constellation",
    "frequency_bands": "Comma-separated MHz band edges from the Frequency Summary table (e.g. 17700-18200,27500-28350)",
    "description": "Filing description or abstract as published on the IBFS landing page",
    "applicant_address": "Mailing address on the filing",
    "ibfs_url": "Canonical URL of the filing on fcc.report",
    "fetched_at_utc": "UTC timestamp when this row was refreshed from fcc.report",
}

DESCRIPTION = """\
Structured metadata for the major FCC NGSO (non-geostationary satellite orbit) constellation \
filings — the authoritative public record of who has asked the US Federal Communications \
Commission for permission to launch and operate which mega-constellations. Includes Starlink \
Gen1 and Gen2, Amazon Project Kuiper, OneWeb, Telesat Lightspeed, and other major systems \
from the FCC International Bureau Filing System (IBFS).

The FCC IBFS is the regulatory backbone of the LEO broadband race. Every constellation \
operator that wants to serve US customers (or use US spectrum, or launch from US soil) must \
obtain FCC authorization through an IBFS filing. The filing discloses the requested number of \
satellites, orbital shells, frequency bands, and service type. Status transitions from \
Application Filed through Accepted for Filing, Comment Period, and eventually Grant of \
Authority or Dismissal. This dataset captures that process as structured data.

Where the companion constellation-health datasets (juliensimon/starlink-fleet-data, \
juliensimon/kuiper-fleet-data, juliensimon/oneweb-fleet-data) track what is actually flying, \
this dataset tracks what was asked for. The gap between requested_satellites and the observed \
operational count is the honest measure of how close each operator is to delivering on its \
FCC promises. Two hand-curated columns — requested_satellites and orbital_shells_json — are \
transcribed from filing PDF attachments because those technical parameters are not exposed on \
the HTML landing page; all other fields are scraped from the public IBFS record. Weekly refresh.

Source: FCC IBFS via fcc.report (third-party mirror, not affiliated with the FCC). The \
underlying filings are public records of the US federal government.\
"""


def load_seed():
    with open(SEED_PATH) as f:
        data = json.load(f)
    return data["filings"]


def _session():
    s = requests.Session()
    s.headers["User-Agent"] = USER_AGENT
    return s


def _clean(s):
    return re.sub(r"\s+", " ", s).strip() if s else ""


def fetch_filing(session, file_number):
    url = f"{BASE_URL}/{file_number}"
    resp = session.get(url, timeout=60)
    if resp.status_code >= 500:
        # One retry with backoff
        time.sleep(5)
        resp = session.get(url, timeout=60)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    # Title: "Application for <service> by <applicant> [<file_number>]"
    title = _clean(soup.title.string if soup.title else "")
    m = re.search(r"by (.+?) \[" + re.escape(file_number) + r"\]", title)
    applicant_from_title = m.group(1) if m else ""
    if not applicant_from_title:
        raise RuntimeError(
            f"No applicant found on fcc.report page for {file_number} — "
            f"the page is empty or the file number does not exist"
        )

    # Description meta
    meta_desc = soup.find("meta", {"name": "Description"})
    description = _clean(meta_desc["content"]) if meta_desc else ""

    # Core metadata: first table inside <div class=well>
    well = soup.find("div", class_="well")
    kv = {}
    if well:
        meta_tbl = well.find("table", class_="table")
        if meta_tbl:
            for tr in meta_tbl.find_all("tr"):
                tds = tr.find_all("td")
                if len(tds) == 2:
                    k = _clean(tds[0].get_text())
                    v = _clean(tds[1].get_text())
                    kv[k] = v

    # Applicant block: <h5>Applicant</h5> inside a column div
    applicant = applicant_from_title
    applicant_address = ""
    app_h5 = soup.find("h5", string="Applicant")
    if app_h5:
        parent = app_h5.parent
        # Get text after the h5
        text = parent.get_text("\n", strip=True)
        lines = [line for line in text.splitlines() if line and line != "Applicant"]
        if lines:
            applicant = lines[0]
            applicant_address = " ".join(lines[1:])

    # Frequency Summary: table under <h3>Frequency Summary</h3>
    freq_h = soup.find("h3", string="Frequency Summary")
    freqs = []
    if freq_h:
        tbl = freq_h.find_next("table")
        if tbl:
            for tr in tbl.find_all("tr")[1:]:  # skip header
                tds = tr.find_all("td")
                if len(tds) == 2:
                    lo = _clean(tds[0].get_text())
                    hi = _clean(tds[1].get_text())
                    if lo and hi:
                        freqs.append(f"{lo}-{hi}")
    frequency_bands = ",".join(freqs)

    def parse_date(s):
        if not s:
            return None
        try:
            return datetime.strptime(s, "%Y-%m-%d").date()
        except ValueError:
            return None

    return {
        "applicant": applicant,
        "applicant_address": applicant_address,
        "nature_of_service": kv.get("Nature of Service", ""),
        "status": kv.get("Status", ""),
        "last_action": kv.get("Last Action", ""),
        "date_filed": parse_date(kv.get("Date Filed", "")),
        "date_granted": parse_date(kv.get("Date Granted", "")),
        "last_action_date": parse_date(kv.get("Last Action Date", "")),
        "frequency_bands": frequency_bands,
        "description": description,
        "ibfs_url": url,
    }


def extract_filing_type(file_number):
    # SAT-LOA-YYYYMMDD-NNNNN → LOA
    parts = file_number.split("-")
    return parts[1] if len(parts) >= 2 else ""


def main():
    print("Loading FCC NGSO filings seed...")
    seed = load_seed()
    print(f"  {len(seed)} filings in seed")

    session = _session()
    rows = []
    now_utc = datetime.now(timezone.utc)

    for i, entry in enumerate(seed):
        file_number = entry["file_number"]
        print(f"  [{i+1}/{len(seed)}] {file_number}...")
        try:
            scraped = fetch_filing(session, file_number)
        except Exception as e:
            print(f"    WARN: fetch failed: {e}")
            continue

        op = entry.get("operator_family", "other")
        if op not in VALID_OPERATOR_FAMILIES:
            print(f"    WARN: unknown operator_family={op!r}, coercing to 'other'")
            op = "other"

        rows.append({
            "file_number": file_number,
            "applicant": scraped["applicant"],
            "operator_family": op,
            "system_name": entry.get("system_name", ""),
            "filing_type": extract_filing_type(file_number),
            "nature_of_service": scraped["nature_of_service"],
            "status": scraped["status"],
            "last_action": scraped["last_action"],
            "date_filed": scraped["date_filed"],
            "date_granted": scraped["date_granted"],
            "last_action_date": scraped["last_action_date"],
            "requested_satellites": entry.get("requested_satellites"),
            "orbital_shells_json": json.dumps(entry.get("orbital_shells", [])),
            "frequency_bands": scraped["frequency_bands"],
            "description": scraped["description"],
            "applicant_address": scraped["applicant_address"],
            "ibfs_url": scraped["ibfs_url"],
            "fetched_at_utc": now_utc,
        })

        if i < len(seed) - 1:
            time.sleep(REQUEST_SLEEP_SEC)

    df = pd.DataFrame(rows)
    df["date_filed"] = pd.to_datetime(df["date_filed"], errors="coerce")
    df["date_granted"] = pd.to_datetime(df["date_granted"], errors="coerce")
    df["last_action_date"] = pd.to_datetime(df["last_action_date"], errors="coerce")
    df["requested_satellites"] = pd.to_numeric(df["requested_satellites"], errors="coerce").astype("Int64")
    df = df.sort_values("date_filed", na_position="last").reset_index(drop=True)

    # Fail fast on empty rows (beyond what check_dataset does): every row must have a
    # non-empty applicant, nature_of_service, status, and date_filed.
    required_non_empty = ["applicant", "nature_of_service", "status"]
    for col in required_non_empty:
        bad = df[df[col].fillna("").str.strip() == ""]
        if len(bad):
            raise RuntimeError(
                f"Empty {col!r} in {len(bad)} row(s): {bad['file_number'].tolist()}"
            )
    if df["date_filed"].isna().any():
        bad = df[df["date_filed"].isna()]["file_number"].tolist()
        raise RuntimeError(f"Missing date_filed in rows: {bad}")

    # Shell-sum invariant: orbital_shells_json counts must equal requested_satellites
    for _, row in df.iterrows():
        if pd.isna(row["requested_satellites"]):
            continue
        shells = json.loads(row["orbital_shells_json"])
        shell_sum = sum(int(s.get("satellite_count", 0)) for s in shells)
        if shell_sum != int(row["requested_satellites"]):
            raise RuntimeError(
                f"Shell sum mismatch in {row['file_number']}: "
                f"shells sum to {shell_sum} but requested_satellites={row['requested_satellites']}"
            )

    n_total = len(df)
    n_granted = int(df["status"].eq("Action Complete").sum())
    total_requested = int(df["requested_satellites"].dropna().sum())
    family_counts = df["operator_family"].value_counts().to_dict()

    print(f"  {n_total} filings parsed, {n_granted} granted, {total_requested:,} total satellites requested")

    with Pipeline(
        repo=HF_REPO,
        pretty_name="FCC NGSO Satellite Filings",
        description=DESCRIPTION,
        tags=["space", "fcc", "ibfs", "ngso", "satellite-filings", "regulation",
              "spectrum", "starlink", "kuiper", "oneweb", "open-data", "tabular-data",
              "parquet", "governance"],
        source_url="https://fcc.report/IBFS/",
        task_categories=["tabular-classification"],
        update_schedule="Weekly on Monday at 10:00 UTC via GitHub Actions",
        collection_url="https://huggingface.co/collections/juliensimon/orbital-mechanics-datasets-69c24caca4ab3934c9856994",
        banner={
            "url": "https://images-assets.nasa.gov/image/iss071e439624/iss071e439624~medium.jpg",
            "alt": "Orbital sunrise illuminating Earth's atmosphere, seen from the ISS",
            "credit": "NASA",
        },
        related_datasets=[
            "juliensimon/starlink-fleet-data",
            "juliensimon/kuiper-fleet-data",
            "juliensimon/oneweb-fleet-data",
            "juliensimon/ast-spacemobile-fleet-data",
            "juliensimon/blue-origin-launches",
            "juliensimon/spacex-launches",
            "juliensimon/ula-launches",
            "juliensimon/constellation-census",
        ],
    ) as p:
        top_families = ", ".join(f"{fam}: {n}" for fam, n in sorted(family_counts.items(), key=lambda x: -x[1]))
        quick_stats = f"""\
- **{n_total}** NGSO constellation filings tracked
- **{total_requested:,}** total satellites requested across all filings
- **{n_granted}** filings with Grant of Authority (Action Complete)
- Operator families: {top_families}
- Source: FCC IBFS via [fcc.report](https://fcc.report/IBFS/) (third-party mirror, not affiliated with the FCC)"""

        usage = """\
```python
from datasets import load_dataset
import json

ds = load_dataset("juliensimon/fcc-ngso-filings", split="train").to_pandas()

# Requested satellites per operator family
print(ds.groupby("operator_family")["requested_satellites"].sum().sort_values(ascending=False))

# Gap between requested and flying — pair with kuiper-fleet-data / starlink-fleet-data
kuiper = ds[ds["operator_family"] == "amazon"].iloc[0]
print(f"Kuiper requested {kuiper['requested_satellites']} sats across {len(json.loads(kuiper['orbital_shells_json']))} shells")

# Filings timeline
print(ds[["file_number", "applicant", "date_filed", "date_granted", "status"]].sort_values("date_filed"))
```"""

        p.publish(
            df,
            filename="fcc_ngso_filings.parquet",
            min_rows=1,
            expected_columns=["file_number", "applicant", "operator_family", "status"],
            critical_columns=["file_number", "applicant"],
            column_descriptions=COLUMN_DESCRIPTIONS,
            quick_stats=quick_stats,
            usage=usage,
            commit_message=(
                f"Update FCC NGSO filings: {n_total} filings "
                f"({total_requested:,} satellites requested, {n_granted} granted)"
            ),
        )
    print("Done.")


if __name__ == "__main__":
    main()
