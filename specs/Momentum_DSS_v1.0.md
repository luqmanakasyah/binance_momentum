Data Schema Specification v1.0

Applies to: PBC v2.2, SAS v1.0, Test Matrix v1.0
Goal: Define the persistent storage needed to enforce governance, reproducibility, auditing, and recovery.
Storage model: Relational (PostgreSQL recommended). No code, but fields are fully specified.

⸻

0. Design Rules (Binding)
   1. Append-only for audit and trade ledger
      Never update or delete historical records. Use new rows and explicit status fields.
   2. Version everything that can change
      Parameter bundles, optimisation runs, assumptions (fees/slippage), and strategy spec version.
   3. Deterministic recovery
      On restart, the bot must reconstruct PositionState, cooldown state, and active parameter bundles solely from persisted records.
   4. Per-instrument parameter governance
      Every decision must reference the parameter bundle version used.

⸻

1. Core Entities and Relationships

Entity graph (conceptual)
• instrument 1—many parameter_bundle
• parameter_bundle 1—many trade_plan
• trade_plan 1—many order_event
• trade_plan 1—1 position
• optimisation_run 1—many optimisation_result (one per instrument)
• system_state_snapshot captures current runtime summary (optional convenience, not source of truth)
• audit_event records every decision and safety action

⸻

2. Tables

2.1 instrument

Stores the fixed watchlist and ranking metadata.

Columns
• instrument_id (PK, UUID)
• symbol (TEXT, unique, e.g. BTCUSDT)
• contract_type (TEXT, must be USD-M_PERP)
• quote_asset (TEXT, e.g. USDT)
• is_active (BOOLEAN)
• liquidity_rank (INT, lower is better, immutable unless explicitly re-ranked)
• created_at (TIMESTAMP WITH TZ)

Constraints
• symbol unique
• Only active instruments are eligible for signals

⸻

2.2 assumption_set

Versioned constants used by optimiser and reporting.

Columns
• assumption_set_id (PK, UUID)
• name (TEXT, e.g. default_costs_v1)
• maker_fee_bps (NUMERIC)
• taker_fee_bps (NUMERIC)
• slippage_bps (NUMERIC)
• funding_cost_model (TEXT, descriptive identifier)
• effective_from (TIMESTAMP WITH TZ)
• effective_to (TIMESTAMP WITH TZ, nullable)
• created_at (TIMESTAMP WITH TZ)

Notes
• Every optimisation run must reference exactly one assumption_set_id.

⸻

2.3 optimisation_run

One record per optimiser execution.

Columns
• optimisation_run_id (PK, UUID)
• run_type (TEXT: DEPLOYMENT or MONTHLY)
• triggered_at (TIMESTAMP WITH TZ)
• started_at (TIMESTAMP WITH TZ)
• completed_at (TIMESTAMP WITH TZ, nullable until complete)
• status (TEXT: SUCCESS, FAILED, PARTIAL)
• month_key (TEXT, e.g. 2026-01 for monthly runs, nullable for deployment)
• training_window_days (INT, fixed for this run)
• validation_window_days (INT, fixed for this run)
• assumption_set_id (FK → assumption_set)
• git_commit_sha (TEXT, nullable but recommended)
• strategy_spec_version (TEXT, must be PBC_v2.2)
• notes (TEXT, nullable)

Constraints
• run_type=MONTHLY must have month_key
• Only one MONTHLY run per month_key should be marked SUCCESS (enforced via unique index on (month_key, status) with status='SUCCESS')

⸻

2.4 parameter_bundle

Versioned per-instrument parameter selection.

Columns
• parameter_bundle_id (PK, UUID)
• instrument_id (FK → instrument)
• bundle_version (INT, increment per instrument)
• optimisation_run_id (FK → optimisation_run, nullable if seeded)
• atr_stop_multiplier (NUMERIC, allowed: 1.2, 1.4, 1.6, 1.8)
• vol_gate_type (TEXT: ATR_GT_ATRMA or ATR_PERCENTILE)
• atr_ma_length (INT, allowed: 20, 30, nullable if percentile mode)
• atr_percentile_threshold (INT, allowed: 60, 70, nullable if ATRMA mode)
• rsi_reference (INT, allowed: 45, 50, 55)
• training_start (TIMESTAMP WITH TZ, nullable but recommended)
• training_end (TIMESTAMP WITH TZ, nullable but recommended)
• validation_start (TIMESTAMP WITH TZ, nullable but recommended)
• validation_end (TIMESTAMP WITH TZ, nullable but recommended)
• selected_objective_value (NUMERIC, nullable)
• selected_drawdown (NUMERIC, nullable)
• selected_trade_count (INT, nullable)
• is_active (BOOLEAN)
• active_from (TIMESTAMP WITH TZ)
• active_to (TIMESTAMP WITH TZ, nullable)
• created_at (TIMESTAMP WITH TZ)

Constraints
• Only one active bundle per instrument: unique partial index on (instrument_id) where is_active=true
• Values restricted to approved discrete sets
• If vol_gate_type=ATR_GT_ATRMA, then atr_ma_length required and atr_percentile_threshold null
• If vol_gate_type=ATR_PERCENTILE, then atr_percentile_threshold required and atr_ma_length null

Activation rule (governance)
• Bundles may not become active mid-position. This is enforced by the application, and verified by audit events (see Section 2.10).

⸻

2.5 signal_evaluation

Captures per-instrument evaluation outcomes at each 15m close, for traceability and diagnostics.

Columns
• signal_eval_id (PK, UUID)
• eval_timestamp (TIMESTAMP WITH TZ, must equal 15m candle close)
• instrument_id (FK → instrument)
• parameter_bundle_id (FK → parameter_bundle used)
• htf_trend_state (TEXT: BULL, BEAR, NEUTRAL_BUFFER)
• vol_gate_state (TEXT: PASS, FAIL)
• momentum_state (TEXT: PASS, FAIL)
• funding_state (TEXT: PASS, FAIL, UNKNOWN)
• eligible (BOOLEAN)
• rejection_reason (TEXT, nullable; enumerated preferred)
• trend_strength_score (NUMERIC, nullable)
• vol_expansion_score (NUMERIC, nullable)
• liquidity_rank (INT)
• created_at (TIMESTAMP WITH TZ)

Constraints
• Unique on (eval_timestamp, instrument_id) to avoid duplicates

⸻

2.6 selection_decision

Records the final selection among eligible signals per 15m close.

Columns
• selection_id (PK, UUID)
• eval_timestamp (TIMESTAMP WITH TZ)
• selected_instrument_id (FK → instrument, nullable if none selected)
• selected_signal_eval_id (FK → signal_evaluation, nullable)
• decision (TEXT: SELECTED, NONE, BLOCKED_BY_POSITION, BLOCKED_BY_COOLDOWN, BLOCKED_BY_SAFETY)
• decision_reason (TEXT, nullable)
• created_at (TIMESTAMP WITH TZ)

Constraints
• Unique on eval_timestamp (one decision per candle close)

⸻

2.7 trade_plan

Represents the intended trade with frozen R and parameter references.

Columns
• trade_plan_id (PK, UUID)
• created_at (TIMESTAMP WITH TZ)
• eval_timestamp (TIMESTAMP WITH TZ, originating 15m close)
• instrument_id (FK → instrument)
• parameter_bundle_id (FK → parameter_bundle)
• direction (TEXT: LONG, SHORT)
• entry_type (TEXT: MARKET)
• entry_intent_price (NUMERIC, nullable, for reference)
• stop_price (NUMERIC)
• tp_price (NUMERIC)
• r_value_price_distance (NUMERIC, absolute stop distance from entry reference)
• risk_intent_fraction (NUMERIC, must be 0.005)
• equity_total_at_plan (NUMERIC)
• equity_available_at_plan (NUMERIC)
• risk_intent_amount (NUMERIC) — 0.5% of total equity
• margin_required_estimate (NUMERIC)
• margin_used_actual (NUMERIC, nullable until filled)
• capital_constrained (BOOLEAN)
• realised_risk_at_stop_amount (NUMERIC) — after capital constraint
• qty (NUMERIC)
• tick_rounding_policy_id (TEXT, version tag)
• status (TEXT: PLANNED, SUBMITTED, CANCELLED, FILLED, FAILED)
• failure_reason (TEXT, nullable)

Binding constraints
• TP must be exactly 2R: store r_value_price_distance and validate that |tp - entry_ref| = 2 \* r_value after rounding policy.

⸻

2.8 position

Single-position lifecycle record per executed trade.

Columns
• position_id (PK, UUID)
• trade_plan_id (FK → trade_plan)
• instrument_id (FK → instrument)
• direction (TEXT: LONG, SHORT)
• opened_at (TIMESTAMP WITH TZ, nullable until open)
• closed_at (TIMESTAMP WITH TZ, nullable)
• entry_price_avg (NUMERIC, nullable)
• exit_price_avg (NUMERIC, nullable)
• qty_filled (NUMERIC, nullable)
• pnl_realised (NUMERIC, nullable)
• r_realised (NUMERIC, nullable) — realised pnl divided by risk at stop
• exit_reason (TEXT: TP, SL, TREND_INVALID, VOL_CONTRACTION, MOMENTUM_FAIL, FUNDING_EXTREME, SAFETY_HALT, MANUAL_FORBIDDEN_SHOULD_NOT_OCCUR)
• status (TEXT: OPENING, OPEN, CLOSING, CLOSED, FAILED)
• consecutive_loss_count_at_open (INT)
• consecutive_loss_count_at_close (INT)

Constraints
• Application enforces global one-open-position rule. Database can assist with a unique partial index where status in ('OPENING','OPEN','CLOSING').

⸻

2.9 order_event

Normalized order lifecycle events for entry, stop, TP, and close orders.

Columns
• order_event_id (PK, UUID)
• trade_plan_id (FK → trade_plan)
• position_id (FK → position, nullable until position exists)
• instrument_id (FK → instrument)
• order_role (TEXT: ENTRY, STOP, TP, CLOSE)
• exchange_order_id (TEXT)
• client_order_id (TEXT, unique per bot instance)
• event_type (TEXT: SUBMITTED, ACK, REJECTED, PARTIAL_FILL, FILL, CANCELLED, EXPIRED, ERROR)
• event_time (TIMESTAMP WITH TZ)
• price (NUMERIC, nullable)
• qty (NUMERIC, nullable)
• fee_paid (NUMERIC, nullable)
• raw_status (TEXT, nullable)
• notes (TEXT, nullable)

Constraints
• Append-only. Every order state change is another row.

⸻

2.10 audit_event

Append-only audit log for decisions, rejections, safety, and optimisation actions.

Columns
• audit_event_id (PK, UUID)
• event_time (TIMESTAMP WITH TZ)
• severity (TEXT: INFO, WARN, ERROR, CRITICAL)
• category (TEXT: SIGNAL, SELECTION, RISK, EXECUTION, POSITION, EXIT, COOLDOWN, OPTIMISATION, SAFETY, SYSTEM)
• event_name (TEXT, e.g. ENTRY_REJECTED_VOL_GATE, HALT_LEVERAGE_MISMATCH)
• instrument_id (FK → instrument, nullable)
• trade_plan_id (FK → trade_plan, nullable)
• position_id (FK → position, nullable)
• parameter_bundle_id (FK → parameter_bundle, nullable)
• optimisation_run_id (FK → optimisation_run, nullable)
• message (TEXT)
• details_json (JSONB, nullable, structured payload for debugging)
• strategy_spec_version (TEXT, must be PBC_v2.2)

Required events (minimum)
• Any rejection reason
• Any selection decision
• Any halt, resume, or safeguard action
• Any parameter bundle activation
• Any exit reason
• Monthly optimisation summary per instrument

⸻

2.11 cooldown_state

Single-row table storing cooldown status, for deterministic restart.

Columns
• cooldown_state_id (PK, UUID)
• is_active (BOOLEAN)
• consecutive_losses (INT)
• activated_at (TIMESTAMP WITH TZ, nullable)
• release_after_htf_close_time (TIMESTAMP WITH TZ, nullable)
• last_updated_at (TIMESTAMP WITH TZ)

Notes
• Alternatively, cooldown can be reconstructed from position history, but this table simplifies restart correctness.

⸻

2.12 system_halt_state

Single-row table to persist HALTED status across restarts.

Columns
• halt_state_id (PK, UUID)
• is_halted (BOOLEAN)
• halt_reason (TEXT)
• halted_at (TIMESTAMP WITH TZ, nullable)
• last_checked_at (TIMESTAMP WITH TZ)

Notes
• Every halt and resume must also be written to audit_event.

⸻

2.13 notification_event

Records outbound notifications for traceability.

Columns
• notification_event_id (PK, UUID)
• event_time (TIMESTAMP WITH TZ)
• channel (TEXT: TELEGRAM)
• type (TEXT: TRADE_OPEN, TRADE_CLOSE, HALT, RESUME, DAILY_SUMMARY, MONTHLY_OPTIMISATION)
• instrument_id (FK → instrument, nullable)
• trade_plan_id (FK → trade_plan, nullable)
• position_id (FK → position, nullable)
• status (TEXT: SENT, FAILED)
• failure_reason (TEXT, nullable)
• payload_json (JSONB, nullable)

⸻

3. Key Queries the System Must Support (Functional Requirements)
   1. Load active bundles per instrument
      • Fetch parameter_bundle where is_active=true for each active instrument.
   2. Reconstruct current position on restart
      • Find latest position where status in OPENING, OPEN, CLOSING.
   3. Determine if cooldown is active
      • From cooldown_state, plus check against the next 1H candle close time.
   4. Generate daily summary
      • Aggregate position closed today, PnL, R, win rate, rejection reasons from signal_evaluation.
   5. Monthly optimisation audit
      • For each instrument, show bundle changes and their objective metrics with links to optimisation_run.

⸻

4. Data Integrity Checks (What the implementation should validate)

These checks should be run at startup and periodically:
• Exactly one active bundle per instrument
• Any trade_plan has parameter_bundle_id
• Any position has trade_plan_id
• TP equals exactly 2R in each trade_plan (within deterministic tick rounding policy)
• No time-based exits present in exit_reason taxonomy
• No position exists with leverage != 1x (can be recorded in audit details)
