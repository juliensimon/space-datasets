"""SIMBAD TAP queries with a mirror fallback.

On 2026-11-23 every /simbad/ path at CDS returned 404. The CfA mirror answers
the same GET query with the same CSV columns, so ``simbad_query`` tries CDS
first and falls through to CfA. A dead primary gets a short retry budget so the
mirror is reached within minutes; the last host keeps the full ``RETRY_WAITS``
budget.
"""

import requests

from hf_dataset_utils.http import RETRY_WAITS, fetch_with_retry

# Tried in order: CDS (primary), then the CfA mirror.
SIMBAD_TAP_HOSTS = (
    "https://simbad.u-strasbg.fr/simbad/sim-tap/sync",
    "https://simbad.cfa.harvard.edu/simbad/sim-tap/sync",
)

# Retry budget for every host except the last (3 attempts, 30s + 60s of waiting).
PRIMARY_WAITS = (30, 60)


def simbad_query(adql: str, *, timeout: int = 300) -> requests.Response:
    """Run ``adql`` against SIMBAD TAP and return the CSV ``Response``.

    Raises the last host's exception unchanged if every host fails.
    """
    params = {
        "REQUEST": "doQuery",
        "LANG": "ADQL",
        "FORMAT": "csv",
        "QUERY": adql,
    }
    last_index = len(SIMBAD_TAP_HOSTS) - 1
    for i, host in enumerate(SIMBAD_TAP_HOSTS):
        is_last = i == last_index
        try:
            resp = fetch_with_retry(
                host,
                params=params,
                timeout=timeout,
                waits=RETRY_WAITS if is_last else PRIMARY_WAITS,
                label="SIMBAD",
            )
        except requests.RequestException as exc:
            if is_last:
                raise
            print(f"  SIMBAD host {host} failed ({exc}); trying next host", flush=True)
            continue
        print(f"  SIMBAD answered from {host}", flush=True)
        return resp
    raise RuntimeError("SIMBAD_TAP_HOSTS is empty")  # pragma: no cover
