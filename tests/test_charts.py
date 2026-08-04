"""
Render tests for every Plotly chart (Phase 5, week6-d5, flow-pass §d).

Each chart must return a plotly Figure on populated input AND on empty input,
never raising. Inputs are produced through the real metrics pipeline so the
shapes match what the pages pass.
"""

import pandas as pd
import plotly.graph_objects as go

from src.tradelens.services.demo import get_demo_df
from src.tradelens.services.metrics import (
    by_day_of_week,
    by_session,
    by_setup_type,
    by_strategy,
    calendar_daily_pnl,
    compute_breakdown,
    compute_profit_factor_raw,
    drawdown_series,
    emotion_vs_rr,
    equity_curve_series,
    r_multiple_distribution,
)
from src.tradelens.ui.components.charts import (
    calendar_heatmap_chart,
    drawdown_chart,
    emotion_vs_rr_chart,
    equity_curve_chart,
    pnl_by_dow_chart,
    pnl_by_emotion_chart,
    pnl_by_session_chart,
    pnl_by_strategy_chart,
    profit_factor_gauge,
    r_multiple_histogram,
    risk_over_time_chart,
    session_dow_heatmap,
    setup_breakdown_chart,
    win_rate_by_dow_chart,
    win_rate_rules_chart,
)

_DF = get_demo_df()
_EMPTY = pd.DataFrame()


def _is_fig(obj):
    assert isinstance(obj, go.Figure)


# --- Populated inputs ---------------------------------------------------------


def test_equity_curve_chart_renders():
    _is_fig(equity_curve_chart(equity_curve_series(_DF)))


def test_drawdown_chart_renders():
    _is_fig(drawdown_chart(drawdown_series(_DF)))


def test_win_rate_by_dow_chart_renders():
    _is_fig(win_rate_by_dow_chart(by_day_of_week(_DF)))


def test_pnl_by_strategy_chart_renders():
    _is_fig(pnl_by_strategy_chart(by_strategy(_DF)))


def test_profit_factor_gauge_renders():
    _is_fig(profit_factor_gauge(compute_profit_factor_raw(_DF)))


def test_profit_factor_gauge_handles_inf():
    _is_fig(profit_factor_gauge(float("inf")))


def test_r_multiple_histogram_renders():
    _is_fig(r_multiple_histogram(r_multiple_distribution(_DF), median_rr=1.5))


def test_emotion_vs_rr_chart_renders():
    _is_fig(emotion_vs_rr_chart(emotion_vs_rr(_DF)))


def test_setup_breakdown_chart_renders():
    _is_fig(setup_breakdown_chart(by_setup_type(_DF)))


def test_calendar_heatmap_chart_renders():
    _is_fig(calendar_heatmap_chart(calendar_daily_pnl(_DF, 2026, 6), 2026, 6))


# --- Part 4 Analytics-redesign charts -----------------------------------------


def test_pnl_by_session_chart_renders():
    _is_fig(pnl_by_session_chart(by_session(_DF)))


def test_pnl_by_dow_chart_renders():
    _is_fig(pnl_by_dow_chart(by_day_of_week(_DF)))


def test_pnl_by_emotion_chart_renders():
    _is_fig(pnl_by_emotion_chart(compute_breakdown(_DF, "emotions_before")))


def test_risk_over_time_chart_renders():
    _is_fig(risk_over_time_chart(_DF))


def test_win_rate_rules_chart_renders():
    _is_fig(win_rate_rules_chart(0.62, 0.31, 40, 12))


def test_session_dow_heatmap_renders():
    _is_fig(session_dow_heatmap(_DF))


# --- Empty inputs (designed empty figure, never an exception) ------------------


def test_all_charts_handle_empty_input():
    _is_fig(equity_curve_chart(_EMPTY))
    _is_fig(drawdown_chart(_EMPTY))
    _is_fig(win_rate_by_dow_chart(_EMPTY))
    _is_fig(pnl_by_strategy_chart(_EMPTY))
    _is_fig(profit_factor_gauge(0.0))
    _is_fig(r_multiple_histogram(_EMPTY, median_rr=None))
    _is_fig(emotion_vs_rr_chart(_EMPTY))
    _is_fig(setup_breakdown_chart(_EMPTY))
    _is_fig(calendar_heatmap_chart(calendar_daily_pnl(_EMPTY, 2026, 1), 2026, 1))
    _is_fig(pnl_by_session_chart(_EMPTY))
    _is_fig(pnl_by_dow_chart(_EMPTY))
    _is_fig(pnl_by_emotion_chart(_EMPTY))
    _is_fig(risk_over_time_chart(_EMPTY))
    _is_fig(session_dow_heatmap(_EMPTY))


# ---------------------------------------------------------------------------
# Chart stage — one framing applied to every figure (Task 6).
# ---------------------------------------------------------------------------


def test_apply_chart_stage_paints_the_dark_stage():
    """One helper owns the instrument framing, so a new chart cannot ship
    with different margins, a different background, or light-surface text."""
    from src.tradelens.ui import design_system as ds
    from src.tradelens.ui.components.charts import apply_chart_stage

    fig = apply_chart_stage(go.Figure())
    assert fig.layout.paper_bgcolor == ds.TL_SURFACE_CHART
    assert fig.layout.plot_bgcolor == ds.TL_SURFACE_CHART
    assert fig.layout.font.color == ds.TL_CONTENT_PRIMARY


def test_apply_chart_stage_returns_the_same_figure():
    from src.tradelens.ui.components.charts import apply_chart_stage

    fig = go.Figure()
    assert apply_chart_stage(fig) is fig


def test_apply_chart_stage_sets_a_title_when_asked():
    from src.tradelens.ui.components.charts import apply_chart_stage

    fig = apply_chart_stage(go.Figure(), title="Equity curve")
    assert fig.layout.title.text == "Equity curve"
    # …and leaves it alone otherwise
    assert apply_chart_stage(go.Figure()).layout.title.text is None


def test_compact_stage_is_shorter_than_the_dominant_one():
    """A supporting chart must not claim the same room as the instrument
    the panel is built around."""
    from src.tradelens.ui.components.charts import apply_chart_stage

    dominant = apply_chart_stage(go.Figure())
    compact = apply_chart_stage(go.Figure(), compact=True)
    assert compact.layout.height < dominant.layout.height


def test_apply_chart_stage_keeps_axis_labels_off_the_stage_edge():
    """automargin is what stops the stage's own edge clipping tick text."""
    from src.tradelens.ui.components.charts import apply_chart_stage

    fig = apply_chart_stage(go.Figure())
    assert fig.layout.xaxis.automargin is True
    assert fig.layout.yaxis.automargin is True


# ---------------------------------------------------------------------------
# Sample annotation — the panel says what it is drawn from.
# ---------------------------------------------------------------------------


def test_add_sample_annotation_states_the_sample():
    from src.tradelens.ui.components.charts import add_sample_annotation

    fig = add_sample_annotation(go.Figure(), sample_size=21, minimum=5)
    texts = [a.text for a in fig.layout.annotations]
    assert any("21" in t for t in texts)


def test_add_sample_annotation_flags_a_thin_sample():
    """Below the threshold the chart must say so on its own face — a reader
    who scrolled straight to it never saw the panel's caveat."""
    from src.tradelens.ui.components.charts import add_sample_annotation

    thin = add_sample_annotation(go.Figure(), sample_size=3, minimum=5)
    text = " ".join(a.text for a in thin.layout.annotations).lower()
    assert "3" in text
    assert "small" in text or "limited" in text or "thin" in text


def test_add_sample_annotation_is_quiet_when_the_sample_is_adequate():
    from src.tradelens.ui.components.charts import add_sample_annotation

    ok = add_sample_annotation(go.Figure(), sample_size=40, minimum=5)
    text = " ".join(a.text for a in ok.layout.annotations).lower()
    assert "small" not in text


def test_add_sample_annotation_returns_the_same_figure():
    from src.tradelens.ui.components.charts import add_sample_annotation

    fig = go.Figure()
    assert add_sample_annotation(fig, sample_size=1, minimum=5) is fig


def test_sample_annotation_reserves_room_for_itself():
    """The caption hangs below the plot area, so it needs a bottom margin.
    Without one Plotly draws it outside the painted region and the stage
    clips it — measured in the browser, not inferred."""
    from src.tradelens.ui.components.charts import (
        _SAMPLE_MARGIN,
        add_sample_annotation,
    )

    fig = add_sample_annotation(go.Figure(), sample_size=12, minimum=5)
    assert fig.layout.margin.b >= _SAMPLE_MARGIN


def test_the_stage_never_shrinks_a_reserved_bottom_margin():
    """The two helpers may be applied in either order, so neither may undo
    the other's reservation."""
    from src.tradelens.ui.components.charts import (
        _SAMPLE_MARGIN,
        add_sample_annotation,
        apply_chart_stage,
    )

    annotate_first = apply_chart_stage(
        add_sample_annotation(go.Figure(), sample_size=12, minimum=5)
    )
    stage_first = add_sample_annotation(
        apply_chart_stage(go.Figure()), sample_size=12, minimum=5
    )
    for fig in (annotate_first, stage_first):
        assert fig.layout.margin.b >= _SAMPLE_MARGIN


def test_a_plain_staged_chart_keeps_the_tight_bottom_margin():
    """Only charts that carry a caption pay for the space."""
    from src.tradelens.ui.components.charts import apply_chart_stage

    assert apply_chart_stage(go.Figure()).layout.margin.b == 8
