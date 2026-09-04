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


# =========================================================================
# Task A4 — the conditional result write: ordering guard and confirmation
# lock. See design decision 3 for why the lock is absolute.
# =========================================================================


def _insert_trade(user_id):
    """One `trades` row for `user_id`, straight through SQL.

    Same style as `_insert_correction` / `_insert_strategy` above: the write
    guard cares only that a trade with this owner exists, and there is no
    shared factory module in this repo to reuse.
    """
    from src.tradelens.db.session import SessionLocal

    db = SessionLocal()
    try:
        result = db.execute(
            sa_text("INSERT INTO trades (user_id, asset) VALUES (:u, 'NQ')"),
            {"u": user_id},
        )
        db.commit()
        return int(result.lastrowid)
    finally:
        db.close()


def _analysis_usage():
    """A `Usage` for the store call. Named apart from every helper above."""
    from src.tradelens.services.ai_client import Usage

    return Usage("claude-opus-5", 10, 20, 30, 0.01, 0.5)


def _analysis_row(trade_id):
    from src.tradelens.db.models import AIAnalysis
    from src.tradelens.db.session import SessionLocal

    db = SessionLocal()
    try:
        return db.query(AIAnalysis).filter(AIAnalysis.trade_id == trade_id).first()
    finally:
        db.close()


def _confirm_labels(trade_id, **fields):
    """Simulate Task C1's confirm, for tests that only need its effect."""
    import json

    from src.tradelens.db.models import AIAnalysis
    from src.tradelens.db.session import SessionLocal

    db = SessionLocal()
    try:
        row = db.query(AIAnalysis).filter(AIAnalysis.trade_id == trade_id).one()
        for name, value in fields.items():
            setattr(row, name, value)
        row.confirmed_at = "2026-09-01T09:30:00+00:00"
        row.confirmed_fields_json = json.dumps(sorted(fields))
        db.commit()
    finally:
        db.close()


def _set_confirmed_json(trade_id, raw):
    from src.tradelens.db.models import AIAnalysis
    from src.tradelens.db.session import SessionLocal

    db = SessionLocal()
    try:
        row = db.query(AIAnalysis).filter(AIAnalysis.trade_id == trade_id).one()
        row.confirmed_fields_json = raw
        db.commit()
    finally:
        db.close()


@pytest.fixture()
def owned_trade(two_users):
    """One user with one trade, in the isolated tmp database. (user, trade)."""
    owner, _other = two_users
    return owner, _insert_trade(owner)


@pytest.fixture()
def two_users_with_trades(two_users):
    """Two users, one trade each. Returns ((u1, t1), (u2, t2))."""
    first, second = two_users
    return (first, _insert_trade(first)), (second, _insert_trade(second))


# --- rule 1: ordering ----------------------------------------------------


def test_a_newer_job_replaces_an_older_job_s_result(owned_trade):
    """The ordinary re-run: the trader asked for a fresh read and gets one."""
    user_id, trade_id = owned_trade
    ta.store_analysis(
        user_id,
        trade_id,
        job_id=1,
        vision_result={"bias": "bullish"},
        usage=_analysis_usage(),
    )
    outcome = ta.store_analysis(
        user_id,
        trade_id,
        job_id=2,
        vision_result={"bias": "bearish"},
        usage=_analysis_usage(),
    )
    assert outcome.written is True
    assert _analysis_row(trade_id).bias == "bearish"


def test_a_stale_job_cannot_land_on_top_of_a_newer_result(owned_trade):
    """Two jobs in flight; the slow older one finishes last.

    Without the conditional write it wins purely by being slow, and the
    trader sees the reading they did not ask for with nothing saying so.
    """
    user_id, trade_id = owned_trade
    ta.store_analysis(
        user_id,
        trade_id,
        job_id=9,
        vision_result={"bias": "bearish"},
        usage=_analysis_usage(),
    )
    outcome = ta.store_analysis(
        user_id,
        trade_id,
        job_id=4,
        vision_result={"bias": "bullish"},
        usage=_analysis_usage(),
    )
    assert outcome.written is False
    assert outcome.superseded is True
    assert _analysis_row(trade_id).bias == "bearish"
    assert _analysis_row(trade_id).analysis_job_id == 9


def test_a_job_replaying_its_own_id_does_not_write_twice(owned_trade):
    """`<` not `<=`: a redelivered job is not newer than itself."""
    user_id, trade_id = owned_trade
    ta.store_analysis(
        user_id,
        trade_id,
        job_id=5,
        vision_result={"bias": "bearish"},
        usage=_analysis_usage(),
    )
    outcome = ta.store_analysis(
        user_id,
        trade_id,
        job_id=5,
        vision_result={"bias": "bullish"},
        usage=_analysis_usage(),
    )
    assert outcome.written is False
    assert _analysis_row(trade_id).bias == "bearish"


# --- rule 2: the confirmation lock ---------------------------------------


def test_a_job_enqueued_before_a_confirmation_cannot_replace_it(owned_trade):
    """The obvious half of the lock: the job was reading a stale world."""
    user_id, trade_id = owned_trade
    ta.store_analysis(
        user_id,
        trade_id,
        job_id=1,
        vision_result={"bias": "bullish"},
        usage=_analysis_usage(),
    )
    _confirm_labels(trade_id, bias="neutral")

    outcome = ta.store_analysis(
        user_id,
        trade_id,
        job_id=2,
        vision_result={"bias": "bearish", "trade_quality": 8},
        usage=_analysis_usage(),
    )

    assert outcome.written is True
    assert outcome.locked == frozenset({"bias"})
    # The confirmed field is untouched; every unconfirmed field still updates.
    assert _analysis_row(trade_id).bias == "neutral"
    assert _analysis_row(trade_id).trade_quality == 8


def test_a_job_started_after_a_confirmation_STILL_cannot_replace_it(owned_trade):
    """THE decided rule, and the one that reverses the first draft.

    Clicking re-analyse asks for analysis — usually because a better
    screenshot was attached. It is not a request to discard the trader's own
    judgement, and it says nothing about labels. A confirmed value stays
    until the trader changes it, whatever the job ordering.

    Asserted against a job whose every plausible "enqueued at" reading is
    LATER than the confirmation: the highest job id on the row and a real
    clock reading taken after `confirmed_at`. A rule that consulted timing at
    all would let this write land, so this test fails against the design
    that was turned down, not merely against a broken implementation.
    """
    import datetime as _dt2

    user_id, trade_id = owned_trade
    ta.store_analysis(
        user_id,
        trade_id,
        job_id=1,
        vision_result={"bias": "bullish"},
        usage=_analysis_usage(),
    )
    _confirm_labels(trade_id, bias="neutral")

    # Every clock says this job is newer than the confirmation.
    now = _dt2.datetime.now(_dt2.timezone.utc).isoformat()
    assert now > _analysis_row(trade_id).confirmed_at

    outcome = ta.store_analysis(
        user_id,
        trade_id,
        job_id=99,
        vision_result={"bias": "bearish"},
        usage=_analysis_usage(),
    )
    assert outcome.written is True
    assert outcome.locked == frozenset({"bias"})
    assert _analysis_row(trade_id).bias == "neutral"


def test_store_analysis_takes_no_enqueue_timestamp_at_all(owned_trade):
    """The rejected design needed a job timestamp; this one must not have one.

    Pins the shape of the decision as well as its effect: there is no
    parameter through which a caller could reintroduce a timing comparison,
    and no `confirmed_at` read on the write path.
    """
    import inspect

    signature = inspect.signature(ta.store_analysis)
    assert "enqueued_at" not in signature.parameters
    assert not any(
        "enqueued" in name or "created_at" in name for name in signature.parameters
    )
    source = inspect.getsource(ta.store_analysis)
    assert "confirmed_at" not in source


def test_the_locked_field_s_new_reading_is_still_recorded_for_the_trader(owned_trade):
    """Locked means "not applied", never "hidden"."""
    import json

    user_id, trade_id = owned_trade
    ta.store_analysis(
        user_id,
        trade_id,
        job_id=1,
        vision_result={"bias": "bullish"},
        usage=_analysis_usage(),
    )
    _confirm_labels(trade_id, bias="neutral")
    ta.store_analysis(
        user_id,
        trade_id,
        job_id=2,
        vision_result={"bias": "bearish"},
        usage=_analysis_usage(),
    )
    assert json.loads(_analysis_row(trade_id).raw_response_json)["bias"] == "bearish"


def test_raw_response_json_stays_current_even_when_it_is_itself_confirmed(owned_trade):
    """`raw_response_json` is not a label, so it is never lockable.

    Task D3's one-click adopt reads it, so a stored list naming it must not
    freeze the newest model output out of the row.
    """
    import json

    user_id, trade_id = owned_trade
    ta.store_analysis(
        user_id,
        trade_id,
        job_id=1,
        vision_result={"bias": "bullish"},
        usage=_analysis_usage(),
    )
    _set_confirmed_json(trade_id, json.dumps(["bias", "raw_response_json"]))
    outcome = ta.store_analysis(
        user_id,
        trade_id,
        job_id=2,
        vision_result={"bias": "bearish"},
        usage=_analysis_usage(),
    )
    assert "raw_response_json" not in outcome.locked
    assert json.loads(_analysis_row(trade_id).raw_response_json)["bias"] == "bearish"


def test_a_confirmed_field_survives_any_number_of_re_runs(owned_trade):
    """The lock is a property, not a one-shot guard."""
    user_id, trade_id = owned_trade
    ta.store_analysis(
        user_id,
        trade_id,
        job_id=1,
        vision_result={"bias": "bullish"},
        usage=_analysis_usage(),
    )
    _confirm_labels(trade_id, bias="neutral")
    for job_id in range(2, 8):
        ta.store_analysis(
            user_id,
            trade_id,
            job_id=job_id,
            vision_result={"bias": "bearish"},
            usage=_analysis_usage(),
        )
    assert _analysis_row(trade_id).bias == "neutral"


def test_an_unparseable_confirmed_field_list_locks_nothing(owned_trade):
    """Fail toward a refreshable row, not a permanently frozen one."""
    user_id, trade_id = owned_trade
    ta.store_analysis(
        user_id,
        trade_id,
        job_id=1,
        vision_result={"bias": "bullish"},
        usage=_analysis_usage(),
    )
    _set_confirmed_json(trade_id, "{not json")
    outcome = ta.store_analysis(
        user_id,
        trade_id,
        job_id=2,
        vision_result={"bias": "bearish"},
        usage=_analysis_usage(),
    )
    assert outcome.locked == frozenset()
    assert _analysis_row(trade_id).bias == "bearish"


def test_a_confirmed_name_that_is_not_a_writable_column_is_ignored(owned_trade):
    """The lock list is data, and data is never a column name."""
    import json

    user_id, trade_id = owned_trade
    ta.store_analysis(
        user_id,
        trade_id,
        job_id=1,
        vision_result={"bias": "bullish"},
        usage=_analysis_usage(),
    )
    _set_confirmed_json(trade_id, json.dumps(["detected_setup", "journal_entry_md"]))
    outcome = ta.store_analysis(
        user_id,
        trade_id,
        job_id=2,
        vision_result={"bias": "bearish"},
        usage=_analysis_usage(),
    )
    assert outcome.written is True
    assert outcome.locked == frozenset()
    assert _analysis_row(trade_id).analysis_job_id == 2
    assert _analysis_row(trade_id).bias == "bearish"


def test_the_stored_lock_list_can_never_name_the_job_id_column(owned_trade):
    """A hostile entry must not be able to freeze the ordering guard itself.

    If `analysis_job_id` were lockable, one stored string would stop the row
    ever advancing and every later job would read as stale forever.
    """
    import json

    user_id, trade_id = owned_trade
    ta.store_analysis(
        user_id,
        trade_id,
        job_id=1,
        vision_result={"bias": "bullish"},
        usage=_analysis_usage(),
    )
    _set_confirmed_json(trade_id, json.dumps(["analysis_job_id", "cost_usd"]))
    outcome = ta.store_analysis(
        user_id,
        trade_id,
        job_id=2,
        vision_result={"bias": "bearish"},
        usage=_analysis_usage(),
    )
    assert outcome.written is True
    assert _analysis_row(trade_id).analysis_job_id == 2


def test_confirmed_fields_reads_the_stored_list(owned_trade):
    """The helper Task C1 and the panel both read, pinned on its own."""
    import json

    user_id, trade_id = owned_trade
    ta.store_analysis(
        user_id,
        trade_id,
        job_id=1,
        vision_result={"bias": "bullish"},
        usage=_analysis_usage(),
    )
    assert ta.confirmed_fields(None) == frozenset()
    assert ta.confirmed_fields(_analysis_row(trade_id)) == frozenset()
    _set_confirmed_json(trade_id, json.dumps(["bias", "trade_quality"]))
    assert ta.confirmed_fields(_analysis_row(trade_id)) == frozenset(
        {"bias", "trade_quality"}
    )
    _set_confirmed_json(trade_id, json.dumps({"bias": True}))
    assert ta.confirmed_fields(_analysis_row(trade_id)) == frozenset()


# --- ownership -----------------------------------------------------------


def test_another_owner_s_trade_is_never_written(two_users_with_trades):
    """Ownership resolves through the trade join; aianalysis has no user_id."""
    (owner, _owner_trade), (_other, other_trade) = two_users_with_trades
    with pytest.raises(ValueError):
        ta.store_analysis(
            owner,
            other_trade,
            job_id=1,
            vision_result={"bias": "bullish"},
            usage=_analysis_usage(),
        )
    assert _analysis_row(other_trade) is None


def test_a_bogus_owner_is_refused_before_any_write(owned_trade):
    """Owner identity is validated here, not assumed by the caller."""
    _user_id, trade_id = owned_trade
    with pytest.raises(ValueError):
        ta.store_analysis(
            0,
            trade_id,
            job_id=1,
            vision_result={"bias": "bullish"},
            usage=_analysis_usage(),
        )
    assert _analysis_row(trade_id) is None


# --- the run function: the image source, cost, and terminal failure -------


def test_analysis_reads_the_promoted_object_and_nothing_else(owned_trade, monkeypatch):
    """The model only ever sees bytes we produced.

    Pinning the FUNCTION, not the bytes: `read_owned_final_object` is what
    enforces both the ownership join and `_is_final_key`, so a future change
    that reads a quarantine object or an upload key directly must fail here.
    """
    user_id, trade_id = owned_trade
    seen = {}

    def fake_read(uid, sid):
        seen["args"] = (uid, sid)
        return b"promoted-bytes"

    monkeypatch.setattr(ta.storage, "read_owned_final_object", fake_read)
    monkeypatch.setattr(
        ta, "_analyse_bytes", lambda data, on_usage: {"bias": "bullish"}
    )

    ta.run_analysis(
        user_id,
        trade_id,
        44,
        job_id=1,
        on_usage=lambda usage: None,
    )
    assert seen["args"] == (user_id, 44)


def test_an_unreadable_screenshot_fails_terminally_and_costs_nothing(
    owned_trade, monkeypatch
):
    """No image, no billable call — and the failure is terminal, not a retry."""
    user_id, trade_id = owned_trade
    calls = []
    monkeypatch.setattr(ta.storage, "read_owned_final_object", lambda u, s: None)
    monkeypatch.setattr(ta, "_analyse_bytes", lambda data, on_usage: calls.append(1))

    with pytest.raises(ta.AnalysisUnavailable):
        ta.run_analysis(
            user_id,
            trade_id,
            44,
            job_id=1,
            on_usage=lambda usage: None,
        )
    assert calls == []


def test_a_present_but_unreadable_blob_never_reaches_the_paid_call(
    owned_trade, monkeypatch
):
    """Bytes exist but are not an image — that must not buy a vision call.

    The other tests in this group patch `_analyse_bytes` wholesale, so none
    of them exercises the local quality pre-check at all; removing it left
    every one of them green while an unopenable object went straight to a
    paid Opus call. The promoted object should always be valid PNG, which is
    exactly why this is worth pinning: when that assumption breaks, the
    failure is silent and billed.
    """
    called = []

    monkeypatch.setattr(
        ta.storage, "read_owned_final_object", lambda u, s: b"not an image at all"
    )
    monkeypatch.setattr(
        ta,
        "analyze_screenshot_v3",
        lambda *a, **k: called.append(1) or ({}, None),
    )

    user_id, trade_id = owned_trade
    with pytest.raises(ta.AnalysisUnavailable):
        ta.run_analysis(
            user_id,
            trade_id,
            44,
            job_id=1,
            on_usage=lambda usage: None,
        )
    assert called == []


def test_usage_is_recorded_even_when_the_response_fails_to_parse(
    owned_trade, monkeypatch
):
    """A billed call that then fails must still appear in cost tracking."""
    user_id, trade_id = owned_trade
    logged = []

    def fake_analyse(data, on_usage):
        on_usage(_analysis_usage())
        raise ta.AnalysisUnavailable("unparseable")

    monkeypatch.setattr(ta.storage, "read_owned_final_object", lambda u, s: b"x")
    monkeypatch.setattr(ta, "_analyse_bytes", fake_analyse)

    with pytest.raises(ta.AnalysisUnavailable):
        ta.run_analysis(
            user_id,
            trade_id,
            44,
            job_id=1,
            on_usage=logged.append,
        )
    assert len(logged) == 1
