"""Autofill markup pre-check policy, shared by the Streamlit app and services.

This is the confidence rule that decides whether a detected-markup checkbox
(entry/stop) starts pre-checked. It used to live only in
`ui/components/ai_autofill_review.py`, and `services/trade_autofill.py`
reached across the layer boundary to import it rather than duplicate it —
the right instinct (one confidence rule, not two copies that can drift), the
wrong direction. Reaching *up* from services into ui/components drags
Streamlit into any process that imports the service (the FastAPI container
included), which is exactly what "no Streamlit imports in services/" exists
to prevent.

The policy moves *down* instead: this module owns it, and the Streamlit
component re-exports it, the same pattern `services/sample_policy.py` uses
for the low-data policy at `ui/components/data_state.py`. Re-exporting keeps
every existing caller of the Streamlit component working unchanged while the
policy itself lives somewhere both services and pages can import it from
without either one importing Streamlit.
"""

from __future__ import annotations

# Entry/stop pre-check only when the model is confident; everything else
# opt-in. Kept here (not in trade_autofill.py) because this threshold is
# about the review UI's default checkbox state, not the autofill pipeline —
# the same reasoning that keeps display thresholds in sample_policy.py
# rather than in the pages that render them.
AUTOCHECK_FIELDS = ("entry_price", "stop_price")
AUTOCHECK_MIN_CONFIDENCE = 0.70


def should_autocheck(field: str, confidence) -> bool:
    """Default-checked state for a detected-markup checkbox.

    Only entry/stop auto-check, and only at >= 0.70 confidence — below that the
    trader must opt in explicitly. Junk/missing confidence never auto-checks.
    """
    if field not in AUTOCHECK_FIELDS:
        return False
    try:
        return float(confidence) >= AUTOCHECK_MIN_CONFIDENCE
    except (TypeError, ValueError):
        return False
