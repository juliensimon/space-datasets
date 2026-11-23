"""The two SIMBAD pipelines fetch through the shared retry helper.

Context: Update Quasars and Update Black Holes failed six weekly runs in a row
because the CDS host timed out and each script's private 3-attempt loop gave
up after about a minute and a half. Both now call ``simbad_query`` (retry
helper plus CDS-to-CfA mirror fallback, tested in test_simbad_fallback.py).
These tests replace ``simbad_query`` and the Hugging Face Pipeline with
stand-ins: they pin the ADQL that is sent and that the response is parsed into
the published DataFrame. Nothing here touches the network.

Run:
    python3 scripts/tests/test_simbad_scripts.py
"""

import importlib.util
import sys
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parents[2]
SCRIPTS = REPO / "scripts"
sys.path.insert(0, str(SCRIPTS))

QUASARS_CSV = "name,ra,dec,object_type\n3C 273,187.27,2.05,QSO\nMrk 421,166.11,38.21,BLL\n"
BLACK_HOLES_CSV = (
    "name,ra,dec,object_type,spectral_type\n"
    "Cyg X-1,299.59,35.2,BH,O9.7Iab\nGRS 1915+105,288.8,10.95,BH?,\n"
)


class _Resp:
    def __init__(self, text):
        self.text = text


class _FakePipeline:
    """Stand-in for hf_dataset_utils.Pipeline: records what is published."""

    published = None

    def __init__(self, **kwargs):
        self.kwargs = kwargs

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def clean(self, df, **kwargs):
        return df

    def publish(self, df, **kwargs):
        type(self).published = df


def _load(filename):
    spec = importlib.util.spec_from_file_location(
        filename.removesuffix(".py").replace("-", "_"), SCRIPTS / filename
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run(filename, csv, category_column):
    module = _load(filename)
    _FakePipeline.published = None
    with (
        mock.patch.object(module, "Pipeline", _FakePipeline),
        mock.patch.object(module, "simbad_query",
                          return_value=_Resp(csv)) as query,
    ):
        module.main()

    query.assert_called_once_with(module.ADQL)

    df = _FakePipeline.published
    assert df is not None, "publish() was never reached"
    assert len(df) == 2, df
    assert {"name", "ra_deg", "dec_deg", "object_type", category_column} <= set(
        df.columns
    ), list(df.columns)
    assert df[category_column].notna().all(), df
    return module, df


def test_update_quasars_builds_dataframe_via_simbad_query():
    _, df = _run("update-quasars.py", QUASARS_CSV, "agn_category")
    assert set(df["agn_category"]) == {"Quasar", "BL Lac Object"}, df
    print("PASS: update-quasars fetches via simbad_query and builds the table")


def test_update_black_holes_builds_dataframe_via_simbad_query():
    _, df = _run("update-black-holes.py", BLACK_HOLES_CSV, "bh_category")
    assert set(df["bh_category"]) == {
        "Confirmed Black Hole", "Black Hole Candidate"
    }, df
    print("PASS: update-black-holes fetches via simbad_query and builds the table")


if __name__ == "__main__":
    test_update_quasars_builds_dataframe_via_simbad_query()
    test_update_black_holes_builds_dataframe_via_simbad_query()
    print("\nAll tests passed.")
