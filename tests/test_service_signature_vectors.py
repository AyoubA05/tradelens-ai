"""Python half of the cross-language signing contract.

The TypeScript suite asserts it reproduces the expectations file; this asserts
the expectations file still matches the Python implementation that produced it.
Together they fail the build if either side drifts.
"""

import json
import pathlib
import subprocess
import sys

import pytest

from src.tradelens.api.security import build_message, canonical_query, sign_request

ROOT = pathlib.Path(__file__).resolve().parents[1]
SPEC = json.loads(
    (ROOT / "docs/contracts/service-signature-vectors.json").read_text(encoding="utf-8")
)
EXPECTATIONS_PATH = ROOT / "web/__tests__/fixtures/signature-expectations.json"


def _sign(vector):
    return sign_request(
        SPEC["secret"],
        vector["timestamp"],
        vector["method"],
        vector["path"],
        vector["query"],
        vector["body"].encode("utf-8"),
    )


@pytest.mark.parametrize("vector", SPEC["vectors"], ids=lambda v: v["name"])
def test_each_vector_matches_the_committed_expectation(vector):
    expected = json.loads(EXPECTATIONS_PATH.read_text(encoding="utf-8"))
    assert _sign(vector) == expected[vector["name"]]


def test_every_vector_has_an_expectation():
    expected = json.loads(EXPECTATIONS_PATH.read_text(encoding="utf-8"))
    assert sorted(expected) == sorted(v["name"] for v in SPEC["vectors"])


def test_the_expectations_file_is_regenerable():
    """Guards against a hand-edited expectations file.

    The file is derived output. If someone edits it to make a failing test pass,
    the two languages agree on a value neither implementation produces.
    """
    before = EXPECTATIONS_PATH.read_text(encoding="utf-8")
    subprocess.run(
        [sys.executable, "scripts/generate_signature_expectations.py"],
        cwd=ROOT,
        check=True,
        capture_output=True,
    )
    assert EXPECTATIONS_PATH.read_text(encoding="utf-8") == before


def test_method_case_does_not_change_the_message():
    assert build_message("1", "post", "/x", "", b"") == build_message(
        "1", "POST", "/x", "", b""
    )


def test_reordering_the_query_changes_the_signature():
    """Parameter order is observable for duplicate keys and must be bound.

    Treating every reordering as equivalent let a captured signature for
    ``sort=created&sort=name`` authorize the reverse order even though common
    query parsers expose that order to handlers.
    """
    assert canonical_query("sort=created&sort=name") != canonical_query(
        "sort=name&sort=created"
    )


def test_a_changed_query_value_changes_the_signature():
    """And the property it must not cost us."""
    assert canonical_query("limit=10") != canonical_query("limit=999")


def test_blank_values_survive_canonicalisation():
    assert canonical_query("debug") == "debug="


def test_sub_delims_are_escaped():
    """Python's quote() escapes these; JavaScript's encodeURIComponent does not.
    The TypeScript side compensates, and this pins the expected form."""
    assert canonical_query("q=a'b") == "q=a%27b"


def test_a_leading_question_mark_is_literal_query_data():
    """The verifier receives a raw query without its URL delimiter.

    A leading ``?`` is therefore part of the first parameter name. Collapsing
    it with the delimiter-free form lets one signature authorize two query
    strings that Starlette exposes differently to a handler.
    """
    assert canonical_query("?a=1&b=2") != canonical_query("a=1&b=2")
    assert canonical_query("?") == "%3F="
