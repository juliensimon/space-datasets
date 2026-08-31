#!/usr/bin/env python3
"""Regression test for fetch_with_retry, the shared HTTP retry helper.

Context: between 2026-08-28 and 08-31, celestrak.org black-holed TCP
connections from GitHub runners for 6+ minutes at a time. Five daily pipelines
failed because each carried its own retry loop with a budget far shorter than
the outage (update-conjunctions.py gave up after ~7s). The fix was one shared
helper with a budget that outlasts a real outage.

A long budget is only safe if the helper is picky about *what* it retries: on
the old bare-`except Exception` loops a 404 was retried like a timeout, so
widening the ladder would turn a dead URL into a silent 12-minute hang. These
tests pin both halves of that bargain -- the ladder is walked for transient
failures, and skipped entirely for a status that will never recover -- so a
future budget change can't quietly reintroduce the hang.

Run:
    python3 scripts/tests/test_http_retry.py
"""

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts"))

import requests

from hf_dataset_utils import http


class _Resp:
    """Minimal stand-in for requests.Response."""

    def __init__(self, status=200, text="payload"):
        self.status_code = status
        self.text = text

    @property
    def ok(self):
        return self.status_code < 400

    def raise_for_status(self):
        if not self.ok:
            raise requests.HTTPError(f"{self.status_code} Error", response=self)


def _patch(script):
    """Script requests.get with a sequence; capture sleeps and passed kwargs.

    Sleeps are captured rather than performed -- the real ladder is 7.5 minutes.
    """
    calls = {"sleeps": [], "kwargs": []}
    seq = list(script)

    def fake_get(url, **kwargs):
        calls["kwargs"].append(kwargs)
        item = seq.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    http.requests.get = fake_get
    http.time.sleep = lambda s: calls["sleeps"].append(s)
    return calls


def _timeout():
    return requests.exceptions.ConnectTimeout("connect timed out")


def test_transient_failures_are_ridden_out():
    """The Aug 31 failure mode: connect timeouts, then the source comes back."""
    calls = _patch([_timeout(), _timeout(), _Resp(200)])

    resp = http.fetch_with_retry("https://celestrak.org/pub/satcat.csv")

    assert resp.text == "payload", resp.text
    # Default ladder, in order -- pins the budget, not just "it retried".
    assert calls["sleeps"] == [30, 60], calls["sleeps"]
    print("PASS: connection timeouts retried on the 30s/60s ladder, then succeed")


def test_budget_is_finite_and_original_error_surfaces():
    """A permanently unreachable host must fail loudly, not hang forever."""
    calls = _patch([_timeout(), _timeout(), _timeout()])

    try:
        http.fetch_with_retry("https://celestrak.org/pub/satcat.csv", waits=(1, 2))
    except requests.exceptions.ConnectTimeout:
        pass
    else:
        raise AssertionError("exhausted budget should re-raise the connect timeout")

    assert calls["sleeps"] == [1, 2], calls["sleeps"]
    print("PASS: budget is finite and the underlying ConnectTimeout propagates")


def test_dead_url_is_not_retried():
    """The guard that makes a 12-minute budget safe: 404 costs zero waiting."""
    calls = _patch([_Resp(404)])

    try:
        http.fetch_with_retry("https://celestrak.org/pub/typo.csv")
    except requests.HTTPError:
        pass
    else:
        raise AssertionError("a 404 must raise, not be retried into a timeout")

    assert calls["sleeps"] == [], f"404 burned the retry budget: {calls['sleeps']}"
    assert len(calls["kwargs"]) == 1, calls["kwargs"]
    print("PASS: 404 raises immediately without spending the retry budget")


def test_transient_status_still_retried():
    """CelesTrak's documented 5xx flakiness must stay inside the ladder."""
    calls = _patch([_Resp(503), _Resp(200)])

    resp = http.fetch_with_retry("https://celestrak.org/pub/satcat.csv")

    assert resp.status_code == 200
    assert calls["sleeps"] == [30], calls["sleeps"]
    print("PASS: 503 is retried (CelesTrak 5xx behaviour preserved)")


def test_request_kwargs_reach_requests_get():
    """update-conjunctions.py only works with its Mozilla User-Agent header."""
    calls = _patch([_Resp(200)])
    headers = {"User-Agent": "Mozilla/5.0"}

    http.fetch_with_retry("https://celestrak.org/SOCRATES/sort-minRange.csv",
                          timeout=90, headers=headers)

    assert calls["kwargs"][0]["headers"] == headers, calls["kwargs"]
    assert calls["kwargs"][0]["timeout"] == 90, calls["kwargs"]
    print("PASS: headers and timeout are forwarded to requests.get")


if __name__ == "__main__":
    test_transient_failures_are_ridden_out()
    test_budget_is_finite_and_original_error_surfaces()
    test_dead_url_is_not_retried()
    test_transient_status_still_retried()
    test_request_kwargs_reach_requests_get()
    print("\nAll tests passed.")
