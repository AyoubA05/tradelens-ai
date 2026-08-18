"""Class B/C: functions where None selected the legacy NULL-owner tenant.

These already failed closed for a real user. The risk was quieter: a None
arriving by mistake read or wrote the legacy tenant instead of raising, so the
bug surfaced as missing data rather than an error.
"""
import pytest

from src.tradelens.services import cost, csvio, sample_data, trade_service, weekly


@pytest.mark.parametrize(
    "call",
    [
        lambda: trade_service.get_trade(1, None),
        lambda: trade_service.update_trade(1, None, pnl=1.0),
        lambda: trade_service.delete_trade(1, None),
        lambda: weekly.get_weekly_review("2026-08-10", None),
        lambda: weekly.get_weekly_reviews(None),
        lambda: sample_data.count_sample_trades(None),
        lambda: sample_data.clear_sample_trades(None),
        lambda: sample_data.load_sample_trades(None),
        lambda: cost.log_ai_usage("partner", object(), None),
    ],
)
def test_a_null_owner_raises_rather_than_selecting_the_legacy_tenant(call):
    with pytest.raises(ValueError):
        call()


def test_csv_import_requires_an_owner(tmp_path):
    f = tmp_path / "t.csv"
    f.write_bytes(b"trade_date,asset,result,pnl\n2026-08-12,NQ,Win,100\n")
    with pytest.raises(ValueError):
        with f.open("rb") as handle:
            csvio.import_trades_csv(handle, None)


def test_sample_trades_are_scoped_to_their_owner(two_users):
    a, b = two_users
    sample_data.load_sample_trades(a)

    assert sample_data.count_sample_trades(a) > 0
    assert sample_data.count_sample_trades(b) == 0
