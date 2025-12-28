System Architecture Specification (SAS) v1.0

Derived from: PBC v2.2
System: Momentum Continuation Bot (HTF + ATR-Gated), Binance USD-M, Isolated, 1x

⸻

1. Architecture Overview

1.1 High-level components

1. Market Data Service
   • Produces completed 15m and 1H candles per instrument
   • Guarantees candle-close determinism (no intrabar signals)
2. Indicator Engine
   • Computes EMA200 (1H), ATR(14) (15m), ATR-MA (15m), ATR percentile (15m), RSI (15m)
   • Provides instrument-scoped indicator snapshots
3. Signal Engine
   • Applies HTF trend filter + EMA buffer
   • Applies momentum continuation rule
   • Applies volatility expansion gate
   • Emits per-instrument “Eligible Signal” objects at candle close only
4. Selector
   • Resolves simultaneous signals
   • Enforces one-position-at-a-time
   • Deterministically selects exactly one instrument to trade (or none)
5. Risk and Sizing Engine
   • Computes stop distance from ATR and instrument parameters
   • Computes target size from risk intent (0.5% equity at stop)
   • Applies capital constraint: if insufficient available equity, uses all available equity
6. Execution Engine
   • Places market entry
   • Places protective stop and fixed TP at exactly 2R
   • Validates Binance modes: isolated, 1x
   • Tracks order acknowledgements and fills
7. Position Manager
   • Maintains a single global position state
   • Applies regime exits (trend invalidation, volatility contraction, momentum failure, funding extreme)
   • Applies optional trailing only after ≥1R unrealised profit
   • Initiates closes and cancels as needed
8. Optimisation Subsystem
   • Runs per-instrument optimisation at deployment and on the first day of each month
   • Selects from discrete parameter sets only
   • Produces versioned parameter bundles per instrument
   • Never changes parameters mid-position
9. Safety Supervisor
   • Kill switches: API errors, latency, state mismatch, liquidation buffer invalid, leverage or margin mode mismatch
   • If triggered: halts new entries; may close existing position
10. Audit Logger and Notifier
    • Append-only structured logs for every decision
    • Telegram notifications: trade open, trade close, halt, monthly optimisation outcome, daily summary

⸻

2. Runtime Workflow

2.1 Candle-close loop (15m)

1. Market Data Service emits “15m candle closed” for each instrument
2. Indicator Engine updates 15m indicators
3. Signal Engine evaluates eligibility for each instrument using:
   • Latest 1H state (cached)
   • Latest 15m indicators
   • Current instrument parameter bundle
4. Selector chooses at most one signal
5. Safety Supervisor validates system health and exchange mode invariants
6. Risk and Sizing Engine computes order sizes and protective levels
7. Execution Engine submits entry + stop + TP (or entry then immediately place stop/TP)
8. Position Manager begins monitoring for exits and trailing eligibility

2.2 Candle-close loop (1H)

1. Market Data Service emits “1H candle closed”
2. Indicator Engine updates 1H EMA200 and HTF ATR for buffer sizing
3. Signal Engine updates HTF regime state used by 15m loop
4. Cooldown rule evaluation point:
   • If in cooldown, it may resume only after this event

2.3 Position monitoring loop (event-driven)

Triggered by:
• Order execution reports
• Funding updates (poll or stream)
• New 15m/1H candle closes
• Safety events

⸻

3. Data Contracts (Internal Objects)

3.1 InstrumentParameterBundle (per instrument, versioned)

Fields:
• atr_stop_multiplier ∈ {1.2, 1.4, 1.6, 1.8}
• vol_gate_type ∈ {ATR_GT_ATRMA, ATR_PERCENTILE}
• atr_ma_length ∈ {20, 30} (if ATR_GT_ATRMA)
• atr_percentile_threshold ∈ {60, 70} (if ATR_PERCENTILE)
• rsi_reference ∈ {45, 50, 55}
• bundle_version_id
• active_from_timestamp
• generated_by (deployment optimiser or monthly optimiser)
• training_window, validation_window metadata

3.2 IndicatorSnapshot (per instrument)
• 1H: EMA200, HTF ATR (for buffer)
• 15m: ATR14, ATRMA, ATR percentile, RSI
• Timestamps for last fully closed candles

3.3 EligibleSignal (per instrument)
• Instrument
• Direction (LONG or SHORT)
• Timestamp (must equal 15m candle close)
• Scores for selection hierarchy:
• trend_strength_score
• vol_expansion_score
• liquidity rank
• Reasons for eligibility

3.4 TradePlan (output of sizing)
• Instrument, direction
• Entry type (market)
• Stop price (ATR-based)
• TP price (exactly 2R)
• Quantity and margin requirement at 1x
• Risk intent amount (0.5% equity)
• Realised risk at stop after capital constraint

3.5 PositionState (global, single)
• Instrument, direction, entry price, qty
• Stop and TP order ids
• R value (stop distance) frozen at entry
• Trailing status (enabled only after ≥1R)
• Cooldown counters (consecutive losses)
• Current mode: FLAT, OPEN, CLOSING, HALTED

⸻

4. Determinism and Invariants (Must Always Hold)

4.1 Exchange mode invariants
• Margin mode is isolated
• Leverage is exactly 1x
• If mismatch detected, system enters HALTED and blocks new entries

4.2 Execution invariants
• No intrabar entries
• No entry without stop and TP placement workflow
• Only one open position globally at any time

4.3 Risk invariants
• Intended loss at stop = 0.5% of total equity
• Capital constraint:
• If required margin exceeds available equity, use all available equity
• Realised loss at stop < 0.5% total equity
• No behaviour may increase leverage or risk percentage to satisfy risk intent

4.4 TP invariants
• TP is exactly 2R, where R is the stop distance at entry
• TP must not be modified except by closing the position

4.5 Optimisation invariants
• Per instrument parameter bundles only
• Optimisation runs only at:
• Deployment
• First calendar day of each month
• Parameters must not change mid-position
• Only discrete allowed sets may be used

4.6 Cooldown invariant
• After 2 consecutive losing trades, no new entries until next 1H candle closes

⸻

5. Regime Exit Specification (No time-based exits)

A position must close when any is true:

1. HTF trend invalidates (price crosses into opposite side beyond buffer)
2. Volatility gate fails (expansion no longer true)
3. Momentum continuation fails (RSI condition no longer satisfied)
4. Funding becomes extreme against the position
5. Safety Supervisor triggers kill switch

Notes:
• These checks run on candle close and on relevant events (funding updates, safety events)
• Exit action is deterministic: close position with market order, cancel remaining orders

⸻

6. Monthly Optimisation Subsystem Specification

6.1 Trigger schedule
• Deployment initial run
• Then on the first calendar day of each month (system timezone fixed, documented)

6.2 Per-instrument evaluation

For each instrument independently:
• Enumerate all allowed parameter bundles
• Backtest over fixed windows:
• Training window and validation window (lengths fixed in config, not per instrument)
• Costs:
• Include fees and slippage assumptions (fixed constants, versioned)

6.3 Selection rules

A bundle is eligible only if it passes constraints:
• Positive expectancy net costs on validation
• Meets minimum trade count threshold
• No extreme tail behaviour beyond defined thresholds
• Drawdown within guardrails

Tie-break:
• Prefer stability and lower drawdown
• Prefer continuity with current active bundle when near-equal

If no eligible bundle:
• Keep current active bundle

6.4 Output
• Writes new InstrumentParameterBundle with version id and metadata
• Emits audit log and notification summarising changes per instrument

⸻

7. Storage and Persistence

Minimum persistent stores:

1. Parameter Store
   • Current active bundle per instrument
   • Historical bundles with metadata
2. Trade Ledger
   • Every trade plan, order ids, fills, exits, realised PnL, realised R
   • Consecutive loss tracking state
3. Audit Log
   • Append-only decision logs, rejection reasons, safety events
4. System State Snapshot
   • Current PositionState
   • Cooldown state
   • Halt state and reasons

⸻

8. Observability Requirements

8.1 Metrics
• Trade count, win rate, expectancy, drawdown
• Slippage distribution
• API error rates, latency percentiles
• Signal rejection rates by reason (trend, buffer, vol gate, momentum, cooldown, safety)

8.2 Notifications
• Open, close, halt, resume
• Daily summary
• Monthly optimisation result per instrument

⸻

9. Acceptance Tests (Spec-level, no code)

The system is accepted only if the following can be demonstrated:

1. Determinism
   • Given identical candle data and parameters, the bot selects the same instrument and decision every time
2. One-position rule
   • Cannot open a second position under any signal collision scenario
3. Risk constraint correctness
   • When available equity is insufficient, size uses all available equity and realised stop loss is below 0.5% of total equity
4. No intrabar
   • Signals and entries occur only at candle close timestamps
5. TP is exactly 2R
   • For every trade, TP distance equals two times the stop distance from entry
6. No time-based exits
   • Positions never close solely due to elapsed time
7. Regime exits trigger properly
   • Each regime exit condition forces closure and is logged with the correct reason
8. Cooldown enforcement
   • After two losses, entries are blocked until next 1H candle close
9. Optimisation governance
   • Parameters change only on deployment and on the first of the month, never mid-position, and only to allowed discrete bundles
10. Safety halts
    • Leverage or margin mode mismatch forces HALTED state and blocks new entries
