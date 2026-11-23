"""simbad_query falls back from the CDS host to the CfA mirror.

Context: on 2026-11-23 every /simbad/ path at CDS (simbad.u-strasbg.fr)
returned 404. The CfA mirror answers the same TAP GET query. These tests pin
the fallback: only ``requests.get`` and ``time.sleep`` are replaced, so the real
``fetch_with_retry`` ladder runs. Nothing here touches the network.

Run:
    python3 -m pytest scripts/tests/test_simbad_fallback.py
"""

import sys
from pathlib import Path
from unittest import mock

import pytest
import requests

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts"))

from hf_dataset_utils import http, simbad

CDS = "https://simbad.u-strasbg.fr/simbad/sim-tap/sync"
CFA = "https://simbad.cfa.harvard.edu/simbad/sim-tap/sync"
ADQL = "SELECT TOP 3 main_id FROM basic"


class _Resp:
    def __init__(self, status=200, text="main_id\nA\n"):
        self.status_code = status
        self.text = text

    @property
    def ok(self):
        return self.status_code < 400

    def raise_for_status(self):
        if not self.ok:
            raise requests.HTTPError(f"{self.status_code} Error", response=self)


class _Net:
    """Scripted ``requests.get``: one list of outcomes per host."""

    def __init__(self, script):
        self.script = {url: list(items) for url, items in script.items()}
        self.urls = []
        self.kwargs = []
        self.sleeps = []

    def get(self, url, **kwargs):
        self.urls.append(url)
        self.kwargs.append(kwargs)
        item = self.script[url].pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    def sleep(self, seconds):
        self.sleeps.append(seconds)


@pytest.fixture
def net(request):
    holder = {}

    def install(script):
        holder["net"] = _Net(script)
        return holder["net"]

    with (
        mock.patch.object(requests, "get", lambda *a, **k: holder["net"].get(*a, **k)),
        mock.patch.object(http.time, "sleep", lambda s: holder["net"].sleep(s)),
    ):
        yield install


def test_hosts_are_cds_then_cfa():
    assert simbad.SIMBAD_TAP_HOSTS == (CDS, CFA)


def test_primary_success_never_calls_mirror(net):
    n = net({CDS: [_Resp()], CFA: []})
    resp = simbad.simbad_query(ADQL)
    assert resp.text == "main_id\nA\n"
    assert n.urls == [CDS]
    assert n.sleeps == []


def test_query_params_and_timeout_are_sent(net):
    n = net({CDS: [_Resp()], CFA: []})
    simbad.simbad_query(ADQL, timeout=123)
    assert n.kwargs[0]["params"] == {
        "REQUEST": "doQuery", "LANG": "ADQL", "FORMAT": "csv", "QUERY": ADQL,
    }
    assert n.kwargs[0]["timeout"] == 123


def test_primary_404_falls_through_without_waiting(net, capsys):
    n = net({CDS: [_Resp(404)], CFA: [_Resp(text="mirror")]})
    resp = simbad.simbad_query(ADQL)
    assert resp.text == "mirror"
    assert n.urls == [CDS, CFA]
    assert n.sleeps == []
    out = capsys.readouterr().out
    assert "simbad.u-strasbg.fr" in out and "404" in out


def test_primary_timeouts_use_short_budget_then_mirror(net):
    n = net({
        CDS: [requests.ConnectTimeout("t")] * 3,
        CFA: [_Resp(text="mirror")],
    })
    resp = simbad.simbad_query(ADQL)
    assert resp.text == "mirror"
    assert n.urls == [CDS, CDS, CDS, CFA]
    assert n.sleeps == [30, 60]


def test_mirror_uses_full_default_budget(net):
    n = net({
        CDS: [_Resp(404)],
        CFA: [requests.ConnectTimeout("t")] * (len(http.RETRY_WAITS) + 1),
    })
    with pytest.raises(requests.ConnectTimeout):
        simbad.simbad_query(ADQL)
    assert n.sleeps == list(http.RETRY_WAITS)


def test_both_fail_raises_mirror_exception(net):
    n = net({CDS: [_Resp(404)], CFA: [_Resp(404)]})
    with pytest.raises(requests.HTTPError) as err:
        simbad.simbad_query(ADQL)
    assert "404" in str(err.value)
    assert n.urls == [CDS, CFA]


def test_success_line_names_answering_host(net, capsys):
    net({CDS: [_Resp(404)], CFA: [_Resp()]})
    simbad.simbad_query(ADQL)
    out = capsys.readouterr().out
    assert "SIMBAD answered from https://simbad.cfa.harvard.edu" in out


def test_success_line_names_primary_when_it_answers(net, capsys):
    net({CDS: [_Resp()], CFA: []})
    simbad.simbad_query(ADQL)
    assert "SIMBAD answered from https://simbad.u-strasbg.fr" in capsys.readouterr().out


def test_waits_kwargs_per_host():
    seen = []

    def fake_fetch(url, **kwargs):
        seen.append((url, kwargs))
        if url == CDS:
            raise requests.ConnectTimeout("t")
        return _Resp()

    with mock.patch.object(simbad, "fetch_with_retry", fake_fetch):
        simbad.simbad_query(ADQL)
    assert seen[0][0] == CDS and seen[0][1]["waits"] == (30, 60)
    assert seen[1][0] == CFA and seen[1][1]["waits"] == http.RETRY_WAITS
    assert all(kw["label"] == "SIMBAD" for _, kw in seen)
