from datetime import datetime
from typing import List, Optional
from uuid import UUID, uuid4
from sqlalchemy import (
    Column, Integer, String, Boolean, Numeric, DateTime, 
    ForeignKey, CheckConstraint, UniqueConstraint, Index, text
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID, JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

class Base(DeclarativeBase):
    pass

class Instrument(Base):
    __tablename__ = "instrument"
    
    instrument_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    symbol: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    contract_type: Mapped[str] = mapped_column(String, default="USD-M_PERP", nullable=False)
    quote_asset: Mapped[str] = mapped_column(String, default="USDT", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    liquidity_rank: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("CURRENT_TIMESTAMP"))

class AssumptionSet(Base):
    __tablename__ = "assumption_set"
    
    assumption_set_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String, nullable=False)
    maker_fee_bps: Mapped[float] = mapped_column(Numeric, nullable=False)
    taker_fee_bps: Mapped[float] = mapped_column(Numeric, nullable=False)
    slippage_bps: Mapped[float] = mapped_column(Numeric, nullable=False)
    funding_cost_model: Mapped[str] = mapped_column(String, nullable=False)
    effective_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    effective_to: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("CURRENT_TIMESTAMP"))

class OptimisationRun(Base):
    __tablename__ = "optimisation_run"
    
    optimisation_run_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    run_type: Mapped[str] = mapped_column(String, nullable=False)
    triggered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String, nullable=False)
    month_key: Mapped[Optional[str]] = mapped_column(String)
    training_window_days: Mapped[int] = mapped_column(Integer, nullable=False)
    validation_window_days: Mapped[int] = mapped_column(Integer, nullable=False)
    assumption_set_id: Mapped[Optional[UUID]] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("assumption_set.assumption_set_id"))
    git_commit_sha: Mapped[Optional[str]] = mapped_column(String)
    strategy_spec_version: Mapped[str] = mapped_column(String, default="PBC_v2.2", nullable=False)
    notes: Mapped[Optional[str]] = mapped_column(String)

    __table_args__ = (
        CheckConstraint("run_type IN ('DEPLOYMENT', 'MONTHLY')"),
        CheckConstraint("status IN ('SUCCESS', 'FAILED', 'PARTIAL')"),
        CheckConstraint("run_type != 'MONTHLY' OR month_key IS NOT NULL"),
        Index("idx_one_success_per_month", "month_key", unique=True, postgresql_where=text("status = 'SUCCESS' AND run_type = 'MONTHLY'")),
    )

class ParameterBundle(Base):
    __tablename__ = "parameter_bundle"
    
    parameter_bundle_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    instrument_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("instrument.instrument_id"), nullable=False)
    bundle_version: Mapped[int] = mapped_column(Integer, nullable=False)
    optimisation_run_id: Mapped[Optional[UUID]] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("optimisation_run.optimisation_run_id"))
    atr_stop_multiplier: Mapped[float] = mapped_column(Numeric, nullable=False)
    vol_gate_type: Mapped[str] = mapped_column(String, nullable=False)
    atr_ma_length: Mapped[Optional[int]] = mapped_column(Integer)
    atr_percentile_threshold: Mapped[Optional[int]] = mapped_column(Integer)
    rsi_reference: Mapped[int] = mapped_column(Integer, nullable=False)
    training_start: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    training_end: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    validation_start: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    validation_end: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    selected_objective_value: Mapped[Optional[float]] = mapped_column(Numeric)
    selected_drawdown: Mapped[Optional[float]] = mapped_column(Numeric)
    selected_trade_count: Mapped[Optional[int]] = mapped_column(Integer)
    is_active: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    active_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    active_to: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("CURRENT_TIMESTAMP"))

    __table_args__ = (
        CheckConstraint("atr_stop_multiplier IN (1.2, 1.4, 1.6, 1.8)"),
        CheckConstraint("vol_gate_type IN ('ATR_GT_ATRMA', 'ATR_PERCENTILE')"),
        CheckConstraint("atr_ma_length IN (20, 30) OR atr_ma_length IS NULL"),
        CheckConstraint("atr_percentile_threshold IN (60, 70) OR atr_percentile_threshold IS NULL"),
        CheckConstraint("rsi_reference IN (45, 50, 55)"),
        CheckConstraint(
            "(vol_gate_type = 'ATR_GT_ATRMA' AND atr_ma_length IS NOT NULL AND atr_percentile_threshold IS NULL) OR "
            "(vol_gate_type = 'ATR_PERCENTILE' AND atr_percentile_threshold IS NOT NULL AND atr_ma_length IS NULL)"
        ),
        Index("idx_active_bundle_per_instrument", "instrument_id", unique=True, postgresql_where=text("is_active = true")),
    )

class SignalEvaluation(Base):
    __tablename__ = "signal_evaluation"
    
    signal_eval_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    eval_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    instrument_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("instrument.instrument_id"), nullable=False)
    parameter_bundle_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("parameter_bundle.parameter_bundle_id"), nullable=False)
    htf_trend_state: Mapped[str] = mapped_column(String, nullable=False)
    vol_gate_state: Mapped[str] = mapped_column(String, nullable=False)
    momentum_state: Mapped[str] = mapped_column(String, nullable=False)
    funding_state: Mapped[str] = mapped_column(String, nullable=False)
    eligible: Mapped[bool] = mapped_column(Boolean, nullable=False)
    rejection_reason: Mapped[Optional[str]] = mapped_column(String)
    trend_strength_score: Mapped[Optional[float]] = mapped_column(Numeric)
    vol_expansion_score: Mapped[Optional[float]] = mapped_column(Numeric)
    liquidity_rank: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("CURRENT_TIMESTAMP"))

    __table_args__ = (
        CheckConstraint("htf_trend_state IN ('BULL', 'BEAR', 'NEUTRAL_BUFFER')"),
        CheckConstraint("vol_gate_state IN ('PASS', 'FAIL')"),
        CheckConstraint("momentum_state IN ('PASS', 'FAIL')"),
        CheckConstraint("funding_state IN ('PASS', 'FAIL', 'UNKNOWN')"),
        UniqueConstraint("eval_timestamp", "instrument_id"),
    )

class SelectionDecision(Base):
    __tablename__ = "selection_decision"
    
    selection_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    eval_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), unique=True, nullable=False)
    selected_instrument_id: Mapped[Optional[UUID]] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("instrument.instrument_id"))
    selected_signal_eval_id: Mapped[Optional[UUID]] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("signal_evaluation.signal_eval_id"))
    decision: Mapped[str] = mapped_column(String, nullable=False)
    decision_reason: Mapped[Optional[str]] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("CURRENT_TIMESTAMP"))

    __table_args__ = (
        CheckConstraint("decision IN ('SELECTED', 'NONE', 'BLOCKED_BY_POSITION', 'BLOCKED_BY_COOLDOWN', 'BLOCKED_BY_SAFETY')"),
    )

class TradePlan(Base):
    __tablename__ = "trade_plan"
    
    trade_plan_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("CURRENT_TIMESTAMP"))
    eval_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    instrument_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("instrument.instrument_id"), nullable=False)
    symbol: Mapped[str] = mapped_column(String, nullable=False)
    parameter_bundle_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("parameter_bundle.parameter_bundle_id"), nullable=False)
    direction: Mapped[str] = mapped_column(String, nullable=False)
    entry_type: Mapped[str] = mapped_column(String, default="MARKET", nullable=False)
    entry_intent_price: Mapped[Optional[float]] = mapped_column(Numeric)
    stop_price: Mapped[float] = mapped_column(Numeric, nullable=False)
    tp_price: Mapped[float] = mapped_column(Numeric, nullable=False)
    r_value_price_distance: Mapped[float] = mapped_column(Numeric, nullable=False)
    risk_intent_fraction: Mapped[float] = mapped_column(Numeric, default=0.005, nullable=False)
    equity_total_at_plan: Mapped[float] = mapped_column(Numeric, nullable=False)
    equity_available_at_plan: Mapped[float] = mapped_column(Numeric, nullable=False)
    risk_intent_amount: Mapped[float] = mapped_column(Numeric, nullable=False)
    margin_required_estimate: Mapped[float] = mapped_column(Numeric, nullable=False)
    margin_used_actual: Mapped[Optional[float]] = mapped_column(Numeric)
    capital_constrained: Mapped[bool] = mapped_column(Boolean, nullable=False)
    realised_risk_at_stop_amount: Mapped[float] = mapped_column(Numeric, nullable=False)
    qty: Mapped[float] = mapped_column(Numeric, nullable=False)
    tick_rounding_policy_id: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False)
    failure_reason: Mapped[Optional[str]] = mapped_column(String)

    __table_args__ = (
        CheckConstraint("direction IN ('LONG', 'SHORT')"),
        CheckConstraint("status IN ('PLANNED', 'SUBMITTED', 'CANCELLED', 'FILLED', 'FAILED')"),
    )

class Position(Base):
    __tablename__ = "position"
    
    position_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    trade_plan_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("trade_plan.trade_plan_id"), nullable=False)
    instrument_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("instrument.instrument_id"), nullable=False)
    symbol: Mapped[str] = mapped_column(String, nullable=False)
    direction: Mapped[str] = mapped_column(String, nullable=False)
    opened_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    closed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    entry_price_avg: Mapped[Optional[float]] = mapped_column(Numeric)
    exit_price_avg: Mapped[Optional[float]] = mapped_column(Numeric)
    qty_filled: Mapped[Optional[float]] = mapped_column(Numeric)
    pnl_realised: Mapped[Optional[float]] = mapped_column(Numeric)
    r_realised: Mapped[Optional[float]] = mapped_column(Numeric)
    exit_reason: Mapped[Optional[str]] = mapped_column(String)
    status: Mapped[str] = mapped_column(String, nullable=False)
    consecutive_loss_count_at_open: Mapped[int] = mapped_column(Integer, nullable=False)
    consecutive_loss_count_at_close: Mapped[int] = mapped_column(Integer, nullable=False)

    __table_args__ = (
        CheckConstraint("direction IN ('LONG', 'SHORT')"),
        CheckConstraint("status IN ('OPENING', 'OPEN', 'CLOSING', 'CLOSED', 'FAILED')"),
        CheckConstraint("exit_reason IN ('TP', 'SL', 'TREND_INVALID', 'VOL_CONTRACTION', 'MOMENTUM_FAIL', 'FUNDING_EXTREME', 'SAFETY_HALT', 'MANUAL_FORBIDDEN_SHOULD_NOT_OCCUR') OR exit_reason IS NULL"),
        Index("idx_one_open_position", "status", unique=True, postgresql_where=text("status IN ('OPENING', 'OPEN', 'CLOSING')")),
    )

class OrderEvent(Base):
    __tablename__ = "order_event"
    
    order_event_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    trade_plan_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("trade_plan.trade_plan_id"), nullable=False)
    position_id: Mapped[Optional[UUID]] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("position.position_id"))
    instrument_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("instrument.instrument_id"), nullable=False)
    order_role: Mapped[str] = mapped_column(String, nullable=False)
    exchange_order_id: Mapped[str] = mapped_column(String, nullable=False)
    client_order_id: Mapped[str] = mapped_column(String, nullable=False)
    event_type: Mapped[str] = mapped_column(String, nullable=False)
    event_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    price: Mapped[Optional[float]] = mapped_column(Numeric)
    qty: Mapped[Optional[float]] = mapped_column(Numeric)
    fee_paid: Mapped[Optional[float]] = mapped_column(Numeric)
    raw_status: Mapped[Optional[str]] = mapped_column(String)
    notes: Mapped[Optional[str]] = mapped_column(String)

    __table_args__ = (
        CheckConstraint("order_role IN ('ENTRY', 'STOP', 'TP', 'CLOSE')"),
        CheckConstraint("event_type IN ('SUBMITTED', 'ACK', 'REJECTED', 'PARTIAL_FILL', 'FILL', 'CANCELLED', 'EXPIRED', 'ERROR')"),
    )

class AuditEvent(Base):
    __tablename__ = "audit_event"
    
    audit_event_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    event_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("CURRENT_TIMESTAMP"))
    severity: Mapped[str] = mapped_column(String, nullable=False)
    category: Mapped[str] = mapped_column(String, nullable=False)
    event_name: Mapped[str] = mapped_column(String, nullable=False)
    instrument_id: Mapped[Optional[UUID]] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("instrument.instrument_id"))
    trade_plan_id: Mapped[Optional[UUID]] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("trade_plan.trade_plan_id"))
    position_id: Mapped[Optional[UUID]] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("position.position_id"))
    parameter_bundle_id: Mapped[Optional[UUID]] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("parameter_bundle.parameter_bundle_id"))
    optimisation_run_id: Mapped[Optional[UUID]] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("optimisation_run.optimisation_run_id"))
    message: Mapped[str] = mapped_column(String, nullable=False)
    details_json: Mapped[Optional[dict]] = mapped_column(JSONB)
    strategy_spec_version: Mapped[str] = mapped_column(String, default="PBC_v2.2", nullable=False)

    __table_args__ = (
        CheckConstraint("severity IN ('INFO', 'WARN', 'ERROR', 'CRITICAL')"),
        CheckConstraint("category IN ('SIGNAL', 'SELECTION', 'RISK', 'EXECUTION', 'POSITION', 'EXIT', 'COOLDOWN', 'OPTIMISATION', 'SAFETY', 'SYSTEM')"),
    )

class CooldownState(Base):
    __tablename__ = "cooldown_state"
    
    cooldown_state_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    is_active: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    consecutive_losses: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    activated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    release_after_htf_close_time: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    last_updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("CURRENT_TIMESTAMP"), onupdate=text("CURRENT_TIMESTAMP"))

class SystemHaltState(Base):
    __tablename__ = "system_halt_state"
    
    halt_state_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    is_halted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    halt_reason: Mapped[Optional[str]] = mapped_column(String)
    halted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    last_checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("CURRENT_TIMESTAMP"))

class NotificationEvent(Base):
    __tablename__ = "notification_event"
    
    notification_event_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    event_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("CURRENT_TIMESTAMP"))
    channel: Mapped[str] = mapped_column(String, default="TELEGRAM", nullable=False)
    type: Mapped[str] = mapped_column(String, nullable=False)
    instrument_id: Mapped[Optional[UUID]] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("instrument.instrument_id"))
    trade_plan_id: Mapped[Optional[UUID]] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("trade_plan.trade_plan_id"))
    position_id: Mapped[Optional[UUID]] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("position.position_id"))
    status: Mapped[str] = mapped_column(String, nullable=False)
    failure_reason: Mapped[Optional[str]] = mapped_column(String)
    payload_json: Mapped[Optional[dict]] = mapped_column(JSONB)

    __table_args__ = (
        CheckConstraint("type IN ('TRADE_OPEN', 'TRADE_CLOSE', 'HALT', 'RESUME', 'DAILY_SUMMARY', 'MONTHLY_OPTIMISATION')"),
        CheckConstraint("status IN ('SENT', 'FAILED')"),
    )
