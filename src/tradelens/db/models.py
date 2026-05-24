from typing import Optional
from sqlalchemy import String, Float, Integer, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .session import Base


class Strategy(Base):
    __tablename__ = "strategies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    trading_style: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    entry_rules: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    trades = relationship("Trade", back_populates="strategy")


class Trade(Base):
    __tablename__ = "trades"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    asset: Mapped[str] = mapped_column(String, nullable=False)
    timeframe: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    direction: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    entry_price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    exit_price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    pnl: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    result: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    rr_realized: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    setup_type: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    emotions_before: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    strategy_id: Mapped[Optional[int]] = mapped_column(ForeignKey("strategies.id"), nullable=True)

    strategy = relationship("Strategy", back_populates="trades")
    screenshots = relationship("Screenshot", back_populates="trade")


class Screenshot(Base):
    __tablename__ = "screenshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    file_path: Mapped[str] = mapped_column(String, nullable=False)
    trade_id: Mapped[int] = mapped_column(ForeignKey("trades.id"))

    trade = relationship("Trade", back_populates="screenshots")