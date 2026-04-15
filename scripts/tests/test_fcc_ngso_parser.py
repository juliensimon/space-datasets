#!/usr/bin/env python3
"""Parser fixture test for update-fcc-ngso-filings.

Runs parse_filing_html against a saved fcc.report HTML snapshot so that any
upstream HTML drift is caught locally *before* the weekly cron ships broken
data. Pure unit test — no network, no HF upload.

Run:
    python3 scripts/tests/test_fcc_ngso_parser.py

Update fixture if fcc.report layout intentionally changes:
    curl -s -A "space-datasets/fcc-ngso-filings" \
        https://fcc.report/IBFS/SAT-LOA-20190704-00057 \
        | python3 -c "import sys,re; \
sys.stdout.write(re.sub(r'src=\"https://www\\.google\\.com/maps/embed[^\"]*\"', \
'src=\"REDACTED-GOOGLE-MAPS-EMBED-URL\"', sys.stdin.read()))" \
        > scripts/data/fixtures/kuiper.html

The inline scrub removes fcc.report's public Google Maps Embed API key
from the saved HTML — GitHub secret scanning will flag it as a Google API
key pattern even though the key is already publicly exposed on fcc.report
and referrer-restricted at Google's end. The parser never touches the
iframe block so stripping it does not affect test coverage.
"""

import importlib.util
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "scripts" / "update-fcc-ngso-filings.py"
FIXTURE = REPO / "scripts" / "data" / "fixtures" / "kuiper.html"
SEED = REPO / "scripts" / "data" / "fcc_ngso_seed.json"


def _load_module():
    sys.path.insert(0, str(REPO / "scripts"))
    spec = importlib.util.spec_from_file_location("fcc_filings", SCRIPT)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def test_parse_kuiper_fixture():
    m = _load_module()
    html = FIXTURE.read_text()
    file_number = "SAT-LOA-20190704-00057"
    result = m.parse_filing_html(html, file_number)

    expectations = {
        "applicant": "Kuiper Systems LLC",
        "nature_of_service": "Fixed Satellite Service",
        "status": "Action Complete",
        "last_action": "Grant of Authority",
    }
    for k, expected in expectations.items():
        assert result[k] == expected, f"{k}: expected {expected!r}, got {result[k]!r}"

    assert str(result["date_filed"]) == "2019-07-04", f"date_filed: {result['date_filed']}"
    assert str(result["date_granted"]) == "2020-07-30", f"date_granted: {result['date_granted']}"

    # Kuiper address and IBFS URL
    assert "1776 K Street" in result["applicant_address"], f"address: {result['applicant_address']!r}"
    assert result["ibfs_url"].endswith(file_number)

    # Ka-band frequency pairs must be present (17700-18200 is the core Kuiper band)
    assert "17700-18200" in result["frequency_bands"], f"frequency_bands: {result['frequency_bands']!r}"

    # Description should mention Kuiper and NGSO
    desc = result["description"].lower()
    assert "kuiper" in desc and ("non-geostationary" in desc or "ngso" in desc), \
        f"description missing expected keywords: {result['description'][:200]!r}"

    print("PASS: parse_filing_html(kuiper.html) extracted all expected fields")


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
    test_parse_empty_html_fails_fast()
    test_load_seed_validates()
    print("\nAll tests passed.")
