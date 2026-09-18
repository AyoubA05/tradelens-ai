"""The §8 parity ledger is complete and honest.

Spec §8: "Nothing below may be dropped without an explicit, recorded decision."
Every §8 item appears exactly once with a status; `implemented` rows name a
location and a test; `removed` rows carry a reason.
"""

import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[1]
LEDGER = ROOT / "docs/superpowers/parity/2026-09-14-phase10-parity-ledger.md"

SECTION_ITEMS = {
    "Overview": [
        "KPI row (net P&L, win rate, expectancy, profit factor, trades)",
        "today P&L",
        "this-week P&L",
        "max drawdown",
        "rule adherence",
        "edge leak",
        "consistency score",
        "equity curve",
        "current/best streak",
        "average win",
        "average loss",
        "killzone performance",
        "setup performance",
        "trading-days calendar",
        "activation next-step",
        "recent trades",
        "filter panel",
        "low-data states",
    ],
    "Journal / Trades": [
        "date range",
        "asset",
        "session",
        "setup filters",
        "trades table (date, asset, session, setup, result, P&L, R, grade, screenshot)",
        "calendar month view",
        "open-from-day",
        "trade detail",
        "AI summary of the filtered set",
        "edit",
        "delete with confirmation",
        "per-trade screenshot upload",
    ],
    "New Trade": [
        "upload or image URL",
        "quality check",
        "AI analysis",
        "autofill review per field",
        "trade date",
        "entry time",
        "session auto-detect",
        "asset",
        "timeframe",
        "HTF bias",
        "LTF bias",
        "setup model",
        "evidence",
        "confirmation text",
        "followed-rules (yes/no/partial)",
        "result",
        "P&L",
        "risk",
        "position size",
        "R multiple",
        "exact price levels",
        "reflection notes",
        "emotion log (before/during/after)",
        "mistake tags",
        "completeness warnings",
        "draft persistence",
        "duplicate detection",
        "outcome/P&L contradiction block",
    ],
    "AI Reviews": [
        "Patterns (candidates, cards, confidence, evidence, sample size, next review action)",
        "Weekly Recap (week selector, generate, retry, validated sections)",
        "Daily Debrief (day selector, five sections)",
        "read-full-note disclosure",
    ],
    "Analytics": [
        "date range",
        "asset/session/strategy filters",
        "four lenses (Performance, Risk, Timing, Setups)",
        "equity curve",
        "daily P&L",
        "drawdown series",
        "R-multiple distribution",
        "by day of week",
        "by session",
        "by strategy",
        "by timeframe",
        "by asset",
        "by setup type",
        "emotion vs RR",
        "by hour of day",
        "killzone performance",
        "confirmation-model performance",
        "mistake frequency",
        "total edge leak",
        "rule adherence",
        "consistency score",
        "trade of the week",
        "period deltas",
        "evidence narrative per lens",
    ],
    "Strategy Profile": [
        "identity (name, style)",
        "markets",
        "timeframes",
        "entry rules",
        "exit rules (stop, target)",
        "risk rules",
        "setups",
        "mistakes to avoid",
        "active strategy",
        "ICT/SMC starter playbook",
        "sections-written progress",
        "skip path",
        "AI insight append",
    ],
    "AI Partner": [
        "global chat",
        "per-trade chat",
        "journal-grounded context",
        "evidence sources",
        "history trimming",
        "scope guard",
        "image attachment",
    ],
    "Settings": [
        "recovery email",
        "timezone",
        "API-key guidance",
        "CSV export",
        "CSV import",
        "load sample trades",
        "clear sample trades",
        "delete all trades",
        "delete account",
        "monthly cost by feature",
        "demo banner",
    ],
    "Cross-cutting": [
        "onboarding gate",
        "strategy gate",
        "activation status",
        "corrections capture feeding few-shot",
        "AI usage and cost logging",
        "DEMO_MODE",
        "low-sample confidence policy",
        "reflection-only safety language (never signals, predictions, or advice)",
    ],
    "Carried decisions": ["Strategy demo-playbook preview"],
}

ROW = re.compile(
    r"^\|\s*(?P<section>[^|]+?)\s*\|\s*(?P<item>[^|]+?)\s*\|\s*(?P<location>[^|]*?)\s*"
    r"\|\s*(?P<test>[^|]*?)\s*\|\s*(?P<status>[^|]+?)\s*\|$"
)


def _rows():
    rows = []
    for line in LEDGER.read_text(encoding="utf-8").splitlines():
        match = ROW.match(line)
        if (
            match
            and match["section"] not in ("Section", "---")
            and not set(match["section"]) <= {"-"}
        ):
            rows.append(match.groupdict())
    return rows


def test_every_section_8_item_appears_exactly_once():
    seen = {}
    for row in _rows():
        key = (row["section"], row["item"])
        seen[key] = seen.get(key, 0) + 1
    expected = {(s, i) for s, items in SECTION_ITEMS.items() for i in items}
    assert set(seen) == expected, {
        "missing": sorted(expected - set(seen)),
        "unexpected": sorted(set(seen) - expected),
    }
    assert all(count == 1 for count in seen.values()), {
        k: v for k, v in seen.items() if v > 1
    }


def test_every_row_has_an_allowed_status_with_its_evidence():
    for row in _rows():
        status = row["status"]
        assert (
            status == "implemented"
            or status == "blocker"
            or status.startswith("removed — ")
        ), row
        if status == "implemented":
            assert row["location"] and row["test"], row
        if status.startswith("removed — "):
            assert len(status) > len("removed — ") + 10, row


def test_implemented_locations_exist():
    for row in _rows():
        if row["status"] != "implemented":
            continue
        path = row["location"].split(":")[0].strip("` ")
        assert (ROOT / path).exists(), row
