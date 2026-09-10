"""The Strategy Profile write contract.

The profile is the rulebook every AI review reads, so these tests treat a
write as a change to a prompt: it must be owned, serialized, version-checked,
bounded, and never silently merged or truncated.
"""

from __future__ import annotations

from src.tradelens.services import strategy_playbook as pb
from src.tradelens.ui.components import strategy_profile as ui_pb


def test_the_ui_module_serves_the_service_constants_not_a_copy():
    # Identity, not equality: two equal copies drift the first time one is edited.
    assert ui_pb.STARTER_TEMPLATE is pb.STARTER_TEMPLATE
    assert ui_pb.SECTION_FIELDS is pb.SECTION_FIELDS
    assert ui_pb.profile_completion is pb.profile_completion


def test_six_sections_cover_profile_fields_exactly_once():
    from src.tradelens.services.strategy import _PROFILE_FIELDS

    flat = [f for group in pb.SECTION_FIELDS for f in group]
    assert len(pb.SECTION_FIELDS) == len(pb.SECTION_LABELS) == len(pb.SECTION_IDS) == 6
    assert len(flat) == len(set(flat))
    assert set(flat) <= _PROFILE_FIELDS


def test_a_section_is_written_by_any_one_field_and_blank_is_not_written():
    assert pb.profile_completion({}) == (0, 6)
    assert pb.profile_completion({"name": "   "}) == (0, 6)
    assert pb.profile_completion({"name": "X", "take_profit_rules": "TP"}) == (2, 6)


def test_the_repeat_threshold_is_the_streamlit_one():
    from src.tradelens.ui.components import corrections_sidebar

    assert corrections_sidebar._REPEAT_THRESHOLD == pb.REPEAT_THRESHOLD == 5
