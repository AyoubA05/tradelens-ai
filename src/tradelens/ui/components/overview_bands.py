"""Forms for the Overview's five bands.

Pure and Streamlit-free, like ``workspace.py``: every builder escapes its
caller's values, emits one root element, and takes pre-formatted strings so no
presentation helper silently re-rounds a number a trader is reading.

The Overview is a fixed editorial composition, not a widget surface, and the
anti-grid rule is structural rather than stylistic: **each band takes a
different visual form.** Five bands, five forms. A trader's eye cannot get lost
in a rhythm of identical tiles because there is no such rhythm — which is why
the discipline panel here is deliberately not another KPI strip.
"""

from __future__ import annotations

from dataclasses import dataclass
from html import escape
from typing import List, Optional, Sequence

import pandas as pd

from src.tradelens.services.metrics import (
    _MIN_TRADES_FOR_CONSISTENCY,
    compute_equity_curve,
    compute_max_drawdown,
    consistency_score,
    edge_leak_summary,
    rule_adherence_rate,
)
from src.tradelens.ui.components.data_state import (
    MIN_DATED_POINTS,
    sample_state,
    show_dated_instrument,
)


def money(value) -> str:
    """Signed currency, or N/A. Never '--', never a bare 0 for missing.

    Mirrors app.py's formatter deliberately: this module must stay importable
    without booting a Streamlit page, and app.py runs its whole page at module
    scope. One shared helper would mean importing the page to format a number.
    """
    if value is None or pd.isna(value):
        return "N/A"
    value = float(value)
    return f"{'-' if value < 0 else ''}${abs(value):,.2f}"


@dataclass(frozen=True)
class DisciplineMeasure:
    """One row of the discipline panel. Values arrive pre-formatted.

    ``sample`` is not optional and never blank. A rate over an unstated sample
    reads as certainty the journal has not earned, and handoff §2 requires the
    numerator and denominator beside the percentage so a small sample cannot be
    mistaken for a settled fact.

    ``note`` carries the one sentence a figure needs when its sign is
    misleading — a positive edge leak being the case that matters.
    """

    label: str
    value: str
    sample: str
    note: Optional[str] = None


def render_discipline_panel(measures: Sequence[DisciplineMeasure]) -> str:
    """Band 2: figure-and-sample pairs on one ruled panel.

    Not a KPI strip and not four cards. The inline sample under each figure is
    what makes this band read differently from band 1 above it, and it is also
    the honest part: these four measures are the ones most easily overstated on
    a thin sample.

    Returns "" for no measures. An empty panel is worse than no panel — it
    leaves a titled box asking the reader to work out what is missing.
    """
    if not measures:
        return ""

    rows = []
    for measure in measures:
        note = (
            f'<p class="tl-discipline-note">{escape(str(measure.note))}</p>'
            if measure.note
            else ""
        )
        rows.append(
            '<div class="tl-discipline-row">'
            f'<span class="tl-discipline-label">{escape(str(measure.label))}</span>'
            f'<span class="tl-discipline-value">{escape(str(measure.value))}</span>'
            f'<span class="tl-discipline-sample">{escape(str(measure.sample))}</span>'
            f"{note}"
            "</div>"
        )
    return '<div class="tl-discipline">' + "".join(rows) + "</div>"


def discipline_measures(df) -> List[DisciplineMeasure]:
    """Band 2: can this standing be trusted?

    Band 1 says where a trader stands. This says whether the number deserves
    belief — drawdown, whether the plan was followed, what breaking it cost,
    and how steady the process has been.

    Every measure states its own sample, and every one of the four has a way
    of being unknown that is NOT zero. That distinction is the whole point of
    the band: a 0% adherence over nothing recorded, and a genuine 0% over
    forty trades, are opposite facts that used to render identically.

    No measure carries a tone. Adherence and consistency are process, and
    red/green belongs to money (spec 5.3).
    """
    trades = 0 if df is None or df.empty else len(df)

    # Drawdown. compute_max_drawdown returns a positive MAGNITUDE by
    # documented contract, which on this panel would sit unsigned beside a
    # positive edge leak and read as money made. It is money lost from a peak,
    # so presentation signs it; the service is unchanged and still owns the
    # number. Pinned by test_max_drawdown_is_displayed_as_money_lost.
    magnitude = compute_max_drawdown(compute_equity_curve(df)) if trades else 0.0
    drawdown = -magnitude if magnitude else 0.0
    state = sample_state(df)
    drawdown_sample = (
        f"n={trades}"
        if show_dated_instrument(state)
        else f"{state.dated_points} of {MIN_DATED_POINTS} trading days"
    )

    # Rule adherence — Codex-owned. `rate is None` means nothing was recorded,
    # which is not the same as nobody following their rules.
    adherence = rule_adherence_rate(df)
    if adherence.rate is None:
        adherence_value = "Not recorded"
        adherence_sample = "no trade has a rules answer yet"
    else:
        adherence_value = f"{adherence.rate * 100:.0f}%"
        adherence_sample = f"{adherence.followed} of {adherence.recorded}"

    # Edge leak — three states, and they must read as three (spec D10).
    leak = edge_leak_summary(df)
    leak_note = None
    if leak.net_pnl is None:
        leak_value = "Not recorded"
        leak_sample = "needs a rules answer or a mistake tag"
    elif leak.qualifying_trades == 0:
        leak_value = money(0.0)
        leak_sample = f"no rule-breaking in {leak.recorded_trades} recorded"
    else:
        leak_value = money(leak.net_pnl)
        leak_sample = f"{leak.qualifying_trades} of {leak.recorded_trades} recorded"
        if leak.net_pnl > 0:
            # The case that matters. Breaking the plan and profiting is the
            # most dangerous number on the page, because it looks like a win.
            leak_note = (
                "Breaking your rules made money here. That is luck, "
                "not repeatable — read it as a warning, not a result."
            )

    # Consistency — withheld below its own sample floor, saying what unlocks it.
    if trades >= _MIN_TRADES_FOR_CONSISTENCY:
        consistency_value = f"{consistency_score(df):.0f}"
        consistency_sample = f"n={trades}"
    else:
        consistency_value = "Not yet"
        needed = _MIN_TRADES_FOR_CONSISTENCY - trades
        consistency_sample = (
            f"{needed} more trade{'s' if needed != 1 else ''} to score it"
        )

    return [
        DisciplineMeasure("Max drawdown", money(drawdown), drawdown_sample),
        DisciplineMeasure("Rule adherence", adherence_value, adherence_sample),
        DisciplineMeasure("Edge leak", leak_value, leak_sample, note=leak_note),
        DisciplineMeasure("Consistency", consistency_value, consistency_sample),
    ]
