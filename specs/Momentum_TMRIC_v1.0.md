Test Matrix and Runtime Invariants Checklist v1.0

Applies to: PBC v2.2 and SAS v1.0
Goal: Map every binding clause to concrete tests and runtime assertions, so the implementation cannot drift.

⸻

1. Runtime Invariants Checklist (Must always hold)

These are assertions the system should continuously enforce. If any invariant is violated, the system must enter HALTED and block new entries (and optionally close any open position if safety-critical).

1.1 Exchange Mode and Account Safety
• INV-EX-001: Margin mode is Isolated for every instrument traded.
• INV-EX-002: Leverage is exactly 1x for every instrument traded.
• INV-EX-003: Position mode and margin configuration match expected settings before any order placement.
• INV-EX-004: No API key permissions beyond trading are required. Withdrawals are not used.

1.2 Determinism and Time Discipline
• INV-TM-001: The strategy evaluates entries only on completed 15m candle closes.
• INV-TM-002: HTF state updates only on completed 1H candle closes.
• INV-TM-003: No intrabar entry decisions. If intrabar data is received, it must not trigger signals.

1.3 Position Concurrency
• INV-POS-001: At most one open position globally at any time.
• INV-POS-002: If a position is OPEN or CLOSING, the entry subsystem must reject all new entries.
• INV-POS-003: Selector must choose 0 or 1 instrument per 15m candle close. Never more.

1.4 Risk and Sizing
• INV-RSK-001: Risk intent is fixed at 0.5% of total equity at stop.
• INV-RSK-002: Capital constraint rule is enforced: if required margin exceeds available equity, use all available equity, resulting realised stop loss below 0.5%.
• INV-RSK-003: No leverage increase may be used to satisfy risk intent.
• INV-RSK-004: Every opened position must have a valid stop and TP placement workflow.

1.5 TP and SL Correctness
• INV-TP-001: TP is placed at exactly 2R where R is the stop distance at entry.
• INV-TP-002: R is frozen at entry and never redefined during the trade.
• INV-SL-001: Stop distance is ATR-based using the instrument’s current parameter bundle.
• INV-SL-002: Stop must be placed immediately after entry acknowledgement, within a bounded time budget. If not possible, close position and halt.

1.6 Regime Gating and Exits
• INV-GATE-001: No entries when volatility expansion gate is false.
• INV-GATE-002: No entries when price is inside EMA200 buffer zone.
• INV-EXIT-001: No time-based exits exist.
• INV-EXIT-002: Any regime exit trigger must result in a deterministic close action and audit log.

1.7 Cooldown Behaviour
• INV-CD-001: After 2 consecutive losing trades, the system blocks new entries.
• INV-CD-002: Cooldown ends only after the next 1H candle closes.
• INV-CD-003: Cooldown applies globally across all instruments.

1.8 Optimisation Governance
• INV-OPT-001: Parameters are per instrument and must be loaded from the Parameter Store.
• INV-OPT-002: Optimisation may run only at deployment and on the first calendar day of each month.
• INV-OPT-003: Optimiser can only select from the approved discrete parameter set.
• INV-OPT-004: Parameter bundle changes must not occur mid-position.
• INV-OPT-005: If optimisation fails or yields no eligible candidate, retain current bundle.

1.9 Safety Supervisor
• INV-SAF-001: If leverage or margin mode mismatch is detected, halt entries immediately.
• INV-SAF-002: If account state is inconsistent (position unknown, order state ambiguous), halt entries.
• INV-SAF-003: If API error rate or latency exceeds thresholds, halt entries.
• INV-SAF-004: Every halt must generate an audit record and notification.

⸻

2. Test Matrix (Spec-level tests, no code)

Each test includes: ID, objective, setup, stimulus, expected behaviour, and PBC mapping.

2.1 Exchange Mode and Leverage

T-EX-001: Enforce isolated margin
• Objective: Ensure only isolated margin is used.
• Setup: Exchange returns cross margin mode for a target instrument.
• Stimulus: Attempt to evaluate and place an entry.
• Expected: Bot enters HALTED, blocks entries, logs violation.
• Maps to: PBC 4, 14, 18.

T-EX-002: Enforce 1x leverage
• Setup: Exchange reports leverage set to 2x.
• Stimulus: Entry decision event at 15m close.
• Expected: HALTED, no order placement, notification raised.
• Maps to: PBC 4, 14, 18.

⸻

2.2 Candle Close Discipline and Determinism

T-TM-001: No intrabar entries
• Setup: Provide intrabar ticks that would satisfy momentum conditions.
• Stimulus: Intrabar events only.
• Expected: No signals emitted, no orders placed, log indicates intrabar ignored.
• Maps to: PBC 6, 10.

T-TM-002: Deterministic replay
• Setup: Fixed historical candles, fixed parameter bundles, fixed account state.
• Stimulus: Replay same data twice.
• Expected: Identical eligible signals, identical selection, identical trade plan.
• Maps to: PBC 6, 9, 15.

⸻

2.3 Trend Filter and EMA Buffer

T-TR-001: Reject inside buffer zone
• Setup: Price within EMA200 ± buffer; other conditions true.
• Stimulus: 15m candle close evaluation.
• Expected: Hard rejection, logged reason “EMA buffer”.
• Maps to: PBC 7.1.

T-TR-002: Long only above buffer
• Setup: HTF bullish beyond buffer; other gates true.
• Stimulus: 15m close.
• Expected: Long eligible signals possible; short signals rejected.
• Maps to: PBC 7.1, 8.

T-TR-003: Short only below buffer
• Mirrors T-TR-002 for shorts.
• Maps to: PBC 7.1, 8.

⸻

2.4 Volatility Expansion Gate

T-VOL-001: Reject when contraction
• Setup: ATR gate false; trend and momentum true.
• Stimulus: 15m close.
• Expected: No entry, logged “volatility gate”.
• Maps to: PBC 7.3.

T-VOL-002: Accept only when expansion
• Setup: ATR gate true.
• Stimulus: 15m close.
• Expected: Eligible signal emitted if other conditions satisfied.
• Maps to: PBC 7.3.

⸻

2.5 Signal Collision Selection

T-SEL-001: Multiple instruments signal, choose one deterministically
• Setup: Two or more instruments eligible at same candle close with different scores.
• Stimulus: 15m close evaluation.
• Expected: Exactly one chosen, based on the hierarchy, stable across replays.
• Maps to: PBC 9.2.

T-SEL-002: Tie-break stability
• Setup: Equal trend and vol scores; different liquidity and static priority.
• Expected: Higher liquidity wins, else static priority wins.
• Maps to: PBC 9.2.

⸻

2.6 One Position Rule

T-POS-001: Block entries when position open
• Setup: PositionState = OPEN.
• Stimulus: New 15m close with eligible signal.
• Expected: Entry blocked with logged reason “position already open”.
• Maps to: PBC 9.1, 18.

T-POS-002: Prevent double open on partial fill confusion
• Setup: Entry order acknowledged but fills delayed.
• Stimulus: Next candle produces another signal.
• Expected: Blocked because state is OPEN or OPENING, no second entry.
• Maps to: PBC 9.1, 14.

⸻

2.7 Risk and Capital Constraint

T-RSK-001: Normal sizing hits 0.5% risk
• Setup: Adequate available equity.
• Stimulus: Create trade plan.
• Expected: Planned loss at stop equals 0.5% total equity (within rounding tolerance).
• Maps to: PBC 11.1, 11.2.

T-RSK-002: Insufficient equity uses all available equity
• Setup: Available equity too small to fund size needed for 0.5% risk.
• Expected: Position uses all available equity; realised stop loss < 0.5% total equity; logged “capital constrained”.
• Maps to: PBC 11.2.

T-RSK-003: No leverage increase to satisfy risk
• Setup: Capital constrained scenario.
• Expected: Bot does not change leverage, does not increase risk percent, simply downsizes.
• Maps to: PBC 4, 11.2, 18.

⸻

2.8 Stop and TP Placement

T-ORD-001: Stop required
• Setup: Simulate stop placement failure after entry.
• Expected: Bot closes position immediately and halts; logs “protective stop failure”.
• Maps to: PBC 11.3, 14, 18.

T-TP-001: TP equals exactly 2R
• Setup: Known entry and stop distance.
• Expected: TP distance equals 2 × stop distance exactly (within tick size rounding rules that are deterministic and logged).
• Maps to: PBC 11.4.

⸻

2.9 Regime Exits (No time exits)

T-EXIT-001: Trend invalidation exit
• Setup: Position open; HTF crosses into invalid regime beyond buffer.
• Expected: Close position; log reason “HTF trend invalidation”.
• Maps to: PBC 12.3.

T-EXIT-002: Volatility contraction exit
• Setup: Position open; ATR gate becomes false.
• Expected: Close; reason “volatility contraction”.
• Maps to: PBC 12.4.

T-EXIT-003: Momentum failure exit
• Setup: Position open; RSI continuation condition fails.
• Expected: Close; reason “momentum failure”.
• Maps to: PBC 12.5.

T-EXIT-004: Funding extreme exit
• Setup: Position open; funding becomes extreme against direction.
• Expected: Close; reason “funding extreme”.
• Maps to: PBC 12.6.

T-EXIT-005: No time-based exit
• Setup: Position open; nothing triggers; long time passes.
• Expected: Position remains until SL, TP, or regime exit triggers. No closure due to elapsed time.
• Maps to: PBC 12, 18.

⸻

2.10 Cooldown Rule

T-CD-001: Enter cooldown after 2 losses
• Setup: Two consecutive losing trades recorded.
• Expected: Entries blocked, logged “cooldown active”.
• Maps to: PBC 13.

T-CD-002: Resume only after next 1H close
• Setup: Cooldown active.
• Stimulus: 15m close events before next 1H close.
• Expected: No entries.
• Stimulus: Next 1H candle close occurs.
• Expected: Cooldown lifted; entries allowed again.
• Maps to: PBC 13.

⸻

2.11 Optimisation Subsystem

T-OPT-001: Per-instrument parameters
• Setup: Two instruments, distinct bundles stored.
• Expected: Signals and sizing use the correct bundle per instrument.
• Maps to: PBC 16.1, 15.1.

T-OPT-002: Optimise at deployment
• Setup: Fresh deployment with no active bundles.
• Expected: Optimiser runs once, writes bundles, logs outcomes.
• Maps to: PBC 16.3.

T-OPT-003: Optimise on first of month
• Setup: Simulate system clock reaching first day.
• Expected: Optimiser runs, updates bundles only after completion, not mid-position.
• Maps to: PBC 16.3, 16.6.

T-OPT-004: Discrete set enforcement
• Setup: Optimiser attempts to propose an out-of-set value.
• Expected: Reject proposal, keep current bundle, log violation.
• Maps to: PBC 16.2, 18.

T-OPT-005: No mid-position change
• Setup: Open position; optimisation completes.
• Expected: New bundle marked active only for future trades after position closes.
• Maps to: PBC 16.6, 18.

T-OPT-006: Optimisation failure
• Setup: Optimiser crashes or yields no eligible candidate.
• Expected: Retain existing bundle, log “optimisation failed or no candidate”.
• Maps to: PBC 16.6.

⸻

2.12 Safety Supervisor

T-SAF-001: API error halt
• Setup: Inject elevated API error rate.
• Expected: HALTED, no new entries, notification sent.
• Maps to: PBC 14.

T-SAF-002: State mismatch halt
• Setup: Exchange reports a position that local state does not recognise.
• Expected: HALTED; reconcile workflow invoked; no new entries.
• Maps to: PBC 14.

T-SAF-003: Latency halt
• Setup: Latency threshold exceeded.
• Expected: HALTED; no new entries.
• Maps to: PBC 14.

⸻

3. Spec Decisions That Must Be Documented Before Implementation

These are not code, but they must be fixed in the implementation spec so tests can be exact:

1. Funding “extreme” definition
   A deterministic rule and thresholds, direction-specific, and how frequently it updates.
2. Tick size and rounding policy
   Deterministic rounding rules for stop and TP prices. Must be logged.
3. Fee and slippage constants used by optimiser
   Values and versioning. Must be consistent per run.
4. Optimisation windows
   Exact training and validation lengths and cutoffs.
5. Minimum trade count threshold per instrument
   Needed for optimisation eligibility.
6. Kill switch thresholds
   Error rate, latency, and inconsistency definitions.
