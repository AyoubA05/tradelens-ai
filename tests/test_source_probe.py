"""The probes make structural claims, so they need structural tests.

A probe that silently returns a truncated block turns every assertion built on
it into a false pass — which is exactly what the first version of
function_source did.
"""

from tests import source_probe
from tests.source_probe import function_source, media_context, near, outside

SAMPLE = '''\
"""Module docstring."""

import re

CONSTANT = 1


def alpha(x):
    """First."""
    if x:
        return 1
    return 0


@decorator
@decorator_two
def beta():
    return "beta body"


class Gamma:
    def alpha(self):
        """A nested alpha that must not be picked up."""
        return None


def delta():
    return 3
'''


def test_function_source_returns_the_complete_body():
    block = function_source(SAMPLE, "alpha")
    assert block.startswith("def alpha(x):")
    assert '"""First."""' in block
    assert "return 0" in block
    assert "def beta" not in block


def test_function_source_stops_before_the_next_top_level_statement():
    assert "CONSTANT" not in function_source(SAMPLE, "alpha")
    assert "class Gamma" not in function_source(SAMPLE, "beta")


def test_function_source_includes_stacked_decorators():
    block = function_source(SAMPLE, "beta")
    assert block.startswith("@decorator\n@decorator_two\ndef beta():")
    assert 'return "beta body"' in block


def test_function_source_ignores_a_nested_method_of_the_same_name():
    block = function_source(SAMPLE, "alpha")
    assert "must not be picked up" not in block


def test_function_source_handles_the_last_function_in_a_file():
    block = function_source(SAMPLE, "delta")
    assert block.strip() == "def delta():\n    return 3"


def test_function_source_returns_empty_for_a_missing_name():
    assert function_source(SAMPLE, "nope") == ""


def test_outside_removes_the_whole_block_and_keeps_everything_else():
    rest = outside(SAMPLE, "beta")
    assert "beta body" not in rest
    assert "@decorator_two" not in rest
    assert "def alpha(x):" in rest
    assert "def delta():" in rest
    assert "CONSTANT = 1" in rest


def test_outside_returns_the_source_unchanged_for_a_missing_name():
    assert outside(SAMPLE, "nope") == SAMPLE


def test_outside_removes_only_the_first_match():
    doubled = SAMPLE + "\n\ndef delta():\n    return 4\n"
    rest = outside(doubled, "delta")
    assert rest.count("def delta():") == 1


def test_near_returns_a_window_and_empty_for_a_missing_anchor():
    assert "CONSTANT" in near(SAMPLE, "import re", radius=60)
    assert near(SAMPLE, "absent") == ""


CSS = """
.a { color: red; }
@media (max-width: 767px) {
  .in-phone { display: none; }
}
.after-phone { color: blue; }
@media (min-width: 768px) {
  .in-desktop { display: block; }
  @supports (display: grid) {
    .nested { display: grid; }
  }
}
.top-level-last { color: green; }
"""


def test_media_context_reports_the_enclosing_query():
    assert media_context(CSS, ".in-phone") == "(max-width: 767px)"
    assert media_context(CSS, ".in-desktop") == "(min-width: 768px)"


def test_media_context_is_empty_for_a_rule_outside_every_query():
    assert media_context(CSS, ".a {") == ""
    assert media_context(CSS, ".top-level-last") == ""


def test_a_closed_media_query_is_not_reported_as_enclosing():
    """The bug this replaced: '.after-phone' follows a closed max-width query
    and would have been reported as living inside it."""
    assert media_context(CSS, ".after-phone") == ""


def test_media_context_survives_a_nested_at_rule():
    assert media_context(CSS, ".nested") == "(min-width: 768px)"


def test_media_context_is_empty_for_absent_text():
    assert media_context(CSS, ".missing") == ""


def test_the_probes_import_nothing_beyond_the_standard_library():
    source = open(source_probe.__file__).read()
    assert "import streamlit" not in source
    assert "from src." not in source
