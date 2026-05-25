import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from datetime import datetime, timedelta
import random
from src.tradelens.db.session import SessionLocal
from src.tradelens.db.models import Trade

random.seed(42)

ASSETS = [
    ("NQ",     "futures", "5m",  "NY AM"),
    ("NQ",     "futures", "15m", "NY AM"),
    ("MNQ",    "futures", "5m",  "NY AM"),
    ("ES",     "futures", "5m",  "NY AM"),
    ("ES",     "futures", "15m", "NY PM"),
    ("MES",    "futures", "5m",  "NY AM"),
    ("NG",     "futures", "1H",  "London"),
    ("Gold",   "futures", "15m", "London"),
    ("Silver", "futures", "1H",  "London"),
    ("BTCUSD", "crypto",  "15m", "NY AM"),
    ("BTCUSD", "crypto",  "1H",  "Asia"),
    ("ETHUSD", "crypto",  "15m", "NY AM"),
    ("EURUSD", "forex",   "15m", "London"),
    ("EURUSD", "forex",   "1H",  "NY AM"),
    ("XAUUSD", "forex",   "15m", "London"),
]

SETUPS = [
    "FVG",
    "Order Block",
    "BOS",
    "Liquidity Sweep",
    "S/R Bounce",
    "CHOCH",
    "Breaker Block",
    "Equilibrium Retest",
]

EMOTIONS_BEFORE = ["calm", "focused", "hesitant", "confident", "anxious", "neutral"]
EMOTIONS_DURING = ["patient", "nervous", "disciplined", "impulsive", "calm"]
EMOTIONS_AFTER  = ["satisfied", "frustrated", "neutral", "relieved", "regretful"]

STRATEGIES = ["ICT 5m", "Supply & Demand", "S/R Breakout", "Scalp", "Swing"]

GRADES = ["A", "A-", "B+", "B", "B-", "C+", "C", "D"]

def random_trade(trade_date):
    asset_row  = random.choice(ASSETS)
    asset, asset_class, timeframe, session = asset_row
    direction  = random.choice(["long", "short"])
    result     = random.choices(["win", "loss", "breakeven"], weights=[50, 40, 10])[0]

    entry = round(random.uniform(100, 20000), 2)
    stop_dist = round(entry * random.uniform(0.002, 0.008), 2)
    tp_dist   = stop_dist * random.uniform(1.5, 3.0)

    if direction == "long":
        stop  = round(entry - stop_dist, 2)
        tp    = round(entry + tp_dist,   2)
        exit_ = round(entry + (tp_dist if result == "win" else -stop_dist * 0.9), 2)
    else:
        stop  = round(entry + stop_dist, 2)
        tp    = round(entry - tp_dist,   2)
        exit_ = round(entry - (tp_dist if result == "win" else -stop_dist * 0.9), 2)

    rr_planned  = round(tp_dist / stop_dist, 2)
    rr_realized = round(rr_planned if result == "win" else -0.9 if result == "loss" else 0.0, 2)
    position    = round(random.uniform(1, 5), 1)
    risk_amt    = round(stop_dist * position * 10, 2)
    pnl = round(
        risk_amt * rr_realized if result != "breakeven" else 0.0,
        2
    )

    return Trade(
        user_id          = 1,
        strategy_id      = None,
        trade_date       = trade_date.strftime("%Y-%m-%d"),
        day_of_week      = trade_date.strftime("%a"),
        session          = session,
        asset            = asset,
        asset_class      = asset_class,
        timeframe        = timeframe,
        direction        = direction,
        entry_price      = entry,
        stop_price       = stop,
        tp_price         = tp,
        exit_price       = exit_,
        position_size    = position,
        risk_amount      = risk_amt,
        reward_amount    = round(risk_amt * rr_planned, 2),
        rr_planned       = rr_planned,
        rr_realized      = rr_realized,
        result           = result,
        pnl              = pnl,
        strategy_used    = random.choice(STRATEGIES),
        bias             = random.choice(["bullish", "bearish", "neutral"]),
        setup_type       = random.choice(SETUPS),
        emotions_before  = random.choice(EMOTIONS_BEFORE),
        emotions_during  = random.choice(EMOTIONS_DURING),
        emotions_after   = random.choice(EMOTIONS_AFTER),
        notes            = "Seeded trade.",
        ai_grade         = random.choice(GRADES),
        user_grade       = None,
        created_at       = datetime.utcnow().isoformat(),
        updated_at       = datetime.utcnow().isoformat(),
    )

def seed():
    db = SessionLocal()
    try:
        existing = db.query(Trade).count()
        if existing > 0:
            print(f"Database already has {existing} trades. Skipping seed.")
            return

        start_date = datetime(2026, 3, 1)
        trades = []
        day_offset = 0
        count = 0

        while count < 60:
            trade_date = start_date + timedelta(days=day_offset)
            # skip weekends
            if trade_date.weekday() >= 5:
                day_offset += 1
                continue
            # 1-3 trades per day
            daily = random.randint(1, 3)
            for _ in range(daily):
                trades.append(random_trade(trade_date))
                count += 1
                if count >= 60:
                    break
            day_offset += 1

        db.add_all(trades)
        db.commit()
        print(f"✅ Seeded {len(trades)} trades successfully.")
    except Exception as e:
        db.rollback()
        print(f"❌ Seed failed: {e}")
        raise
    finally:
        db.close()

if __name__ == "__main__":
    seed()