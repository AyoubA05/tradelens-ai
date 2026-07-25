"""Subprocess helper: drive the account UI under AppTest with an isolated DB.

Run in a child process (no test_ prefix, so pytest does not collect it) for
the same reason as app_boot_check.py: reloading src.tradelens mid-suite
creates a second copy of the package and breaks isinstance checks in other
test files. See that module's warning before changing this.

Usage:
    DATABASE_URL=sqlite:///<tmp> python account_ui_check.py <root> <scenario>

Exits 0 on success, non-zero with a message on failure.
"""

import os
import sys


def _fail(message: str) -> int:
    print(message, file=sys.stderr)
    return 2


def main() -> int:
    root, scenario = sys.argv[1:3]
    sys.path.insert(0, root)

    import streamlit as st

    st.secrets._secrets = {}  # ignore a developer's real secrets file

    from src.tradelens.db.init_db import init_db

    init_db()

    from src.tradelens.services.users import create_user, get_user_by_id, set_email

    user = create_user("trader", "OriginalPass!1")

    from streamlit.testing.v1 import AppTest

    if scenario == "reset-panel":
        app = os.path.join(root, "src", "tradelens", "ui", "app.py")
        at = AppTest.from_file(app).run()
        if at.exception:
            return _fail(f"auth screen raised: {at.exception}")

        # The reset panel lives in a disclosure under the sign-in form, so
        # its fields are part of the same render — nothing is swapped out.
        labels = [i.label for i in at.text_input]
        if not any("Reset code" in label for label in labels):
            return _fail(f"no reset-code field on the sign-in screen: {labels}")
        if not any("Email address" in label for label in labels):
            return _fail("reset panel does not ask for an email address")

        # The token must never be rendered on screen.
        rendered = " ".join(m.value for m in at.markdown)
        if "code:" in rendered:
            return _fail("a reset token was rendered in the UI")

        if not any("Set new password" in b.label for b in at.button):
            return _fail("reset panel has no way to submit a new code")
        print("OK")
        return 0

    if scenario in {"settings-email", "settings-delete"}:
        page = os.path.join(root, "src", "tradelens", "ui", "pages", "9_Settings.py")
        at = AppTest.from_file(page)
        at.session_state["authenticated"] = True
        at.session_state["current_user"] = "trader"
        at.session_state["current_user_id"] = user.id
        at = at.run()
        if at.exception:
            return _fail(f"settings raised: {at.exception}")

        if scenario == "settings-email":
            fields = [i for i in at.text_input if "Email address" in i.label]
            if not fields:
                return _fail("no email field on Settings")
            fields[0].set_value("Trader@Example.COM")
            save = [b for b in at.button if b.key == "settings_email_save"]
            if not save:
                return _fail("no save-email control")
            save[0].click().run()
            stored = get_user_by_id(user.id).email
            if stored != "trader@example.com":
                return _fail(f"email not stored normalised: {stored!r}")
            print("OK")
            return 0

        # settings-delete: the control exists and is gated behind the phrase.
        confirms = [i for i in at.text_input if "DELETE MY ACCOUNT" in i.label]
        if not confirms:
            return _fail("no account-deletion confirmation field")
        buttons = [b for b in at.button if b.key == "secondary_delete_account"]
        if not buttons:
            return _fail("no account-deletion control")
        if not buttons[0].disabled:
            return _fail("deletion control is enabled before the phrase is typed")

        set_email(user.id, "trader@example.com")
        print("OK")
        return 0

    return _fail(f"unknown scenario: {scenario}")


if __name__ == "__main__":
    sys.exit(main())
