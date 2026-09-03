"""Phase 5 service layer: fingerprints, write guards, output validation."""

import datetime as _dt

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


def _insert_strategy(user_id, *, name, is_active, updated_at):
    """One `strategies` row, straight through SQL, like `_insert_correction`."""
    from src.tradelens.db.session import SessionLocal

    db = SessionLocal()
    try:
        db.execute(
            sa_text(
                "INSERT INTO strategies (user_id, name, is_active, updated_at) "
                "VALUES (:u, :n, :a, :t)"
            ),
            {"u": user_id, "n": name, "a": is_active, "t": updated_at},
        )
        db.commit()
    finally:
        db.close()


def test_switching_the_active_strategy_profile_moves_the_input_version(two_users):
    """Against a REAL database, not a patched fingerprint.

    An owner may hold several profiles, and `generate_journal` / `grade_trade`
    read whichever is active — `strategy.get_active_strategy` filters on
    `is_active == 1`. A fingerprint that took an arbitrary row would sit
    still while the AI's actual input changed, and the cached job would come
    back carrying the other profile's reasoning.

    Every other strategy test patches `_strategy_fingerprint` wholesale, so
    this is the only one that can see which row the query really selects.
    """
    owner, _other = two_users
    _insert_strategy(owner, name="A", is_active=1, updated_at="2026-09-01T09:00:00")
    _insert_strategy(owner, name="B", is_active=0, updated_at="2026-09-01T09:00:00")
    before = ta.ai_input_version(owner)

    # Swap which profile is active. Nothing else about either row changes,
    # so an `updated_at`-only digest would not notice this at all.
    from src.tradelens.db.session import SessionLocal

    db = SessionLocal()
    try:
        db.execute(sa_text("UPDATE strategies SET is_active = 0 WHERE name = 'A'"))
        db.execute(sa_text("UPDATE strategies SET is_active = 1 WHERE name = 'B'"))
        db.commit()
    finally:
        db.close()

    assert ta.ai_input_version(owner) != before


def test_the_strategy_fingerprint_reads_the_same_row_get_active_strategy_does(
    two_users,
):
    """The two must agree on 'the profile', or the digest describes a
    different profile than the one the model is actually given."""
    from src.tradelens.services.strategy import get_active_strategy

    owner, _other = two_users
    _insert_strategy(owner, name="inactive", is_active=0, updated_at="t")
    _insert_strategy(owner, name="active", is_active=1, updated_at="t")

    active = get_active_strategy(owner)
    assert active is not None
    assert ta._strategy_fingerprint(owner).startswith(f"{active['id']}:")


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


def test_the_input_version_refuses_rather_than_guessing_when_a_lookup_fails(
    monkeypatch,
):
    """The fingerprint is a correctness boundary, so it fails CLOSED.

    An earlier draft degraded to a constant on any lookup error, reasoning
    that a raising digest would take enqueue down. That trade was wrong: a
    constant makes every un-fingerprintable context share one identity, and
    the key IS the cache. Refusing costs a retry; guessing serves a result
    computed under a different Strategy Profile or a different set of the
    trader's own corrections, with nothing anywhere saying so.
    """

    def boom(_uid):
        raise RuntimeError("db down")

    monkeypatch.setattr(ta, "_corrections_fingerprint", boom)
    with pytest.raises(ta.AIInputVersionUnavailable):
        ta.ai_input_version(U)


def test_a_failing_lookup_stops_every_key_not_just_the_digest(monkeypatch):
    """The refusal has to reach the callers, or it protects nothing."""

    def boom(_uid):
        raise RuntimeError("db down")

    monkeypatch.setattr(ta, "_strategy_fingerprint", boom)
    for build in (
        lambda: analysis_key(U, 7, 12, "t"),
        lambda: journal_key(U, 7, "t", "a"),
        lambda: grade_key(U, 7, "t", "a"),
    ):
        with pytest.raises(ta.AIInputVersionUnavailable):
            build()


def test_the_input_version_logs_when_a_lookup_fails(monkeypatch, caplog):
    """Failing closed silently would hide a database problem behind retries."""

    def boom(_uid):
        raise RuntimeError("db down")

    monkeypatch.setattr(ta, "_corrections_fingerprint", boom)
    with caplog.at_level("ERROR"):
        with pytest.raises(ta.AIInputVersionUnavailable):
            ta.ai_input_version(U)
    assert any("ai_input_version unavailable" in r.message for r in caplog.records)


def test_two_materially_different_contexts_never_share_a_cached_job_across_a_failure(
    two_users,
):
    """THE regression: a transient lookup failure must not collapse two
    genuinely different AI contexts onto one reusable job.

    Walks the real sequence. The owner corrects the AI between the two
    requests, so the second request would legitimately produce a different
    answer. With the old constant fallback both requests keyed to the same
    `unavailable` digest, and `enqueue_with_limit` handed the second one the
    FIRST job — a finished result computed under the earlier correction set,
    returned as though it were the new one's.

    Cross-tenant was never the risk here: `ai_jobs` is unique on
    `(user_id, idempotency_key)`. The collapse is entirely inside one
    trader's own account, which is exactly where it is hardest to notice.
    """
    from src.tradelens.api import jobs

    owner, _other = two_users
    _insert_correction(owner)

    first_key = analysis_key(owner, 7, 12, "t")
    first_id, created = jobs.enqueue_with_limit(
        owner,
        ta.ANALYSIS_JOB_KIND,
        first_key,
        {"trade_id": 7, "screenshot_id": 12, "key": first_key},
        since=_dt.datetime.now(_dt.timezone.utc) - _dt.timedelta(hours=24),
        limit=ta.MAX_ANALYSES_PER_WINDOW,
    )
    assert created is True

    # The trader corrects the AI. The next analysis is genuinely a different
    # question, and must not be answered with the previous one's job.
    _insert_correction(owner)

    # ...and the fingerprint lookup is transiently unavailable right then.
    import unittest.mock as _mock

    with _mock.patch.object(
        ta, "_corrections_fingerprint", side_effect=RuntimeError("db down")
    ):
        with pytest.raises(ta.AIInputVersionUnavailable):
            analysis_key(owner, 7, 12, "t")

    # Nothing was enqueued during the outage, so nothing can be mistakenly
    # reused. Once the lookup recovers the changed context gets its own key.
    recovered_key = analysis_key(owner, 7, 12, "t")
    assert recovered_key != first_key

    second_id, created_again = jobs.enqueue_with_limit(
        owner,
        ta.ANALYSIS_JOB_KIND,
        recovered_key,
        {"trade_id": 7, "screenshot_id": 12, "key": recovered_key},
        since=_dt.datetime.now(_dt.timezone.utc) - _dt.timedelta(hours=24),
        limit=ta.MAX_ANALYSES_PER_WINDOW,
    )
    assert created_again is True
    assert second_id != first_id


def test_the_input_version_refuses_a_bogus_owner():
    """Owner identity is validated here, not assumed by every caller."""
    with pytest.raises(ValueError):
        ta.ai_input_version(0)
