"""Retrying HTTP GET for the flaky public sources these pipelines depend on.

Every dataset script carried its own copy of the same retry loop with a
different budget -- ~7s in update-conjunctions.py, ~210s in update-kuiper.py,
none at all in update-fragmentation-events.py. That made the one number worth
tuning (how long to wait out an upstream outage) a 14-file edit. It lives here
now.

Budget rationale: between 2026-08-28 and 08-31, celestrak.org black-holed TCP
connections from GitHub runners for stretches of 6+ minutes at a time. Every
pipeline whose retries gave up sooner failed; run 33388408533 retried from
11:44 to 11:51 and never completed a handshake. RETRY_WAITS rides out ~12 min
worst case (450s of backoff plus five connect timeouts). Widen it here, not in
the callers.
"""

import time

import requests

# Waits between attempts; total attempts is len(RETRY_WAITS) + 1.
RETRY_WAITS = (30, 60, 120, 240)

# Transient server-side conditions worth waiting out. Everything else (404,
# 401, 400) is a real breakage -- retrying it burns the whole budget and buries
# the cause under a timeout. 403 is included because CelesTrak transiently
# blocks GitHub runner IPs with 403 before allowing access again.
RETRY_STATUS = frozenset({403, 408, 425, 429, 500, 502, 503, 504})


def fetch_with_retry(url, *, timeout=60, waits=RETRY_WAITS, label=None, **kwargs):
    """GET ``url`` with backoff, returning the successful ``requests.Response``.

    Retries connection errors, timeouts, and ``RETRY_STATUS`` responses. Raises
    the underlying exception (or ``HTTPError``) once ``waits`` is exhausted, and
    raises immediately on a non-retryable status. ``kwargs`` pass through to
    ``requests.get`` (e.g. ``headers=``).
    """
    tag = label or url
    attempts = len(waits) + 1
    for i in range(attempts):
        last = i == attempts - 1
        try:
            resp = requests.get(url, timeout=timeout, **kwargs)
        except requests.RequestException as exc:
            if last:
                raise
            reason = exc
        else:
            if resp.ok:
                return resp
            if last or resp.status_code not in RETRY_STATUS:
                resp.raise_for_status()
            reason = f"HTTP {resp.status_code}"
        print(
            f"  {tag}: attempt {i + 1}/{attempts} failed ({reason}); "
            f"retrying in {waits[i]}s...",
            flush=True,
        )
        time.sleep(waits[i])
