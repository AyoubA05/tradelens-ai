"""
Sidebar component: correction-memory badge + repeat-threshold suggestion.

Render-only. Shows how many corrections the AI has learned, and when the trader
has repeated the same correction enough times, fires a toast and offers a
one-click promotion of that correction into the Strategy Profile.
"""

import streamlit as st

from src.tradelens.services.corrections import count_corrections, repeated_corrections
from src.tradelens.services.strategy import append_insight

_REPEAT_THRESHOLD = 5


def render_corrections_sidebar() -> None:
    """Render the 'AI has learned N corrections' badge + repeat suggestions."""
    count = count_corrections()

    with st.sidebar:
        st.markdown("---")
        if count == 0:
            st.caption("🧠 The AI hasn't learned any corrections from you yet.")
            return
        plural = "s" if count != 1 else ""
        st.caption(f"🧠 The AI has learned **{count}** correction{plural} from you.")

        repeats = repeated_corrections(threshold=_REPEAT_THRESHOLD)
        if not repeats:
            return

        # Toast each new repeated correction once per session (toasts can't hold widgets).
        shown = st.session_state.setdefault("_corr_toasts_shown", set())
        for r in repeats:
            key = (r["field"], r["user_value"])
            if key not in shown:
                st.toast(
                    f"You've corrected {r['field']} → {r['user_value']!r} "
                    f"{r['count']}× — add it to your Strategy Profile?",
                    icon="💡",
                )
                shown.add(key)

        st.markdown("**Repeated corrections**")
        for i, r in enumerate(repeats):
            rule = (
                f"{r['field']}: prefer {r['user_value']} "
                f"(corrected {r['count']}x in review)"
            )
            label = f"➕ Add '{r['user_value']}' to Strategy Profile"
            if st.button(label, key=f"corr_apply_{i}", width="stretch"):
                append_insight(rule)
                st.success("Added to your Strategy Profile (risk rules).")
