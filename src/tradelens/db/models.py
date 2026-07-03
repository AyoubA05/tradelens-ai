from typing import Optional
from sqlalchemy import String, Float, Integer, ForeignKey, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .session import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    username: Mapped[str] = mapped_column(
        String, unique=True, nullable=False, index=True
    )
    password_hash: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    is_active: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class Strategy(Base):
    __tablename__ = "strategies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    trading_style: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    entry_rules: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    markets: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    timeframes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    stop_rules: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    take_profit_rules: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    risk_rules: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    setups_traded: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    setups_avoided: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    news_session_rules: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    common_mistakes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_active: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    updated_at: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    trades = relationship("Trade", back_populates="strategy")


class Trade(Base):
    __tablename__ = "trades"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    trade_date: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    day_of_week: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    session: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    asset: Mapped[str] = mapped_column(String, nullable=False)
    asset_class: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    timeframe: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    direction: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    bias: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    setup_type: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    entry_price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    stop_price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    tp_price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    exit_price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    position_size: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    risk_amount: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    reward_amount: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    rr_planned: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    rr_realized: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    result: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    pnl: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    strategy_used: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    emotions_before: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    emotions_during: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    emotions_after: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    ai_grade: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    user_grade: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    # SMC/ICT fields — Phase 1
    htf_bias: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    killzone: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    liquidity_sweep: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    fvg_used: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    order_block_used: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    bos: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    choch: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    confirmation_model: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    entry_type: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    mistake_tags: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    followed_rules: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Marks demo/sample rows so they can be cleared without touching real trades.
    is_sample: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, default=0)

    # Owning user (multi-user, Session B). NULL = legacy single-user trades.
    user_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id"), nullable=True, index=True
    )
    # Deterministic fingerprint for duplicate detection (Session B).
    trade_hash: Mapped[Optional[str]] = mapped_column(String, nullable=True, index=True)

    created_at: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    updated_at: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    strategy_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("strategies.id"), nullable=True
    )

    strategy = relationship("Strategy", back_populates="trades")
    screenshots = relationship(
        "Screenshot", back_populates="trade", cascade="all, delete-orphan"
    )
    ai_analysis = relationship(
        "AIAnalysis",
        back_populates="trade",
        uselist=False,
        cascade="all, delete-orphan",
    )


class Screenshot(Base):
    __tablename__ = "screenshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    trade_id: Mapped[int] = mapped_column(ForeignKey("trades.id", ondelete="CASCADE"))
    file_path: Mapped[str] = mapped_column(String, nullable=False)
    width: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    height: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    uploaded_at: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    trade = relationship("Trade", back_populates="screenshots")


class AIAnalysis(Base):
    __tablename__ = "aianalysis"
    __table_args__ = (UniqueConstraint("trade_id", name="uq_aianalysis_trade_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    trade_id: Mapped[int] = mapped_column(
        ForeignKey("trades.id", ondelete="CASCADE"), nullable=False
    )
    model: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    prompt_version: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    bias: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    detected_setup: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    zones_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    matched_strategy: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    mistakes_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    missed_opps_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    trade_quality: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    journal_entry_md: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    grading_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    raw_response_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    tokens_input: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    tokens_output: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    cost_usd: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    created_at: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    updated_at: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    trade = relationship("Trade", back_populates="ai_analysis")


class Correction(Base):
    __tablename__ = "corrections"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    trade_id: Mapped[int] = mapped_column(
        ForeignKey("trades.id", ondelete="CASCADE"), nullable=False
    )
    ai_analysis_id: Mapped[int] = mapped_column(
        ForeignKey("aianalysis.id", ondelete="CASCADE"), nullable=False
    )
    field: Mapped[str] = mapped_column(Text, nullable=False)
    ai_value: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    user_value: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    user_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    # Owning user (multi-user). NULL = legacy single-user corrections.
    user_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id"), nullable=True, index=True
    )


class AIUsageLog(Base):
    """Per-call AI usage for features with no natural persistence row
    (AI Partner chat, pattern-card detection) — powers the cost dashboard."""

    __tablename__ = "ai_usage_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    feature: Mapped[str] = mapped_column(Text, nullable=False)
    model: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    tokens_input: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    tokens_output: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    cost_usd: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    # Owning user (multi-user). NULL = legacy single-user calls.
    user_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id"), nullable=True, index=True
    )
    created_at: Mapped[Optional[str]] = mapped_column(String, nullable=True)


class PerformanceMetrics(Base):
    __tablename__ = "performance_metrics"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    period_start: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    period_end: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    trades_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    win_rate: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    profit_factor: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    avg_rr: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    avg_win: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    avg_loss: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    total_pnl: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    best_day: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    worst_day: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    best_strategy: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    worst_strategy: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    best_timeframe: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    worst_timeframe: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    computed_at: Mapped[Optional[str]] = mapped_column(String, nullable=True)


class WeeklyReview(Base):
    __tablename__ = "weekly_reviews"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    # Owning user (multi-user, Session D). NULL = legacy single-user reviews.
    user_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id"), nullable=True, index=True
    )
    week_start: Mapped[str] = mapped_column(
        String, nullable=False, index=True
    )  # ISO Monday (YYYY-MM-DD)
    content_md: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    thinking_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    stats_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    cost_usd: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    created_at: Mapped[Optional[str]] = mapped_column(String, nullable=True)
