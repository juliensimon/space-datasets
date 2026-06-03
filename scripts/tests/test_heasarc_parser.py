#!/usr/bin/env python3
"""Regression test for the HEASARC TAP text parser.

HEASARC reports query failures as a plain-text "---- Messages ----" block
returned with HTTP 200 (not an error status, not XML for FORMAT=text). Before
the guard added in heasarc.py, `_parse_text` turned that block into a bogus
one-column DataFrame which passed the non-empty check, so `heasarc_query`
returned it as if it were data. Downstream that surfaced as a cryptic
`KeyError` on a missing column (e.g. update-pulsars.py's `df["period"]`),
masking the real cause: the query never executed.

This test pins that an error block is recognised and rejected, while a normal
pipe-delimited table still parses — so any regression is caught locally,
without a network round-trip, before the weekly cron ships broken data.

Run:
    python3 scripts/tests/test_heasarc_parser.py
"""

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts"))

from hf_dataset_utils.tap.heasarc import _heasarc_failure, _parse_text  # noqa: E402

# Verbatim FORMAT=text body HEASARC returns when a query fails to execute
# (captured from `SELECT name, age FROM atnfpulsar`, where `age` is a broken
# server-side column).
ERROR_BLOCK = "\n---- Messages ----\n----\nFailure: Query Error\nUnable to execute query.\n----\n"

# A normal pipe-delimited result, including the leading/trailing pipes and the
# dashed separator row HEASARC emits.
VALID_TABLE = (
    "name|period|dm\n"
    "----|------|----\n"
    "PSR J0002+6216|0.115364|218.6\n"
    "PSR J0006+1834|0.693748|11.4\n"
)


def test_failure_block_detected():
    msg = _heasarc_failure(ERROR_BLOCK)
    assert msg is not None, "error block must be recognised as a failure"
    assert "Failure: Query Error" in msg, f"message should surface HEASARC's text, got {msg!r}"
    assert "Unable to execute query." in msg, f"message should include the detail line, got {msg!r}"
    print(f"PASS: _heasarc_failure detected error block -> {msg!r}")


def test_error_block_not_parsed_as_data():
    # The core bug: an error block must NOT become a DataFrame.
    assert _parse_text(ERROR_BLOCK) is None, \
        "error block must not be parsed as a (bogus one-column) DataFrame"
    print("PASS: _parse_text rejects the HEASARC error block")


def test_valid_table_still_parses():
    df = _parse_text(VALID_TABLE)
    assert df is not None, "valid pipe table must still parse"
    assert list(df.columns) == ["name", "period", "dm"], f"columns: {list(df.columns)}"
    assert len(df) == 2, f"expected 2 data rows (separator skipped), got {len(df)}"
    # Numeric auto-detection must keep `period` usable for arithmetic downstream.
    assert df["period"].dtype.kind == "f", f"period should be float, got {df['period'].dtype}"
    assert _heasarc_failure(VALID_TABLE) is None, "valid data must not be flagged as a failure"
    print("PASS: _parse_text still parses a normal pipe table (period is numeric)")


if __name__ == "__main__":
    test_failure_block_detected()
    test_error_block_not_parsed_as_data()
    test_valid_table_still_parses()
    print("\nAll tests passed.")
