#!/usr/bin/env python3
"""Parser fixture test for update-fcc-ngso-filings.

Runs parse_filing_html against saved fcc.report HTML snapshots so that any
upstream HTML drift is caught locally *before* the weekly cron ships broken
data. Pure unit test — no network, no HF upload.

fcc.report serves two layouts and both are covered here, because they exercise
different code paths: kuiper.html carries transcribed FCC Form 312 sections
(applicant address, nature of service), while starlink-gen1.html is an older
record with the "Filing overview" table only, where those fields must fall
back instead of raising.

Run:
    python3 scripts/tests/test_fcc_ngso_parser.py

Update fixtures if fcc.report layout intentionally changes:
    curl -s -A "space-datasets/fcc-ngso-filings" \
        https://fcc.report/IBFS/SAT-LOA-20190704-00057 > scripts/data/fixtures/kuiper.html
    curl -s -A "space-datasets/fcc-ngso-filings" \
        https://fcc.report/IBFS/SAT-LOA-20161115-00118 > scripts/data/fixtures/starlink-gen1.html
"""

import importlib.util
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "scripts" / "update-fcc-ngso-filings.py"
FIXTURES = REPO / "scripts" / "data" / "fixtures"
SEED = REPO / "scripts" / "data" / "fcc_ngso_seed.json"


def _load_module():
    sys.path.insert(0, str(REPO / "scripts"))
    spec = importlib.util.spec_from_file_location("fcc_filings", SCRIPT)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def _check(result, expectations):
    for k, expected in expectations.items():
        assert result[k] == expected, f"{k}: expected {expected!r}, got {result[k]!r}"


def test_parse_kuiper_fixture():
    """Form-312 layout: applicant details come from the transcribed form."""
    m = _load_module()
    file_number = "SAT-LOA-20190704-00057"
    result = m.parse_filing_html((FIXTURES / "kuiper.html").read_text(), file_number)

    _check(result, {
        "applicant": "Kuiper Systems LLC",
        "nature_of_service": "Fixed-Satellite Service",
        "status": "Closed",
        "last_action": "Grant of Authority",
    })
    assert str(result["date_filed"]) == "2019-07-04", f"date_filed: {result['date_filed']}"
    assert str(result["date_granted"]) == "2020-07-30", f"date_granted: {result['date_granted']}"

    # Applicant address must be Amazon's HQ, not the outside counsel address
    # that fcc.report lists one section earlier under "Application details".
    addr = result["applicant_address"]
    assert "410 Terry Avenue North" in addr and "Seattle" in addr, f"address: {addr!r}"
    assert result["ibfs_url"].endswith(file_number)

    # Ka-band frequency pairs, stripped of the fixed-point zero padding
    assert "17700-18200" in result["frequency_bands"], f"frequency_bands: {result['frequency_bands']!r}"

    assert "kuiper" in result["description"].lower(), f"description: {result['description'][:200]!r}"
    print("PASS: parse_filing_html(kuiper.html) extracted all expected fields")


def test_parse_legacy_layout_fixture():
    """Overview-only layout: no form sections, so the fallbacks must carry it."""
    m = _load_module()
    file_number = "SAT-LOA-20161115-00118"
    result = m.parse_filing_html((FIXTURES / "starlink-gen1.html").read_text(), file_number)

    _check(result, {
        "applicant": "Space Exploration Holdings, LLC",
        # No Form 312 section here — this falls back to the overview "Service" cell.
        "nature_of_service": "Fixed Satellite Service",
        "status": "Action Complete",
        "last_action": "Grant of Authority",
        # fcc.report transcribes no applicant form fields for this vintage.
        "applicant_address": "",
    })
    assert str(result["date_filed"]) == "2016-11-15", f"date_filed: {result['date_filed']}"
    assert str(result["date_granted"]) == "2018-03-29", f"date_granted: {result['date_granted']}"
    assert "10700-10950" in result["frequency_bands"], f"frequency_bands: {result['frequency_bands']!r}"

    desc = result["description"].lower()
    assert "non-geostationary" in desc, f"description: {result['description'][:200]!r}"
    print("PASS: parse_filing_html(starlink-gen1.html) handled the overview-only layout")


def test_parse_empty_html_fails_fast():
    m = _load_module()
    try:
        m.parse_filing_html("<html></html>", "SAT-LOA-19990101-00001")
    except RuntimeError as e:
        assert "No applicant found" in str(e), f"wrong error: {e}"
        print("PASS: parse_filing_html raises RuntimeError on empty page")
        return
    raise AssertionError("Expected RuntimeError on empty HTML, got none")


def test_load_seed_validates():
    m = _load_module()
    filings = m.load_seed(SEED)
    assert len(filings) >= 1
    # Shell-sum invariant must hold across all seed entries (load_seed enforces this)
    for f in filings:
        shell_sum = sum(s["satellite_count"] for s in f["orbital_shells"])
        assert shell_sum == f["requested_satellites"], \
            f"{f['file_number']}: shells sum to {shell_sum}, req={f['requested_satellites']}"
    print(f"PASS: load_seed() validated {len(filings)} entries")


if __name__ == "__main__":
    test_parse_kuiper_fixture()
    test_parse_legacy_layout_fixture()
    test_parse_empty_html_fails_fast()
    test_load_seed_validates()
    print("\nAll tests passed.")
