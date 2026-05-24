from src.tradelens.db.session import SessionLocal
from src.tradelens.db.models import Strategy, Trade


def seed_data():
    db = SessionLocal()

    strategy = Strategy(
        name="Liquidity Sweep + FVG",
        trading_style="Intraday",
        entry_rules="Enter after liquidity sweep and confirmation back into fair value gap."
    )
    db.add(strategy)
    db.commit()
    db.refresh(strategy)

    sample_trades = [
        Trade(
            asset="ES",
            timeframe="5m",
            direction="Long",
            entry_price=5302.25,
            exit_price=5310.75,
            pnl=425.00,
            result="Win",
            rr_realized=2.1,
            setup_type="Liquidity Sweep",
            emotions_before="Calm",
            strategy_id=strategy.id
        ),
        Trade(
            asset="NQ",
            timeframe="5m",
            direction="Short",
            entry_price=18752.50,
            exit_price=18760.25,
            pnl=-155.00,
            result="Loss",
            rr_realized=-1.0,
            setup_type="FVG Rejection",
            emotions_before="Impatient",
            strategy_id=strategy.id
        ),
        Trade(
            asset="BTCUSD",
            timeframe="15m",
            direction="Long",
            entry_price=68250.00,
            exit_price=68940.00,
            pnl=320.00,
            result="Win",
            rr_realized=1.8,
            setup_type="Break of Structure",
            emotions_before="Focused",
            strategy_id=strategy.id
        ),
    ]

    db.add_all(sample_trades)
    db.commit()
    db.close()

    print("✅ Seed data inserted.")


if __name__ == "__main__":
    seed_data()