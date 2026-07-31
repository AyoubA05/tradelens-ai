"""
Subprocess helper: drive real Settings interactions under AppTest.

Run in a child process with an isolated DB, for the same reason as
app_boot_check.py — reloading src.tradelens mid-suite creates a second copy
of ai_client and breaks every downstream `isinstance(x, AIUnavailable)`
check. Keep the subprocess boundary.

These click, type and read the database back. The destructive scenarios
matter most: a confirmation gate that renders but does not gate is worse
than no gate, because it reads as protection.

Usage:
    DATABASE_URL=sqlite:///<tmp> python settings_flow_check.py <root> <scenario>

Exits 0 on success; nonzero with a message on failure.
"""

import sys

PAGE = "src/tradelens/ui/pages/9_Settings.py"
UID = 1


def _account():
    from src.tradelens.db.models import User
    from src.tradelens.db.session import SessionLocal

    session = SessionLocal()
    session.add(User(id=UID, username="setter", password_hash="x"))
    session.commit()
    session.close()


def _trades(n=3):
    from src.tradelens.db.models import Trade
    from src.tradelens.db.session import SessionLocal

    session = SessionLocal()
    session.add_all(
        [
            Trade(
                user_id=UID,
                trade_date=f"2026-06-{10 + i:02d}",
                asset="NQ",
                direction="Long",
                result="Win",
                pnl=100.0 * (i + 1),
            )
            for i in range(n)
        ]
    )
    session.commit()
    session.close()


def _trade_count():
    from src.tradelens.services.trade_service import get_trades

    return len(get_trades(user_id=UID))


def _app(root: str, **state):
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file(f"{root}/{PAGE}", default_timeout=90)
    at.session_state["authenticated"] = True
    at.session_state["current_user_id"] = UID
    for key, value in state.items():
        at.session_state[key] = value
    return at.run()


def _button(at, fragment: str):
    for button in at.button:
        if fragment in button.label:
            return button
    return None


def _field(at, label: str):
    for widget in at.text_input:
        if widget.label == label:
            return widget
    return None


def _rendered(at) -> str:
    return "\n".join([m.value for m in at.markdown] + [c.value for c in at.caption])


def _fail(message: str) -> int:
    print(message, file=sys.stderr)
    return 1


def scenario_timezone_saves_and_reports_in_place(root: str) -> int:
    """Changing a preference persists it and says so beside the control."""
    _account()
    from src.tradelens.services.app_settings import get_timezone

    at = _app(root)
    if at.exception:
        return _fail(f"initial run raised: {at.exception}")

    picker = next((s for s in at.selectbox if s.label == "Trading timezone"), None)
    if picker is None:
        return _fail("no timezone control")
    if get_timezone(UID) == "Asia/Tokyo":
        return _fail("fixture already had the target timezone")

    at = picker.select("Asia/Tokyo").run()
    if at.exception:
        return _fail(f"changing the timezone raised: {at.exception}")
    if get_timezone(UID) != "Asia/Tokyo":
        return _fail(f"timezone did not persist: {get_timezone(UID)!r}")

    page = _rendered(at)
    if "Trading timezone saved" not in page:
        return _fail("no inline confirmation")
    if 'class="tl-setting-status ok"' not in page:
        return _fail("the confirmation did not use the shared status treatment")
    if 'role="status"' not in page:
        return _fail("the confirmation was not announced")
    print("OK")
    return 0


def scenario_sample_data_loads_and_clears(root: str) -> int:
    """Both sample-data actions run, report, and leave real trades alone."""
    _account()
    _trades(2)
    from src.tradelens.services.sample_data import count_sample_trades

    real_before = _trade_count()

    at = _app(root)
    load = _button(at, "Load sample trades")
    if load is None:
        return _fail("no load-samples button")
    at = load.click().run()
    if at.exception:
        return _fail(f"loading samples raised: {at.exception}")

    loaded = count_sample_trades(UID)
    if loaded <= 0:
        return _fail("no sample trades were loaded")
    if "Loaded" not in _rendered(at):
        return _fail("loading samples did not report inline")

    clear = _button(at, "Clear sample trades")
    if clear is None:
        return _fail("no clear-samples button")
    if clear.disabled:
        return _fail("clear stayed disabled with samples present")
    at = clear.click().run()
    if at.exception:
        return _fail(f"clearing samples raised: {at.exception}")

    if count_sample_trades(UID) != 0:
        return _fail("sample trades survived the clear")
    if "Removed" not in _rendered(at):
        return _fail("clearing samples did not report inline")
    if _trade_count() != real_before:
        return _fail(
            f"clearing samples touched real trades: {real_before} -> {_trade_count()}"
        )
    print("OK")
    return 0


def _other_account(other_uid=2, marker="OTHERUSER"):
    """A second account with its own trades, to catch an unscoped query."""
    from src.tradelens.db.models import Trade, User
    from src.tradelens.db.session import SessionLocal

    session = SessionLocal()
    session.add(User(id=other_uid, username="someone-else", password_hash="x"))
    session.add_all(
        [
            Trade(
                user_id=other_uid,
                trade_date=f"2026-05-{10 + i:02d}",
                asset=marker,
                direction="Short",
                result="Loss",
                pnl=-50.0,
                notes=marker,
            )
            for i in range(4)
        ]
    )
    session.commit()
    session.close()
    return other_uid


def scenario_export_supplies_only_the_signed_in_users_rows(root: str) -> int:
    """Capture the bytes the PAGE hands to the download control.

    Recreating the same CSV in the test and asserting on that proves the
    service works, not the page: an export wired to an unscoped query would
    pass. So export_trades_csv is wrapped before the page imports it, and
    what the page passes through is what gets inspected.
    """
    _account()
    _trades(3)
    other_uid = _other_account()

    from src.tradelens.services import csvio

    real_export = csvio.export_trades_csv
    captured = {}

    def _capturing_export(df):
        payload = real_export(df)
        captured["frame"] = df
        captured["bytes"] = payload
        return payload

    csvio.export_trades_csv = _capturing_export
    try:
        at = _app(root)
        if at.exception:
            return _fail(f"initial run raised: {at.exception}")
        labels = [b.label for b in at.get("download_button")]
        if not labels:
            return _fail("no export control")
    finally:
        csvio.export_trades_csv = real_export

    if "bytes" not in captured:
        return _fail("the page never produced an export payload")

    # The payload is checked BEFORE the label, so an unscoped export fails
    # on the leak itself rather than on a row count that merely disagrees.
    text = captured["bytes"].decode("utf-8")
    lines = [line for line in text.splitlines() if line.strip()]
    header, rows = lines[0], lines[1:]
    if "OTHERUSER" in text:
        return _fail("the export payload contained another account's trades")
    for column in ("trade_date", "asset", "pnl"):
        if column not in header:
            return _fail(f"export header is missing {column}")
    if len(rows) != 3:
        return _fail(f"the page supplied {len(rows)} rows, expected 3")
    if "Export 3 trades as CSV" not in labels:
        return _fail(f"export does not state the row count: {labels}")

    frame = captured["frame"]
    if "user_id" in getattr(frame, "columns", []):
        owners = set(frame["user_id"].dropna().unique().tolist())
        if owners - {UID}:
            return _fail(f"the exported frame spans users {owners}")

    from src.tradelens.services.trade_service import get_trades

    if len(get_trades(user_id=other_uid)) != 4:
        return _fail("the other account's trades were disturbed")
    print("OK")
    return 0


def scenario_account_deletion_completes(root: str) -> int:
    """The full destructive path, end to end.

    Locked for the wrong phrase and a near miss, unlocked by the exact one,
    and afterwards: no UI exception, the row gone, the session cleared, and
    a second account untouched.
    """
    _account()
    _trades(3)
    other_uid = _other_account()

    from src.tradelens.services.trade_service import get_trades
    from src.tradelens.services.users import get_user_by_id

    at = _app(root)
    if at.exception:
        return _fail(f"initial run raised: {at.exception}")

    button = _button(at, "Delete my account permanently")
    if button is None:
        return _fail("no account-deletion control")
    if not button.disabled:
        return _fail("account deletion was enabled before confirmation")

    field_label = "Type DELETE MY ACCOUNT to confirm"
    for wrong in ("DELETE", "delete my account", "DELETE MY ACCOUNT!"):
        at = _field(at, field_label).set_value(wrong).run()
        if not _button(at, "Delete my account permanently").disabled:
            return _fail(f"{wrong!r} unlocked account deletion")
    if get_user_by_id(UID) is None:
        return _fail("the account vanished during the locked attempts")

    at = _field(at, field_label).set_value("DELETE MY ACCOUNT").run()
    button = _button(at, "Delete my account permanently")
    if button.disabled:
        return _fail("the exact phrase did not unlock account deletion")

    at = button.click().run()
    if at.exception:
        return _fail(f"deleting the account raised: {at.exception}")

    if get_user_by_id(UID) is not None:
        return _fail("the account row survived deletion")
    if get_trades(user_id=UID):
        return _fail("the account's trades survived deletion")

    # The session must not still point at a row that no longer exists.
    if "authenticated" in at.session_state and at.session_state["authenticated"]:
        return _fail("the session is still authenticated after deletion")
    if (
        "current_user_id" in at.session_state
        and at.session_state["current_user_id"] is not None
    ):
        return _fail("current_user_id still points at the deleted account")

    # …and the neighbour is untouched.
    if get_user_by_id(other_uid) is None:
        return _fail("deleting one account removed another")
    if len(get_trades(user_id=other_uid)) != 4:
        return _fail("deleting one account removed another's trades")
    print("OK")
    return 0


def scenario_csv_import_failure_leaks_nothing(root: str) -> int:
    """A row insert fails with a credential-bearing driver message.

    The page renders whatever import_trades_csv puts in `errors`, so the
    service is the boundary: it must log the exception and return a fixed
    sentence that keeps the row number and nothing else.
    """
    _account()

    leaky = (
        "(psycopg2.OperationalError) FATAL: password authentication failed\n"
        "[SQL: INSERT INTO trades (user_id, asset) VALUES (%(user_id)s, %(asset)s)]\n"
        "postgresql://tl_admin:pr0d-p4ssw0rd-9f3a@db.internal:5432/tradelens"
    )
    secrets = (
        "tl_admin",
        "pr0d-p4ssw0rd-9f3a",
        "db.internal",
        "postgresql://",
        "psycopg2",
        "INSERT INTO",
        "OperationalError",
        "Traceback",
    )

    from src.tradelens.services import csvio

    real_create = csvio.create_trade

    def _explode(*_args, **_kwargs):
        raise RuntimeError(leaky)

    csvio.create_trade = _explode
    try:
        import io as _io

        csv_text = (
            "trade_date,asset,direction,result,pnl\n"
            "2026-06-15,NQ,Long,Win,100\n"
            "2026-06-16,ES,Short,Loss,-40\n"
        )
        inserted, skipped, errors = csvio.import_trades_csv(
            _io.BytesIO(csv_text.encode("utf-8")), user_id=UID
        )
    finally:
        csvio.create_trade = real_create

    if inserted != 0:
        return _fail("rows were inserted despite the failure")
    if len(errors) != 2:
        return _fail(f"expected one error per row, got {errors}")
    joined = "\n".join(errors)
    for secret in secrets:
        if secret in joined:
            return _fail(f"the import error leaked {secret!r}")
    # …and it still says which rows failed, which is the actionable part.
    if "Row 2" not in joined or "Row 3" not in joined:
        return _fail(f"the error lost the row numbers: {errors}")

    # A malformed file takes the other path — same rule.
    bad = _io.BytesIO(b"\x00\x01\x02not,a,csv\x00")

    class _Boom:
        def read(self_inner):
            raise RuntimeError(leaky)

    inserted, skipped, errors = csvio.import_trades_csv(_Boom(), user_id=UID)
    joined = "\n".join(errors)
    for secret in secrets:
        if secret in joined:
            return _fail(f"the parse error leaked {secret!r}")
    if not errors:
        return _fail("an unreadable file produced no error at all")
    del bad
    print("OK")
    return 0


def scenario_destructive_actions_are_gated(root: str) -> int:
    """The confirmation must GATE, not merely appear.

    A disabled-looking button that still fires is worse than no gate: it
    reads as protection. Both actions are checked with the wrong text, with
    nearly-right text, and then with the exact phrase.
    """
    _account()
    _trades(4)

    at = _app(root)
    if at.exception:
        return _fail(f"initial run raised: {at.exception}")

    delete_trades = _button(at, "Delete all trades permanently")
    delete_account = _button(at, "Delete my account permanently")
    if delete_trades is None or delete_account is None:
        return _fail("a destructive control is missing")
    if not delete_trades.disabled or not delete_account.disabled:
        return _fail("a destructive control was enabled before confirmation")

    # Near-miss text must not unlock it.
    field = _field(at, "Type DELETE to confirm")
    if field is None:
        return _fail("no trade-deletion confirmation field")
    at = field.set_value("delete").run()
    if not _button(at, "Delete all trades permanently").disabled:
        return _fail("lowercase 'delete' unlocked the destructive action")
    if _trade_count() != 4:
        return _fail("trades disappeared without confirmation")

    at = _field(at, "Type DELETE to confirm").set_value("DELETE").run()
    button = _button(at, "Delete all trades permanently")
    if button.disabled:
        return _fail("the exact phrase did not unlock the action")
    at = button.click().run()
    if at.exception:
        return _fail(f"deleting all trades raised: {at.exception}")
    if _trade_count() != 0:
        return _fail(f"{_trade_count()} trades survived the confirmed delete")
    if "Deleted 4 trades" not in _rendered(at):
        return _fail("the deletion did not report what it removed")

    # The account gate is a separate, longer phrase; the trade phrase must
    # not open it.
    at = _field(at, "Type DELETE MY ACCOUNT to confirm").set_value("DELETE").run()
    if not _button(at, "Delete my account permanently").disabled:
        return _fail("the trade confirmation unlocked account deletion")

    from src.tradelens.services.users import get_user_by_id

    if get_user_by_id(UID) is None:
        return _fail("the account was deleted without its own confirmation")
    print("OK")
    return 0


_SCENARIOS = {
    "timezone_saves_and_reports_in_place": scenario_timezone_saves_and_reports_in_place,
    "sample_data_loads_and_clears": scenario_sample_data_loads_and_clears,
    "export_supplies_only_the_signed_in_users_rows": (
        scenario_export_supplies_only_the_signed_in_users_rows
    ),
    "account_deletion_completes": scenario_account_deletion_completes,
    "csv_import_failure_leaks_nothing": scenario_csv_import_failure_leaks_nothing,
    "destructive_actions_are_gated": scenario_destructive_actions_are_gated,
}


def main() -> int:
    root, scenario = sys.argv[1:3]
    sys.path.insert(0, root)

    try:
        import streamlit as st

        st.secrets._secrets = {}
    except Exception:  # noqa: BLE001 — must run even if this internal changes
        pass

    from src.tradelens.db.init_db import init_db

    init_db()
    return _SCENARIOS[scenario](root)


if __name__ == "__main__":
    sys.exit(main())
