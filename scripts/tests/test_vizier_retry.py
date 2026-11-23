"""Regression test for the VizieR TAP client's retry behaviour.

Context: the weekly Update WDS pipeline failed six runs in a row because
tapvizier.cds.unistra.fr timed out and ``_fetch_page`` gave up after a ~30s
private retry loop. The client now goes through ``fetch_with_retry`` (the
shared ~71 min budget). The HTTP layer is mocked; nothing here touches the
network.

Run:
    python3 scripts/tests/test_vizier_retry.py
"""

import sys
from contextlib import contextmanager
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts"))

import requests
from hf_dataset_utils import http
from hf_dataset_utils.tap import vizier

CSV = "recno,name\n1,a\n2,b\n"
VOTABLE_ERROR = '<?xml version="1.0"?><VOTABLE><INFO name="QUERY_STATUS" value="ERROR"/></VOTABLE>'


class _Resp:
    def __init__(self, status=200, text=CSV):
        self.status_code = status
        self.text = text

    @property
    def ok(self):
        return self.status_code < 400

    def raise_for_status(self):
        if not self.ok:
            raise requests.HTTPError(f"{self.status_code} Error", response=self)


@contextmanager
def _patch_post(script):
    """Script requests.post with a sequence; capture sleeps and calls."""
    calls = {"sleeps": [], "posts": []}
    seq = list(script)

    def fake_post(url, **kwargs):
        calls["posts"].append((url, kwargs))
        item = seq.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    with (
        mock.patch.object(http.requests, "post", fake_post),
        mock.patch.object(http.time, "sleep", lambda s: calls["sleeps"].append(s)),
    ):
        yield calls


def test_connect_timeout_is_retried_on_shared_ladder():
    """The WDS failure mode: CDS times out, then answers."""
    exc = requests.exceptions.ConnectTimeout("connect timed out")
    with _patch_post([exc, exc, _Resp(200)]) as calls:
        df = vizier.vizier_query("SELECT * FROM \"B/wds/wds\"")

    assert list(df["name"]) == ["a", "b"], df
    assert calls["sleeps"] == [30, 60], calls["sleeps"]
    url, kwargs = calls["posts"][0]
    assert url == vizier.TAP_URL, url
    assert kwargs["timeout"] == 300, kwargs
    assert kwargs["data"]["QUERY"] == "SELECT * FROM \"B/wds/wds\"", kwargs
    assert kwargs["data"]["FORMAT"] == "csv", kwargs
    print("PASS: VizieR ConnectTimeout retried on the 30s/60s ladder, then succeeds")


def test_server_error_status_is_retried():
    with _patch_post([_Resp(503), _Resp(200)]) as calls:
        df = vizier.vizier_query("SELECT * FROM t")

    assert len(df) == 2
    assert calls["sleeps"] == [30], calls["sleeps"]
    print("PASS: VizieR 503 is retried")


def test_votable_error_body_still_exits():
    """A 200 whose body is a VOTable error is a bad query: stop, do not retry."""
    with _patch_post([_Resp(200, VOTABLE_ERROR)]) as calls:
        try:
            vizier.vizier_query("SELECT * FROM nope")
        except SystemExit as exc:
            assert exc.code == 1, exc.code
        else:
            raise AssertionError("VOTable error body must exit")

    assert calls["sleeps"] == [], calls["sleeps"]
    assert len(calls["posts"]) == 1, calls["posts"]
    print("PASS: VOTable error body exits 1 without retrying")


if __name__ == "__main__":
    test_connect_timeout_is_retried_on_shared_ladder()
    test_server_error_status_is_retried()
    test_votable_error_body_still_exits()
    print("\nAll tests passed.")
