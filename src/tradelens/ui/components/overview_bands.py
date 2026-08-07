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
    compute_basic_metrics,
    compute_equity_curve,
    compute_max_drawdown,
    compute_streaks,
    consistency_score,
    edge_leak_summary,
    rule_adherence_rate,
)
from src.tradelens.services.activation import NEXT_STEP_COPY
from src.tradelens.services.sessions import KILLZONE_LABELS
from src.tradelens.ui.components.data_state import (
    MIN_DATED_POINTS,
    leading_category,
    sample_state,
    show_dated_instrument,
)
from src.tradelens.ui.components.workspace import EvidenceItem


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


@dataclass(frozen=True)
class RankedRow:
    """One row of a ranked performance list. Values arrive pre-formatted.

    ``sample`` is per row, not per list: a session with fourteen trades and one
    with two do not deserve the same weight in a reader's head, and the only
    way to say so is to put both counts on the page.
    """

    label: str
    value: str
    sample: str


def render_ranked_list(title: str, rows: Sequence[RankedRow], *, rankable: bool) -> str:
    """Band 4: what repeats, as a ranked list rather than a pie.

    Ranked lists, not pie charts — a trader comparing session P&L needs to read
    magnitudes, not compare silhouettes. A radar was considered and rejected for
    the same reason: its own guidance sends precise comparison to a bar.

    ``rankable=False`` suppresses every ordinal marker. The caller passes
    ``not leading.is_only_category``, because with one category present nothing
    may be called strongest or weakest — a single bar proves nothing, and
    dressing it as a finding is the trust failure the 2026-07-21 audit scored
    4.5/10.
    """
    if not rows:
        return ""

    items = []
    for index, row in enumerate(rows, start=1):
        rank = f' data-rank="{index}"' if rankable else ""
        items.append(
            f'<li class="tl-ranked-row"{rank}>'
            f'<span class="tl-ranked-label">{escape(str(row.label))}</span>'
            f'<span class="tl-ranked-value">{escape(str(row.value))}</span>'
            f'<span class="tl-ranked-sample">{escape(str(row.sample))}</span>'
            "</li>"
        )
    return (
        '<div class="tl-ranked">'
        # h3, not h4: this sits under the band's own h2, and a skipped level
        # is a screen reader announcing a section that is not there.
        # Every style comes from the class, so the level is free.
        f'<h3 class="tl-ranked-title">{escape(str(title))}</h3>'
        f'<ol class="tl-ranked-rows">{"".join(items)}</ol>'
        "</div>"
    )


@dataclass(frozen=True)
class FlankFigure:
    """One figure beside the equity curve. Pre-formatted, like the rest."""

    label: str
    value: str
    detail: str


def render_flanking_figures(figures: Sequence[FlankFigure]) -> str:
    """Band 3's supporting form: a quiet vertical stack beside the chart.

    Not a KPI strip and not the discipline panel — those are bands 1 and 2, and
    reusing either here would collapse three bands into one rhythm. These
    describe the SHAPE of the sequence the curve draws rather than restating
    band 1's totals, which is why streaks and averages live here and net P&L
    does not.
    """
    if not figures:
        return ""
    rows = "".join(
        '<div class="tl-flank-row">'
        f'<span class="tl-flank-label">{escape(str(f.label))}</span>'
        f'<span class="tl-flank-value">{escape(str(f.value))}</span>'
        f'<span class="tl-flank-detail">{escape(str(f.detail))}</span>'
        "</div>"
        for f in figures
    )
    return f'<div class="tl-flank">{rows}</div>'


def trajectory_figures(df) -> List[FlankFigure]:
    """Band 3: how did this standing come about?

    Streaks carry their own word — "winning" / "losing" — so the meaning does
    not depend on a colour a reader may not perceive.

    Average win and average loss return 0.0 from the service when there are no
    wins or no losses (spec D10). A zero average win is not an average of zero;
    it is the absence of any win, and saying "$0.00" would report a result the
    trader never had.
    """
    if df is None or df.empty:
        return []

    streaks = compute_streaks(df)
    metrics = compute_basic_metrics(df)

    # current_streak is SIGNED: -1 means one loss, not minus one trade. The
    # magnitude is the run length and streak_type carries the direction, so
    # the word does the work a colour would otherwise have to.
    current = int(streaks.get("current_streak") or 0)
    kind = {"win": "winning", "loss": "losing"}.get(
        str(streaks.get("streak_type") or "").strip().lower(), ""
    )
    if current and kind:
        current_value = f"{abs(current)} {kind}"
        current_detail = "in a row, most recent first"
    else:
        current_value = "None"
        current_detail = "no run in progress"

    wins = int(metrics.get("wins") or 0)
    losses = int(metrics.get("losses") or 0)

    return [
        FlankFigure("Current streak", current_value, current_detail),
        FlankFigure(
            "Best run",
            f"{int(streaks.get('max_win_streak') or 0)} winning",
            f"longest losing run {int(streaks.get('max_loss_streak') or 0)}",
        ),
        FlankFigure(
            "Average win",
            money(metrics.get("avg_win")) if wins else "No wins yet",
            f"{wins} winning trade{'s' if wins != 1 else ''}",
        ),
        FlankFigure(
            "Average loss",
            money(metrics.get("avg_loss")) if losses else "No losses yet",
            f"{losses} losing trade{'s' if losses != 1 else ''}",
        ),
    ]


def ranked_rows(breakdown, *, label_column: str, labels=None) -> List[RankedRow]:
    """Turn a services breakdown frame into ranked rows, richest first.

    The breakdown decides the numbers; this only words them. Rows with no
    category label are dropped rather than rendered as a blank rank — an
    unlabelled row is a data gap, not a category.
    """
    if breakdown is None or getattr(breakdown, "empty", True):
        return []
    if label_column not in breakdown.columns or "total_pnl" not in breakdown.columns:
        return []

    frame = breakdown.copy()
    frame = frame[frame[label_column].notna()]
    frame = frame[frame[label_column].astype(str).str.strip() != ""]
    if frame.empty:
        return []

    frame = frame.sort_values("total_pnl", ascending=False)
    rows = []
    for _, row in frame.iterrows():
        count = int(row["trades"]) if "trades" in frame.columns else 0
        raw = str(row[label_column])
        # Stored keys are machine-shaped ("ny_am"). A trader reads sessions by
        # their names, so a caller may pass the same label map the ledger uses
        # rather than have two vocabularies for one dimension.
        label = (labels or {}).get(raw, raw)
        rows.append(RankedRow(label, money(row["total_pnl"]), f"n={count}"))
    return rows


@dataclass(frozen=True)
class NextReviewAction:
    """Band 5: the one thing to go and re-read. Never a trade action.

    Two of the Overview's older elements collapse into this — the activation
    next-step card and the period observation. Which one appears is a state
    question, not a layout question, so it is decided here rather than in the
    render path where it would be tangled with columns and headings.
    """

    kind: str  # "next_step" | "observation"
    title: str
    body: str
    progress: Optional[str] = None  # "{completed} of {total}", next_step only
    link_label: Optional[str] = None
    link_slug: Optional[str] = None
    evidence: Optional[EvidenceItem] = None  # observation only


def _period_observation(df) -> Optional[NextReviewAction]:
    """The editorial reading of the period, or None when it is not earned.

    ``leading_category`` decides what is TRUE — it returns None below the
    pattern threshold, because naming a leading session out of three trades
    describes noise. This only words the finding, and every claim carries its
    own sample, confidence and limitation so nothing has to be taken on trust.
    """
    leader = leading_category(df, "killzone")
    if leader is None:
        return None

    label = KILLZONE_LABELS.get(leader.key, leader.key.replace("_", " ").title())
    plural = "trade" if leader.count == 1 else "trades"

    if leader.overall_total > 0 and leader.share >= 0.5:
        body = (
            f"{label} carried most of this period's result: "
            f"{money(leader.total)} of {money(leader.overall_total)} net, "
            f"across {leader.count} {plural}. Re-read those entries before "
            "the next review."
        )
    else:
        body = (
            f"{label} recorded the strongest net result this period at "
            f"{money(leader.total)}, across {leader.count} {plural}. "
            "Re-read those entries before the next review."
        )

    return NextReviewAction(
        kind="observation",
        title="What this period recorded",
        body=body,
        evidence=EvidenceItem(
            evidence=f"{label} · {money(leader.total)} net",
            sample=f"n={leader.count} of {len(df)}",
            confidence=(
                "high"
                if leader.count >= 12
                else "medium" if leader.count >= 6 else "low"
            ),
            limitation=(
                "Only one session is represented, so this ranks nothing."
                if leader.is_only_category
                else None
            ),
        ),
    )


def next_review_action(df, activation) -> Optional[NextReviewAction]:
    """Band 5's payload, or None when the band is omitted entirely.

    An empty band is worse than no band: a heading over nothing asks the reader
    to work out what is missing (spec 5.6).

    Activation outranks the observation. A trader who has not finished setting
    up does not need a pattern read; they need the next setup step. The
    activation service exposes `is_activated` / `next_key` / `completed` /
    `total` — not the nested step object the plan sketched — so the caller
    adapts and the service is left alone.
    """
    if activation is not None and not activation.is_activated:
        heading, slug, link_label = NEXT_STEP_COPY.get(
            activation.next_key, ("Keep going", "/", "Continue")
        )
        return NextReviewAction(
            kind="next_step",
            title=heading,
            body=(
                "One step, not a checklist — this is what unlocks the next "
                "useful review."
            ),
            progress=f"{activation.completed} of {activation.total}",
            link_label=link_label,
            link_slug=slug,
        )

    return _period_observation(df)
