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
