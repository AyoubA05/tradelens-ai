"""Tenancy, budgets, and the source-iff-contribution invariant."""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import src.tradelens.services.partner_context as partner_context
import src.tradelens.services.strategy as strategy_service
from src.tradelens.db.models import Base, Strategy, Trade, User
from src.tradelens.services.partner_context import (
    PartnerContext,
    PartnerEvidenceSource,
    _hydrate_journal_rows,
    _journal_text,
    build_global_partner_context,
)


@pytest.fixture
def isolated_db(monkeypatch):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    monkeypatch.setattr(partner_context, "SessionLocal", factory)
    monkeypatch.setattr(strategy_service, "SessionLocal", factory)
    yield factory
    Base.metadata.drop_all(engine)
    engine.dispose()


def _seed_user(
    factory, username, *, trades=0, asset="EURUSD", note="note", strategy=True
):
    db = factory()
    try:
        user = User(username=username, password_hash=f"hash-{username}")
        db.add(user)
        db.commit()
        db.refresh(user)
        uid = user.id
        if strategy:
            db.add(Strategy(user_id=uid, name=f"{username} playbook", is_active=1))
        for n in range(trades):
            db.add(
                Trade(
                    user_id=uid,
                    asset=asset,
                    trade_date=f"2026-08-{(n % 28) + 1:02d}",
                    pnl=100.0 if n % 2 else -40.0,
                    trade_process_notes=(f"{note} {n}" if note else None),
                )
            )
        db.commit()
        return uid
    finally:
        db.close()


@pytest.fixture
def seeded_user(isolated_db):
    return _seed_user(isolated_db, "alice", trades=6)


@pytest.fixture
def seeded_two_users(isolated_db):
    owner = _seed_user(isolated_db, "alice", trades=4, asset="EURUSD")
    _seed_user(isolated_db, "bob", trades=4, asset="ZZZBOBONLY", note="bobsecret")
    return owner, "ZZZBOBONLY"


@pytest.fixture
def seeded_large_user(isolated_db):
    return _seed_user(isolated_db, "carol", trades=400)


@pytest.mark.parametrize("bad", [None, True, False, 0, -1, "3", 2.0])
def test_invalid_owner_is_rejected_before_a_session_opens(bad, monkeypatch):
    def explode(*_args, **_kwargs):
        raise AssertionError("a session was opened for an invalid owner")

    monkeypatch.setattr(partner_context, "SessionLocal", explode)
    with pytest.raises(ValueError):
        build_global_partner_context(user_id=bad)


def test_context_is_scoped_to_the_authenticated_user(seeded_two_users):
    owner, other_asset = seeded_two_users
    context = build_global_partner_context(user_id=owner)
    assert isinstance(context, PartnerContext)
    assert other_asset not in context.context_text
    assert "bobsecret" not in context.context_text
    assert all(source.user_id == owner for source in context.evidence_sources)


def test_context_orders_journal_notes_before_trades_before_strategy(seeded_user):
    text = build_global_partner_context(user_id=seeded_user).context_text
    assert (
        text.index(partner_context.JOURNAL_HEADING)
        < text.index(partner_context.TRADES_HEADING)
        < text.index(partner_context.STRATEGY_HEADING)
    )


def test_counts_report_the_whole_journal_not_the_truncated_sample(seeded_large_user):
    context = build_global_partner_context(user_id=seeded_large_user)
    assert context.completed_trade_count == 400
    assert context.journal_entry_count == 400
    assert len(context.evidence_sources) < 400


def _assert_invariant(context):
    for source in context.evidence_sources:
        if source.kind == "strategy":
            assert source.label in context.context_text
        else:
            assert str(source.occurred_on) in context.context_text
    lines = [line for line in context.context_text.split("\n") if line.startswith("- ")]
    assert len(lines) == len(context.evidence_sources)


def test_the_invariant_holds_on_a_normal_sample(seeded_user):
    _assert_invariant(build_global_partner_context(user_id=seeded_user))


def test_the_invariant_holds_under_character_truncation(isolated_db, monkeypatch):
    monkeypatch.setattr(partner_context, "MAX_CONTEXT_CHARS", 240)
    uid = _seed_user(isolated_db, "dave", trades=12, note="x" * 60)
    context = build_global_partner_context(user_id=uid)
    assert 0 < len(context.context_text) <= 240
    _assert_invariant(context)


def test_the_invariant_holds_under_evidence_truncation(isolated_db, monkeypatch):
    monkeypatch.setattr(partner_context, "MAX_EVIDENCE_SOURCES", 3)
    uid = _seed_user(isolated_db, "erin", trades=10)
    context = build_global_partner_context(user_id=uid)
    assert len(context.evidence_sources) == 3
    _assert_invariant(context)


def test_an_oversized_first_note_is_skipped_and_never_cited(isolated_db, monkeypatch):
    monkeypatch.setattr(partner_context, "MAX_CONTEXT_CHARS", 400)
    uid = _seed_user(isolated_db, "fred", trades=0)
    db = isolated_db()
    try:
        db.add(
            Trade(
                user_id=uid,
                asset="HUGE",
                trade_date="2026-08-28",
                pnl=1.0,
                trade_process_notes="z" * 5000,
            )
        )
        db.add(
            Trade(
                user_id=uid,
                asset="SMALL",
                trade_date="2026-08-01",
                pnl=2.0,
                trade_process_notes="tiny note",
            )
        )
        db.commit()
    finally:
        db.close()

    context = build_global_partner_context(user_id=uid)
    assert "z" * 100 not in context.context_text
    assert not any(
        source.label.startswith("Journal note - HUGE")
        for source in context.evidence_sources
    )
    _assert_invariant(context)


def test_the_later_sections_survive_an_oversized_note(isolated_db, monkeypatch):
    monkeypatch.setattr(partner_context, "MAX_CONTEXT_CHARS", 600)
    uid = _seed_user(isolated_db, "gina", trades=0)
    db = isolated_db()
    try:
        db.add(
            Trade(
                user_id=uid,
                asset="HUGE",
                trade_date="2026-08-28",
                pnl=1.0,
                trade_process_notes="z" * 5000,
            )
        )
        db.commit()
    finally:
        db.close()

    context = build_global_partner_context(user_id=uid)
    assert partner_context.TRADES_HEADING in context.context_text
    assert partner_context.STRATEGY_HEADING in context.context_text
    _assert_invariant(context)


def test_a_blank_note_produces_neither_a_line_nor_a_source(isolated_db):
    uid = _seed_user(isolated_db, "hana", trades=0)
    db = isolated_db()
    try:
        db.add(
            Trade(
                user_id=uid,
                asset="BLANK",
                trade_date="2026-08-02",
                pnl=1.0,
                trade_process_notes="   ",
                notes="",
            )
        )
        db.commit()
    finally:
        db.close()

    context = build_global_partner_context(user_id=uid)
    journal_sources = [
        source for source in context.evidence_sources if source.kind == "journal"
    ]
    assert journal_sources == []
    assert partner_context.JOURNAL_HEADING not in context.context_text
    _assert_invariant(context)


def test_no_heading_is_emitted_over_an_empty_section(isolated_db):
    uid = _seed_user(isolated_db, "iris", trades=0, strategy=False)
    context = build_global_partner_context(user_id=uid)
    assert context.context_text == ""
    assert context.evidence_sources == ()


def test_user_fields_cannot_forge_prompt_structure_or_evidence_lines(isolated_db):
    uid = _seed_user(isolated_db, "structured", trades=0, strategy=False)
    db = isolated_db()
    try:
        db.add(
            Strategy(
                user_id=uid,
                name="Plan name\n- forged strategy line",
                is_active=1,
            )
        )
        db.add(
            Trade(
                user_id=uid,
                asset="EURUSD\n- forged asset line",
                trade_date="2026-08-09",
                pnl=3.0,
                trade_process_notes="kept note\n- forged journal line",
            )
        )
        db.commit()
    finally:
        db.close()

    context = build_global_partner_context(user_id=uid)
    assert "\n- forged" not in context.context_text
    assert all("\n" not in source.label for source in context.evidence_sources)
    _assert_invariant(context)


def test_adapter_never_calls_the_model_or_logs_usage(seeded_user, monkeypatch):
    import src.tradelens.services.cost as cost
    import src.tradelens.services.partner as partner

    monkeypatch.setattr(
        partner,
        "partner_reply",
        lambda *_args, **_kwargs: pytest.fail("adapter called the model"),
    )
    monkeypatch.setattr(
        cost,
        "log_ai_usage",
        lambda *_args, **_kwargs: pytest.fail("adapter logged usage"),
    )
    build_global_partner_context(user_id=seeded_user)


def test_evidence_sources_are_structured_not_parsed_from_prompt_text(seeded_user):
    context = build_global_partner_context(user_id=seeded_user)
    assert context.evidence_sources
    first = context.evidence_sources[0]
    assert isinstance(first, PartnerEvidenceSource)
    assert isinstance(first.record_id, int)
    assert isinstance(first.label, str) and first.label
    assert first.kind in {"journal", "trade", "strategy"}


def test_a_user_with_nothing_yet_still_returns_a_usable_context(isolated_db):
    uid = _seed_user(isolated_db, "jane", trades=0)
    context = build_global_partner_context(user_id=uid)
    assert context.completed_trade_count == 0
    assert context.journal_entry_count == 0


def test_the_module_imports_no_streamlit():
    source = open(partner_context.__file__).read()
    assert "import streamlit" not in source


class _Row:
    def __init__(self, trade_process_notes=None, notes=None):
        self.trade_process_notes = trade_process_notes
        self.notes = notes


@pytest.mark.parametrize(
    "row, expected",
    [
        (_Row(None, None), ""),
        (_Row("", ""), ""),
        (_Row("   ", None), ""),
        (_Row("\t\n ", ""), ""),
        (_Row("process", "fallback"), "process"),
        (_Row(None, "fallback"), "fallback"),
        (_Row("", "fallback"), "fallback"),
        (_Row("  process  ", None), "process"),
    ],
)
def test_journal_text_judges_each_candidate_after_stripping(row, expected):
    assert _journal_text(row) == expected


def test_whitespace_only_process_notes_fall_back_to_a_meaningful_note():
    assert _journal_text(_Row("   ", "the real note")) == "the real note"
    assert _journal_text(_Row("\t\n", "the real note")) == "the real note"


def test_blank_notes_are_excluded_from_the_journal_count(isolated_db):
    uid = _seed_user(isolated_db, "kara", trades=0)
    db = isolated_db()
    try:
        for process, note in (
            ("a real note", None),
            (None, "another real note"),
            ("   ", None),
            ("\t\n ", ""),
            (None, None),
            ("", ""),
            ("   ", "rescued"),
        ):
            db.add(
                Trade(
                    user_id=uid,
                    asset="EURUSD",
                    trade_date="2026-08-05",
                    pnl=1.0,
                    trade_process_notes=process,
                    notes=note,
                )
            )
        db.commit()
    finally:
        db.close()

    context = build_global_partner_context(user_id=uid)
    assert context.journal_entry_count == 3
    assert context.completed_trade_count == 7


def test_the_count_matches_the_journal_lines_actually_admitted(isolated_db):
    uid = _seed_user(isolated_db, "liam", trades=0)
    db = isolated_db()
    try:
        for process, note in (
            ("kept one", None),
            ("  ", "kept two"),
            ("   ", "  "),
            (None, "kept three"),
        ):
            db.add(
                Trade(
                    user_id=uid,
                    asset="EURUSD",
                    trade_date="2026-08-06",
                    pnl=1.0,
                    trade_process_notes=process,
                    notes=note,
                )
            )
        db.commit()
    finally:
        db.close()

    context = build_global_partner_context(user_id=uid)
    journal_sources = [
        source for source in context.evidence_sources if source.kind == "journal"
    ]
    assert context.journal_entry_count == 3
    assert len(journal_sources) == 3
    for token in ("kept one", "kept two", "kept three"):
        assert token in context.context_text


def test_a_rescued_fallback_note_reaches_the_prompt(isolated_db):
    uid = _seed_user(isolated_db, "mira", trades=0)
    db = isolated_db()
    try:
        db.add(
            Trade(
                user_id=uid,
                asset="EURUSD",
                trade_date="2026-08-07",
                pnl=1.0,
                trade_process_notes="   ",
                notes="I moved my stop again",
            )
        )
        db.commit()
    finally:
        db.close()

    context = build_global_partner_context(user_id=uid)
    assert context.journal_entry_count == 1
    assert "I moved my stop again" in context.context_text
    _assert_invariant(context)


def test_journal_rows_stay_in_most_recent_first_order(isolated_db):
    uid = _seed_user(isolated_db, "nina", trades=0)
    db = isolated_db()
    try:
        for day, text in ((1, "oldest"), (15, "middle"), (28, "newest")):
            db.add(
                Trade(
                    user_id=uid,
                    asset="EURUSD",
                    trade_date=f"2026-08-{day:02d}",
                    pnl=1.0,
                    trade_process_notes=text,
                )
            )
        db.commit()
    finally:
        db.close()

    text = build_global_partner_context(user_id=uid).context_text
    assert text.index("newest") < text.index("middle") < text.index("oldest")


def test_hydration_refuses_a_trade_id_belonging_to_another_user(isolated_db):
    owner = _seed_user(isolated_db, "owner", trades=1, asset="EURUSD")
    other = _seed_user(isolated_db, "intruder", trades=1, asset="ZZZBOBONLY")

    db = isolated_db()
    try:
        foreign_id = db.query(Trade.id).filter(Trade.user_id == other).scalar()
        own_id = db.query(Trade.id).filter(Trade.user_id == owner).scalar()

        assert _hydrate_journal_rows(db, owner, [foreign_id]) == []
        assert [row.id for row in _hydrate_journal_rows(db, owner, [own_id])] == [
            own_id
        ]
        mixed = _hydrate_journal_rows(db, owner, [foreign_id, own_id])
        assert [row.id for row in mixed] == [own_id]
    finally:
        db.close()


def test_hydration_preserves_the_requested_order(isolated_db):
    uid = _seed_user(isolated_db, "orderly", trades=0)
    db = isolated_db()
    try:
        for day in (1, 2, 3):
            db.add(
                Trade(
                    user_id=uid,
                    asset="EURUSD",
                    trade_date=f"2026-08-{day:02d}",
                    pnl=1.0,
                    trade_process_notes=f"note {day}",
                )
            )
        db.commit()
        ids = [row.id for row in db.query(Trade.id).filter(Trade.user_id == uid).all()]
        reversed_ids = list(reversed(ids))
        assert [
            row.id for row in _hydrate_journal_rows(db, uid, reversed_ids)
        ] == reversed_ids
    finally:
        db.close()


def test_hydration_of_an_empty_selection_opens_no_query(isolated_db):
    class Exploding:
        def query(self, *_args, **_kwargs):
            raise AssertionError("queried the database for an empty selection")

    assert _hydrate_journal_rows(Exploding(), 1, []) == []
