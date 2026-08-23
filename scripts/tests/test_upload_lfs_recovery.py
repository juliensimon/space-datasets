#!/usr/bin/env python3
"""Regression test for the broken-LFS-pointer recovery in upload_to_hf.

HF rejects a commit with HTTP 400 when a file already in the repo carries an
LFS pointer to a blob that does not exist; the push can never succeed on retry,
so `_hf_call_with_retry` (429/5xx only) correctly re-raises it straight away.
`upload_to_hf` then catches that escape, deletes the offending remote file and
uploads once more. Added in bc4c6a49 after oneweb-fleet-data
(data/daily_snapshots.parquet) hit it on 2026-08-10.

That recovery branch DELETES A REMOTE FILE, so the risk is not "recovery fails"
— it is "recovery fires when it shouldn't, or deletes the wrong path". These
tests pin the trigger narrow and the parsed path exact: every case that is not
a well-formed LFS-pointer rejection must propagate untouched, having deleted
nothing. Pure unit test — no network, no HF account.

Run:
    python3 scripts/tests/test_upload_lfs_recovery.py
"""

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts"))

from huggingface_hub.errors import HfHubHTTPError  # noqa: E402

from hf_dataset_utils import upload as upload_mod  # noqa: E402

REPO_ID = "juliensimon/oneweb-fleet-data"
OFFENDING = "data/daily_snapshots.parquet"

# Verbatim shape of HF's rejection, reconstructed from bc4c6a49's commit message
# and the strings upload.py matches on. The trailing blanks are deliberate: the
# regex uses a greedy `.+`, so without the .strip() in upload.py delete_file
# would be handed a padded path that matches no file on the remote.
LFS_BODY = (
    f"400 Client Error: Bad Request for url: "
    f"https://huggingface.co/api/datasets/{REPO_ID}/commit/main\n"
    "Invalid request: your push was rejected because it contains an LFS pointer "
    f"pointed to a file that does not exist. Offending file: - {OFFENDING}  \n"
)


class _HfError(HfHubHTTPError):
    """HfHubHTTPError that needs no live Response object.

    huggingface_hub 1.x requires `response: httpx.Response` and dereferences it
    in __init__; 0.x took an optional requests.Response. requirements.txt pins
    only >=0.28, so building a real one would tie this test to a major version.
    upload_to_hf only ever calls str(e) and matches the class, so bypassing
    __init__ is faithful to everything the code under test actually touches.
    """

    def __init__(self, message):
        Exception.__init__(self, message)


class _FakeApi:
    """Stands in for HfApi, recording what upload_to_hf asks it to do."""

    def __init__(self, upload_errors=(), delete_error=None):
        # One entry per upload_folder call; None means that call succeeds.
        self._upload_errors = list(upload_errors)
        self._delete_error = delete_error
        self.uploads = 0
        self.deleted = []

    def repo_info(self, **kwargs):
        return object()  # repo exists, so upload_to_hf skips create_repo

    def upload_folder(self, **kwargs):
        self.uploads += 1
        err = self._upload_errors.pop(0) if self._upload_errors else None
        if err is not None:
            raise err

    def delete_file(self, path, repo_id=None, repo_type=None):
        if self._delete_error is not None:
            raise self._delete_error
        self.deleted.append(path)


def _run(api):
    """Invoke upload_to_hf with HfApi swapped for the fake."""
    original = upload_mod.HfApi
    upload_mod.HfApi = lambda token=None: api
    try:
        upload_mod.upload_to_hf(REPO_ID, "/nonexistent")  # never touched: upload_folder is faked
    finally:
        upload_mod.HfApi = original


def _expect_raise(api):
    try:
        _run(api)
    except HfHubHTTPError as e:
        return e
    raise AssertionError("expected the upload error to propagate, but it was swallowed")


def test_lfs_pointer_deletes_exact_path_then_retries():
    api = _FakeApi(upload_errors=[_HfError(LFS_BODY)])
    _run(api)  # must not raise: recovery absorbs the 400

    # The whole point: exactly the offending path, with no trailing newline
    # dragged in by the `.+` capture, and nothing else removed.
    assert api.deleted == [OFFENDING], f"deleted: {api.deleted!r}"
    assert api.uploads == 2, f"expected the upload to be retried once, got {api.uploads} call(s)"
    print("PASS: broken LFS pointer -> deleted exactly the offending file, retried upload")


def test_unrelated_400_is_not_recovered():
    # A 400 with no LFS pointer in it must never reach the delete branch.
    api = _FakeApi(upload_errors=[_HfError("400 Client Error: Bad Request - invalid repo name")])
    err = _expect_raise(api)

    assert "invalid repo name" in str(err), f"wrong error propagated: {err}"
    assert api.deleted == [], f"must not delete anything on an unrelated 400, deleted {api.deleted!r}"
    assert api.uploads == 1, f"must not retry an unrelated 400, got {api.uploads} upload(s)"
    print("PASS: unrelated 400 propagates with no remote deletion")


def test_unparseable_lfs_error_is_not_recovered():
    # Right rejection, but HF worded it without the "Offending file: -" line, so
    # there is no path to delete. Must fail loud rather than guess at one.
    api = _FakeApi(upload_errors=[_HfError("400 Bad Request: LFS pointer is broken")])
    _expect_raise(api)

    assert api.deleted == [], f"no path parsed, so nothing may be deleted, deleted {api.deleted!r}"
    assert api.uploads == 1, f"must not retry when no path was parsed, got {api.uploads} upload(s)"
    print("PASS: LFS error without a parseable path raises instead of deleting")


def test_non_lfs_400_naming_a_file_is_not_recovered():
    # The regex alone would happily parse a path out of this, so the "LFS pointer"
    # string check is what stops a delete. Without it this 400 costs a remote file.
    api = _FakeApi(upload_errors=[_HfError(
        "400 Client Error: Bad Request\n"
        f"Invalid request: file exceeds the per-file size limit. Offending file: - {OFFENDING}\n"
    )])
    _expect_raise(api)

    assert api.deleted == [], f"a non-LFS 400 must not delete anything, deleted {api.deleted!r}"
    assert api.uploads == 1, f"must not retry a non-LFS 400, got {api.uploads} upload(s)"
    print("PASS: a non-LFS 400 that names a file still deletes nothing")


def test_delete_failure_reraises_original_upload_error():
    # If the delete is refused (permissions, 429), the actionable error is the
    # upload rejection, not the delete failure — and no retry may be attempted.
    api = _FakeApi(upload_errors=[_HfError(LFS_BODY)], delete_error=RuntimeError("403 forbidden"))
    err = _expect_raise(api)

    assert "LFS pointer" in str(err), f"should re-raise the original upload error, got {err}"
    assert api.uploads == 1, f"must not retry after a failed delete, got {api.uploads} upload(s)"
    print("PASS: failed delete re-raises the original upload error, no retry")


if __name__ == "__main__":
    test_lfs_pointer_deletes_exact_path_then_retries()
    test_unrelated_400_is_not_recovered()
    test_unparseable_lfs_error_is_not_recovered()
    test_non_lfs_400_naming_a_file_is_not_recovered()
    test_delete_failure_reraises_original_upload_error()
    print("\nAll tests passed.")
