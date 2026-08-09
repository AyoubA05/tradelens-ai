"""Overview band forms.

Five bands, five forms (spec §5.1). The anti-grid rule is structural, not
stylistic: if two bands share a form the Overview becomes the card wall the
direction forbids, and a trader's eye has nothing to catch on.
"""

from src.tradelens.ui.components.overview_bands import (
    DisciplineMeasure,
    render_discipline_panel,
)


def test_every_value_is_visible_as_text_never_encoded_only_in_an_indicator():
    html = render_discipline_panel(
        [DisciplineMeasure(label="Rule adherence", value="72%", sample="18 of 25")]
    )
    assert "72%" in html and "18 of 25" in html


def test_a_measure_always_carries_its_sample_beside_the_figure():
    """A rate without its sample reads as certainty the journal has not
    earned. Handoff §2 requires the numerator and denominator."""
    html = render_discipline_panel(
        [DisciplineMeasure(label="Rule adherence", value="72%", sample="18 of 25")]
    )
    assert html.index("72%") < html.index("18 of 25")


def test_process_measures_are_never_toned_red_or_green():
    """Red and green are reserved for money outcomes (spec §5.3). Adherence
    and consistency are process, and colour may not do semantic work it is
    not licensed for."""
    html = render_discipline_panel(
        [DisciplineMeasure(label="Consistency", value="64", sample="n=31")]
    )
    assert 'data-tone="positive"' not in html
    assert 'data-tone="negative"' not in html


def test_the_panel_is_not_a_kpi_strip():
    """Band 2 must not reuse band 1's form."""
    html = render_discipline_panel(
        [DisciplineMeasure(label="Max drawdown", value="-$412.00", sample="n=25")]
    )
    assert "tl-kpi-strip" not in html
    assert "tl-discipline" in html


def test_a_note_is_rendered_when_a_measure_carries_one():
    html = render_discipline_panel(
        [
            DisciplineMeasure(
                label="Edge leak",
                value="+$40.00",
                sample="1 of 2 recorded",
                note="Lucky, not repeatable.",
            )
        ]
    )
    assert "Lucky, not repeatable." in html


def test_every_caller_value_is_escaped():
    html = render_discipline_panel(
        [
            DisciplineMeasure(
                label="<script>x</script>",
                value="<b>1</b>",
                sample="n=1",
                note="<i>note</i>",
            )
        ]
    )
    for raw in ("<script>", "<b>1</b>", "<i>note</i>"):
        assert raw not in html
    assert "&lt;script&gt;" in html


def test_one_root_element():
    html = render_discipline_panel(
        [DisciplineMeasure(label="A", value="1", sample="n=1")]
    ).strip()
    assert html.startswith('<div class="tl-discipline"')
    assert html.count('<div class="tl-discipline"') == 1


def test_an_empty_panel_renders_nothing_rather_than_an_empty_box():
    assert render_discipline_panel([]) == ""


def test_max_drawdown_is_displayed_as_money_lost():
    """compute_max_drawdown returns a positive magnitude by contract. Shown
    unsigned it sits beside a positive edge leak and reads as money made, so
    presentation signs it. The service is not changed — it is Codex-owned and
    its magnitude convention is documented and tested."""
    import pandas as pd

    from src.tradelens.ui.components.overview_bands import discipline_measures

    df = pd.DataFrame(
        {
            "trade_date": ["2026-08-01", "2026-08-02", "2026-08-03"],
            "pnl": [100.0, -250.0, 20.0],
        }
    )
    drawdown = [m for m in discipline_measures(df) if m.label == "Max drawdown"][0]
    assert drawdown.value.startswith("-$"), drawdown.value


def test_a_flat_curve_reports_no_drawdown_rather_than_negative_zero():
    import pandas as pd

    from src.tradelens.ui.components.overview_bands import discipline_measures

    df = pd.DataFrame({"trade_date": ["2026-08-01"], "pnl": [5.0]})
    drawdown = [m for m in discipline_measures(df) if m.label == "Max drawdown"][0]
    assert drawdown.value == "$0.00"


# ---------------------------------------------------------------------------
# Task 6 — band 4's ranked lists
# ---------------------------------------------------------------------------
from src.tradelens.ui.components.overview_bands import (  # noqa: E402
    RankedRow,
    render_ranked_list,
)


def test_each_row_carries_its_own_sample_size():
    html = render_ranked_list(
        "Killzone performance",
        [RankedRow("London", "+$820.00", "n=14"), RankedRow("NY", "-$110.00", "n=6")],
        rankable=True,
    )
    assert "n=14" in html and "n=6" in html


def test_one_category_is_never_called_strongest():
    """leading_category.is_only_category owns this decision (spec §5.5). One
    bar proves nothing, and saying so in an editorial voice is how an
    interface starts overstating what the journal knows."""
    html = render_ranked_list(
        "Setup performance",
        [RankedRow("FVG", "+$420.00", "n=9")],
        rankable=False,
    )
    lowered = html.lower()
    for word in ("strongest", "weakest", "best", "worst", "top"):
        assert word not in lowered


def test_a_rankable_list_marks_its_leader():
    html = render_ranked_list(
        "Killzone performance",
        [RankedRow("London", "+$820.00", "n=14"), RankedRow("NY", "-$110.00", "n=6")],
        rankable=True,
    )
    assert 'data-rank="1"' in html


def test_an_unrankable_list_carries_no_ordinal_marker():
    html = render_ranked_list(
        "Setup performance", [RankedRow("FVG", "+$420.00", "n=9")], rankable=False
    )
    assert "data-rank" not in html


def test_ranked_rows_escape_caller_values():
    html = render_ranked_list("S", [RankedRow("<b>x</b>", "1", "n=1")], rankable=False)
    assert "<b>x</b>" not in html
    assert "&lt;b&gt;" in html


def test_an_empty_ranked_list_renders_nothing():
    assert render_ranked_list("Killzone performance", [], rankable=True) == ""


# ---------------------------------------------------------------------------
# Task 6 — band 3's flanking figures
# ---------------------------------------------------------------------------
def _streak_frame():
    import pandas as pd

    return pd.DataFrame(
        {
            "trade_date": [f"2026-08-{d:02d}" for d in range(1, 6)],
            "pnl": [10.0, -4.0, 2.0, 8.0, -1.0],
            "result": ["Win", "Loss", "Win", "Win", "Loss"],
        }
    )


def _flank(df):
    from src.tradelens.ui.components.overview_bands import trajectory_figures

    return {f.label: f for f in trajectory_figures(df)}


def test_a_streak_carries_its_direction_as_a_word_not_only_a_sign():
    """current_streak is signed — -1 is one loss, not minus one trade. Colour
    may not be the only cue, so the word carries it."""
    current = _flank(_streak_frame())["Current streak"]
    assert current.value == "1 losing"


def test_a_winning_streak_reads_as_winning():
    import pandas as pd

    df = pd.DataFrame(
        {
            "trade_date": ["2026-08-01", "2026-08-02"],
            "pnl": [5.0, 6.0],
            "result": ["Win", "Win"],
        }
    )
    assert _flank(df)["Current streak"].value == "2 winning"


def test_no_wins_reads_as_no_wins_yet_never_as_zero():
    """avg_win returns 0.0 with no wins (spec D10). A zero average win is not
    an average of zero — it is the absence of any win."""
    import pandas as pd

    df = pd.DataFrame(
        {
            "trade_date": ["2026-08-01", "2026-08-02"],
            "pnl": [-5.0, -6.0],
            "result": ["Loss", "Loss"],
        }
    )
    figures = _flank(df)
    assert figures["Average win"].value == "No wins yet"
    assert figures["Average loss"].value.startswith("-$")


def test_no_losses_reads_as_no_losses_yet():
    import pandas as pd

    df = pd.DataFrame(
        {
            "trade_date": ["2026-08-01"],
            "pnl": [5.0],
            "result": ["Win"],
        }
    )
    assert _flank(df)["Average loss"].value == "No losses yet"


def test_band_three_does_not_restate_band_one():
    """Flanking figures describe the SHAPE of the sequence. Net P&L, win rate
    and trade count belong to band 1 and must not appear again."""
    labels = set(_flank(_streak_frame()))
    assert labels == {"Current streak", "Best run", "Average win", "Average loss"}


def test_flanking_figures_are_empty_for_an_empty_frame():
    import pandas as pd

    from src.tradelens.ui.components.overview_bands import trajectory_figures

    assert trajectory_figures(pd.DataFrame()) == []
