from datetime import date, datetime, timezone
from typing import Optional
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    String,
    Float,
    Integer,
    ForeignKey,
    Text,
    UniqueConstraint,
    text,
    false as sa_false,
    true as sa_true,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .session import Base


def _utc_iso() -> str:
    """A stable optimistic-concurrency stamp for direct ORM inserts."""
    return datetime.now(timezone.utc).isoformat()


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(
        String, unique=True, nullable=False, index=True
    )
    password_hash: Mapped[str] = mapped_column(String, nullable=False)
    # Optional, and the only way to recover an account: without it a forgotten
    # password is unrecoverable. Stored lowercase so uniqueness is meaningful.
    # Nullable + unique lets existing accounts stay email-less (both SQLite and
    # Postgres permit repeated NULLs under a unique index).
    email: Mapped[Optional[str]] = mapped_column(
        String, unique=True, nullable=True, index=True
    )
    created_at: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    # Integer, not Boolean: 1 is active. The database-side default matters
    # independently of the ORM one — the column is NOT NULL, so a raw INSERT
    # that omits it fails without a server_default. Both are declared and they
    # agree; the Python default keeps ORM-constructed objects meaningful before
    # a flush, the server default makes non-ORM writes land on the same value.
    is_active: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default=text("1")
    )

    # --- Collected at signup by the site-hosted flow (2026-08) --------------
    # Nullable because every account created before that flow existed supplied
    # none of them. The signup endpoint requires them for new accounts, so the
    # asymmetry is deliberate: the database stays permissive so the migration
    # cannot break existing rows, and the service layer enforces the rule where
    # it can tell a new signup from a legacy row.
    full_name: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    birthday: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    referral_source: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    referral_source_other: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    onboarding_completed: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=sa_false()
    )
    strategy_profile_completed: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=sa_false()
    )

    # NULL means unverified; a timestamp means verified. Deliberately NOT
    # backfilled for legacy accounts — their address genuinely was never
    # verified, and writing a timestamp saying otherwise would put a falsehood
    # in the data to save one boolean, and make "which addresses are actually
    # confirmed?" permanently unanswerable.
    email_verified_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # The explicit legacy compatibility rule. False for every account that
    # predates verification, so the login gate lets them through without us
    # pretending they verified. New accounts default to True.
    email_verification_required: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=sa_true()
    )

    # Which application surface this account lands on after login. Defaults to
    # 'streamlit' so every existing account keeps the product it already knows;
    # accounts are moved to 'nextjs' individually during the parity window.
    # Both surfaces read one database, so this routes a person, not their data.
    # Removed once Streamlit is retired (Phase 10).
    app_surface: Mapped[str] = mapped_column(
        String, nullable=False, server_default=text("'streamlit'")
    )


class Strategy(Base):
    __tablename__ = "strategies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id"), nullable=True, index=True
    )
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


class UserSetting(Base):
    __tablename__ = "user_settings"
    __table_args__ = (
        UniqueConstraint("user_id", "key", name="uq_user_settings_user_key"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    key: Mapped[str] = mapped_column(String, nullable=False)
    value: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    updated_at: Mapped[Optional[str]] = mapped_column(String, nullable=True)


class Trade(Base):
    __tablename__ = "trades"
    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "create_idempotency_key",
            name="uq_trades_user_create_idempotency",
        ),
    )

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
    # Item 8: mechanical process notes ("what the chart/trader did"), distinct
    # from the emotional mindset fields. Feeds the per-trade AI review context.
    trade_process_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

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
    # Integer, not Boolean: 0 means a real trade, 1 means seeded sample data.
    # The server default keeps the real/sample partition well-defined for writes
    # that do not go through the ORM; the Python default agrees with it.
    is_sample: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True, default=0, server_default=text("0")
    )

    # Owning user (multi-user, Session B). NULL = legacy single-user trades.
    user_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id"), nullable=True, index=True
    )
    # Deterministic fingerprint for duplicate detection (Session B).
    trade_hash: Mapped[Optional[str]] = mapped_column(String, nullable=True, index=True)
    # Only the authenticated HTTP create path sets this. Keeping it nullable
    # preserves historical/CSV/Streamlit semantics while the per-owner unique
    # constraint makes two concurrent HTTP retries collapse to one row.
    create_idempotency_key: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    created_at: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    updated_at: Mapped[str] = mapped_column(
        String,
        nullable=False,
        default=_utc_iso,
        # `updated_at` is a legacy VARCHAR. PostgreSQL requires the default
        # expression to match that type; a bare CURRENT_TIMESTAMP is temporal
        # and can make the production migration fail. This cast is portable
        # to SQLite while retaining a database-side non-NULL default.
        server_default=text("CAST(CURRENT_TIMESTAMP AS VARCHAR)"),
    )

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
    # Server-owned write guards (Phase 5). Each names the job whose result
    # currently occupies the matching columns. A worker write is conditional
    # on being NEWER than what is stored, so a slow older job cannot land on
    # top of a newer one's result.
    analysis_job_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    journal_job_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    grading_job_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    # When the trader last confirmed labels, and which ones. A confirmed field
    # is locked: no job write may replace it until the trader changes or
    # releases it.
    confirmed_at: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    confirmed_fields_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    trade = relationship("Trade", back_populates="ai_analysis")


class Correction(Base):
    __tablename__ = "corrections"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
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

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
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

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
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


# ---------------------------------------------------------------------------
# Site-hosted authentication (2026-08). Credentials are stored as SHA-256
# hashes only, so reading these tables yields nothing that can be replayed.
# ---------------------------------------------------------------------------


class AuthHandoff(Base):
    """One-time credential handing a signed-in user from the site to Streamlit.

    Redemption is a single conditional UPDATE, never a read-then-write:
    Streamlit reruns scripts concurrently and two tabs can race for the same
    row, so the "is it unconsumed?" check and the "mark it consumed" write have
    to be one statement or both tabs can win.

    Never reused as the durable session — see AuthSession.
    """

    __tablename__ = "auth_handoffs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    token_hash: Mapped[str] = mapped_column(
        String(64), unique=True, nullable=False, index=True
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"), nullable=False, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    consumed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class AuthSession(Base):
    """Revocable server-side session, replacing the self-contained HMAC token.

    The old token could not be revoked: signing out cleared session_state and
    popped the URL parameter, but the token itself stayed cryptographically
    valid for up to 24 hours, so anyone with a copied link could sign back in.
    Revocation here is a row update, which is what makes sign-out mean anything.

    `expires_at` is written once at creation and updated by nothing — that is
    what makes the 12h cap absolute. `last_seen_at` carries the sliding 8h idle
    window, so activity extends the idle bound but never the absolute one.
    """

    __tablename__ = "auth_sessions"
    __table_args__ = (
        CheckConstraint(
            "surface IN ('website', 'streamlit')",
            name="ck_auth_sessions_surface",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # Which surface issued this session. NO DEFAULT, deliberately: a default of
    # 'website' would let a future Streamlit creation path that forgets the
    # field silently mint a website-domain row, which is the exact confusion
    # this column exists to prevent. Every call site must choose.
    surface: Mapped[str] = mapped_column(String(16), nullable=False)
    token_hash: Mapped[str] = mapped_column(
        String(64), unique=True, nullable=False, index=True
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"), nullable=False, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    revoked_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class AuthAttempt(Base):
    """One row per authentication attempt, for DB-backed rate limiting.

    Serverless instances share no memory, so an in-process counter is not a
    limit at all — it resets whenever the platform decides to cold-start.

    `bucket` is an opaque key such as "ip:1.2.3.4" or "id:someone@example.com".
    `succeeded` exists so per-identifier limits can count failures only: without
    it, an attacker could lock a known user out simply by burning their quota.
    """

    __tablename__ = "auth_attempts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    bucket: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    action: Mapped[str] = mapped_column(String(40), nullable=False)
    succeeded: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=sa_false()
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )


class EmailVerification(Base):
    """Durable, opaque, single-use email-verification token.

    The design this replaces signed a claim containing the user id and expiry,
    reusing the password-reset pattern. That is a signed claim rather than an
    opaque handle, and — more importantly — it has no record that a token was
    used, so a replay attempt is indistinguishable from a forgery.

    `email` is the field that does the real work. Without it, a user could sign
    up as one address, change to another, then click the original link and have
    an address nobody proved control of marked verified. Consume compares this
    against the account's current address and refuses on mismatch.

    `consumed_at` and `superseded_at` are separate on purpose. "The user clicked
    this link" and "the user asked for a new one" are different events, and
    merging them would make a genuine replay look exactly like a click on a
    superseded link — the difference between an attack signal and a support case.
    """

    __tablename__ = "email_verifications"
    __table_args__ = (
        # Guards a clock or arithmetic bug at the database rather than in review.
        CheckConstraint(
            "expires_at > created_at",
            name="ck_email_verifications_expiry_after_creation",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    token_hash: Mapped[str] = mapped_column(
        String(64), unique=True, nullable=False, index=True
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # The NORMALISED address being verified, under the same contract as
    # users.email — trimmed and lowercased.
    email: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    consumed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    superseded_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class PasswordReset(Base):
    """Durable, opaque, single-use password-reset token.

    Replaces the signed claim-bearing codes in services/password_reset.py, which
    carried the user id and expiry inside the token and stored nothing — so a
    replay could not be told apart from a forgery, and outstanding tokens could
    not be explicitly invalidated.

    Deliberately the same shape as EmailVerification, plus one column.

    `password_hash_fingerprint` recovers a property the old design got for free.
    Because its signing key derived from the current password hash, *any*
    password change invalidated every outstanding code. A token table loses that
    unless something replaces it — so the fingerprint is compared at consume, and
    a hash that has changed by any route makes the token stale. It is a condition
    nobody can forget, rather than a supersede-write every future password-change
    path must remember to perform.

    It stores SHA-256 of the hash, never the hash itself and never the password.
    """

    __tablename__ = "password_resets"
    __table_args__ = (
        CheckConstraint(
            "expires_at > created_at",
            name="ck_password_resets_expiry_after_creation",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    token_hash: Mapped[str] = mapped_column(
        String(64), unique=True, nullable=False, index=True
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # Normalised address the reset was issued for, under the same contract as
    # users.email.
    email: Mapped[str] = mapped_column(String, nullable=False)
    # SHA-256 hex of the exact users.password_hash string, UTF-8 encoded.
    password_hash_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    consumed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    superseded_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class AIJob(Base):
    """One asynchronous AI request.

    AI calls run 60-120 seconds, which is longer than a request should live and
    longer than most proxies allow. They are therefore enqueued here and run by
    a separate worker process against the same database.

    `(user_id, idempotency_key)` is unique. That constraint is the only thing
    standing between a double-submitted form and a second Anthropic bill, and it
    is per-owner rather than global so one trader's key cannot block another's.
    """

    __tablename__ = "ai_jobs"
    __table_args__ = (
        UniqueConstraint("user_id", "idempotency_key", name="uq_ai_jobs_user_key"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    kind: Mapped[str] = mapped_column(String, nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(
        String, nullable=False, default="queued", server_default=text("'queued'")
    )
    payload: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # A pointer to where the result landed (e.g. an aianalysis id), never the
    # result itself: generated content belongs in its own table.
    result_ref: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    # Safe for a user to read: no provider text, no stack trace.
    error: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    attempts: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    created_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    started_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    finished_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class TradeSummaryResult(Base):
    """Persisted prose for a filtered-trade AI job.

    The queue stores only ``trade_summary:<id>`` in ``result_ref``. The result
    itself remains owner-scoped and is deduplicated by the immutable snapshot
    key carried in the job payload.
    """

    __tablename__ = "trade_summary_results"
    __table_args__ = (
        UniqueConstraint(
            "user_id", "summary_key", name="uq_trade_summary_results_user_key"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    summary_key: Mapped[str] = mapped_column(String, nullable=False)
    filters_json: Mapped[str] = mapped_column(Text, nullable=False)
    content_md: Mapped[str] = mapped_column(Text, nullable=False)
    reviewed_trades: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )


class TradeDraft(Base):
    """An in-progress New Trade form, saved before it is a journal entry.

    Deliberately its own table rather than an `is_draft` flag on `trades`
    (Decision 3): a flag puts the "never a journal entry" guarantee at the
    mercy of every future query, filter, metric or export that touches
    `trades`, while a separate table makes it structurally impossible for a
    draft to be picked up by any of them.

    `user_id` carries a unique constraint, not just an index: "one live draft
    per owner, superseded on save" is enforced by the schema itself rather
    than by application code remembering to delete-before-insert.
    """

    __tablename__ = "trade_drafts"
    __table_args__ = (UniqueConstraint("user_id", name="uq_trade_drafts_user"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    payload_json: Mapped[str] = mapped_column(Text, nullable=False)
    # Monotonic optimistic-concurrency token for browser autosaves.  Create
    # retires (rather than deletes) the row and increments this value, so a PUT
    # that was already in flight cannot recreate the completed trade's draft.
    revision: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    retired_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
