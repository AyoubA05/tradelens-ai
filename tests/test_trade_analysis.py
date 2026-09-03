"""Phase 5 service layer: fingerprints, write guards, output validation."""

import pytest
from sqlalchemy import text as sa_text

from src.tradelens.services import trade_analysis as ta
from src.tradelens.services.trade_analysis import (
    ANALYSIS_JOB_KIND,
    GRADE_JOB_KIND,
    JOURNAL_JOB_KIND,
    analysis_key,
    grade_key,
    journal_key,
)

U = 1  # one owner for every key test; owner separation is the DB constraint's job


def _insert_correction(user_id):
    """Insert one `Correction` row for `user_id`, straight through SQL.

    Kept in the test file on purpose: `record_correction` needs a real trade
    and analysis row, and the only thing this test cares about is that the
    owner's correction *state* moved. A production helper that exists solely
    for a test would be a worse answer than four lines of INSERT here.
    """
    from src.tradelens.db.session import SessionLocal

    db = SessionLocal()
    try:
        db.execute(
            sa_text(
                "INSERT INTO corrections "
                "(trade_id, ai_analysis_id, field, ai_value, user_value, "
                " user_reason, created_at, user_id) "
                "VALUES (1, 1, 'bias', 'bullish', 'bearish', NULL, "
                "'2026-09-01T10:00:00+00:00', :u)"
            ),
            {"u": user_id},
        )
        db.commit()
    finally:
        db.close()


@pytest.fixture()
def frozen_input_version(monkeypatch):
    """Pin the owner-state half of the digest so pure-input tests stay pure.

    Without this every key test would also depend on whatever corrections and
    strategy rows the database happens to hold, and a failure would not say
    which half moved.
    """
    monkeypatch.setattr(ta, "_strategy_fingerprint", lambda uid: "s")
    monkeypatch.setattr(ta, "_corrections_fingerprint", lambda uid: "c")


@pytest.fixture()
def two_owners_with_corrections(two_users):
    """Two real owners in an isolated database, each with one correction.

    Both start with a correction so the "before" digest is a real value and
    not the empty-state constant every owner would share regardless.
    """
    first, second = two_users
    _insert_correction(first)
    _insert_correction(second)
    return first, second


def test_an_unchanged_trade_produces_the_same_analysis_key(frozen_input_version):
    """The same request twice is one job, so a double-click is one bill."""
    first = analysis_key(U, 7, 12, "2026-09-01T10:00:00+00:00")
    second = analysis_key(U, 7, 12, "2026-09-01T10:00:00+00:00")
    assert first == second


def test_editing_the_trade_produces_a_different_analysis_key(frozen_input_version):
    """A changed trade genuinely deserves a fresh read — that is not a retry."""
    before = analysis_key(U, 7, 12, "2026-09-01T10:00:00+00:00")
    after = analysis_key(U, 7, 12, "2026-09-01T11:30:00+00:00")
    assert before != after


def test_a_different_screenshot_produces_a_different_analysis_key(frozen_input_version):
    assert analysis_key(U, 7, 12, "t") != analysis_key(U, 7, 13, "t")


def test_a_different_trade_produces_a_different_analysis_key(frozen_input_version):
    assert analysis_key(U, 7, 12, "t") != analysis_key(U, 8, 12, "t")


def test_every_key_is_namespaced_by_its_kind(frozen_input_version):
    """A journal key must never collide with a grade key for the same inputs.

    They share every input, so without the kind prefix one enqueue would
    return the other's job and the trader would poll a grade for a journal.
    """
    assert journal_key(U, 7, "t", "a") != grade_key(U, 7, "t", "a")
    assert journal_key(U, 7, "t", "a").startswith(JOURNAL_JOB_KIND)
    assert grade_key(U, 7, "t", "a").startswith(GRADE_JOB_KIND)
    assert analysis_key(U, 7, 1, "t").startswith(ANALYSIS_JOB_KIND)


def test_a_regenerated_journal_after_new_analysis_is_a_new_key(frozen_input_version):
    """Re-analysis moves the analysis row, so the journal is genuinely stale."""
    assert journal_key(U, 7, "t", "a1") != journal_key(U, 7, "t", "a2")


# --- every OTHER effective input is in the digest too --------------------
#
# Each of these is a way the answer changes without any visible input
# changing. A key that ignores one of them is a cache that serves a stale
# result under a fresh timestamp, which is worse than no cache.


def test_a_model_change_produces_a_different_key(monkeypatch, frozen_input_version):
    """A job cached under the previous model is a wrong answer, not a saving."""
    before = analysis_key(U, 7, 12, "t")
    monkeypatch.setattr(ta, "ANTHROPIC_MODEL_ID", "claude-something-else")
    assert analysis_key(U, 7, 12, "t") != before


def test_an_effort_change_produces_a_different_key(monkeypatch, frozen_input_version):
    before = analysis_key(U, 7, 12, "t")
    monkeypatch.setattr(ta.settings, "effort_default", "high")
    assert analysis_key(U, 7, 12, "t") != before


def test_demo_mode_never_shares_a_job_with_a_live_request(
    monkeypatch, frozen_input_version
):
    """DEMO_MODE replaces the output wholesale, in both directions."""
    live = analysis_key(U, 7, 12, "t")
    monkeypatch.setattr(ta.settings, "demo_mode", True)
    assert analysis_key(U, 7, 12, "t") != live


def test_editing_the_strategy_profile_produces_a_different_key(monkeypatch):
    """`generate_journal` and `grade_trade` both take the profile.

    A journal graded against last week's rules is not the journal the trader
    asked for after editing them.
    """
    monkeypatch.setattr(ta, "_corrections_fingerprint", lambda uid: "c")
    monkeypatch.setattr(ta, "_strategy_fingerprint", lambda uid: "profile-v1")
    before = journal_key(U, 7, "t", "a")
    monkeypatch.setattr(ta, "_strategy_fingerprint", lambda uid: "profile-v2")
    assert journal_key(U, 7, "t", "a") != before


def test_a_new_correction_produces_a_different_key(monkeypatch):
    """THE one that makes 'correct the AI, then re-run' work at all.

    Without the correction state in the digest the re-run returns the cached
    job the correction was meant to change, and the trader's correction
    appears to do nothing.
    """
    monkeypatch.setattr(ta, "_strategy_fingerprint", lambda uid: "s")
    monkeypatch.setattr(ta, "_corrections_fingerprint", lambda uid: "3:41")
    before = journal_key(U, 7, "t", "a")
    monkeypatch.setattr(ta, "_corrections_fingerprint", lambda uid: "4:52")
    assert journal_key(U, 7, "t", "a") != before


def test_one_owner_s_corrections_do_not_change_another_owner_s_key(
    two_owners_with_corrections,
):
    """The digest is owner-scoped: my corrections are not in your fingerprint."""
    first, second = two_owners_with_corrections
    before = ta.ai_input_version(second)
    _insert_correction(first)
    assert ta.ai_input_version(second) == before


def test_a_new_correction_moves_that_owner_s_own_input_version(
    two_owners_with_corrections,
):
    """The owner-scoping test above must not pass by the digest being inert.

    If `ai_input_version` ignored corrections entirely it would satisfy the
    isolation assertion trivially, so pin the other direction here.
    """
    first, _second = two_owners_with_corrections
    before = ta.ai_input_version(first)
    _insert_correction(first)
    assert ta.ai_input_version(first) != before


def test_the_input_version_never_raises_when_the_database_is_unhappy(monkeypatch):
    """A digest that throws would take down enqueue for every kind.

    Degrading to a constant is safe in the only direction that matters: it
    can make two different states share a key (a stale result), never make
    one owner read another's. It is logged rather than silent.
    """

    def boom(_uid):
        raise RuntimeError("db down")

    monkeypatch.setattr(ta, "_corrections_fingerprint", boom)
    assert isinstance(ta.ai_input_version(U), str)


def test_the_input_version_logs_when_it_degrades(monkeypatch, caplog):
    """Degrading silently would hide a database problem behind stale results."""

    def boom(_uid):
        raise RuntimeError("db down")

    monkeypatch.setattr(ta, "_corrections_fingerprint", boom)
    with caplog.at_level("ERROR"):
        ta.ai_input_version(U)
    assert any("ai_input_version degraded" in r.message for r in caplog.records)


def test_the_input_version_refuses_a_bogus_owner():
    """Owner identity is validated here, not assumed by every caller."""
    with pytest.raises(ValueError):
        ta.ai_input_version(0)
