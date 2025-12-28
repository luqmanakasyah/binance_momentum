Problem Boundary Contract (PBC)

System Name: Momentum Continuation Bot (HTF + ATR-Gated)
Market: Binance USD-M Perpetual Futures
Margin Mode: Isolated
Leverage: Fixed 1× only
Version: v2.2 (Final, Frozen Spec)

⸻

1. System Purpose

The system exists solely to:

Trade momentum continuation setups in liquid USD-M perpetual futures, in both long and short directions, using higher-timeframe structure and volatility expansion, with deterministic risk controls and governed automatic optimisation.

The system prioritises capital preservation, explainability, and controlled adaptation.

⸻

2. System Boundary

2.1 In Scope
• Signal generation
• Position sizing
• Order execution
• Position management
• Regime-based exits
• Automatic parameter optimisation
• Risk enforcement
• Safety halts
• Logging and notifications

2.2 Out of Scope
• Prediction or forecasting
• Continuous or intraday optimisation
• Adaptive learning during live trading
• Multi-position portfolios
• Capital transfers or withdrawals
• Manual parameter tuning
• Leverage above 1×

⸻

3. Market & Instrument Constraints

3.1 Market
• Binance USD-M perpetual futures

3.2 Instruments
• Fixed watchlist of top 10–15 contracts by liquidity
• Stablecoin-margined contracts only

3.3 Exclusions
• Newly listed contracts
• Illiquid contracts
• Exotic or experimental products

⸻

4. Margin & Leverage Rules (Hard Limits)
   • Margin mode: Isolated only
   • Leverage: Fixed at 1×
   • Dynamic or variable leverage is forbidden

⸻

5. Timeframe Architecture

Role Timeframe
Higher Timeframe (HTF) 1 Hour
Execution Timeframe (LTF) 15 Minutes

No additional timeframes are permitted.

⸻

6. Inputs (Stimuli)

The system reacts only to: 1. Completed OHLC candle closes (1H, 15m) 2. Exchange account state updates 3. Order execution reports 4. System clock events 5. OS lifecycle signals

Intrabar price movements are ignored.

⸻

7. Strategy Logic

7.1 HTF Trend Filter
• Trend defined by EMA200 on 1H
• Long bias: price > EMA200 + buffer
• Short bias: price < EMA200 − buffer
• Trades inside the buffer are forbidden

EMA Buffer
• Size = 0.25–0.5 × HTF ATR
• Volatility-scaled and deterministic

⸻

7.2 Momentum Confirmation (LTF)
• RSI on 15m
• RSI interpreted strictly as momentum continuation
• Momentum must align with HTF direction

⸻

7.3 Volatility Expansion Gate (Mandatory)

A trade is valid only if:
• ATR(14) on 15m indicates expansion, defined as:
• ATR > ATR moving average (20–30), or
• ATR percentile ≥ 55–70

Volatility contraction results in hard rejection of new trades.

⸻

8. Directional Logic

Long Trades
• HTF bullish
• Momentum continuation present
• Volatility expanding
• Funding not extreme against longs

Short Trades
• HTF bearish
• Momentum continuation present
• Volatility expanding
• Funding not extreme against shorts

No directional bias is allowed.

⸻

9. Concurrency & Signal Selection

9.1 Position Limit
• Maximum one open position at any time

9.2 Signal Collision Resolution

If multiple instruments signal on the same candle close, select exactly one using this fixed hierarchy: 1. Strongest HTF trend (distance from EMA200 normalised by ATR) 2. Strongest volatility expansion 3. Highest liquidity ranking 4. Fixed static instrument priority list

Random selection is forbidden.

⸻

10. Order Execution
    • Order type: Market only
    • Entries allowed only on candle close
    • Intrabar execution is forbidden

⸻

11. Position Sizing & Risk Management

11.1 Risk Intent
• Target maximum loss per trade = 0.5% of total equity at stop

11.2 Capital Constraint Handling (Authoritative)
• Position size is first calculated to realise a 0.5% equity loss at stop.
• If the required margin at 1× exceeds available equity:
• Use all available equity
• Accept that realised loss at stop will be less than 0.5% of total equity

This downscaling behaviour is mandatory and must not be overridden.

⸻

11.3 Stop Loss
• Stop distance = ATR-based
• Multiplier selected via optimisation (see Section 16)
• Stop must be placed immediately on entry
• Stop must be meaningfully above liquidation price

⸻

11.4 Take Profit (Deterministic)
• Take profit placed at exactly 2R
• R = stop distance
• TP fixed at order creation
• No discretionary or variable TP permitted
• Optional trailing allowed only after ≥1R unrealised profit

⸻

12. Exit Conditions (No Time-Based Exit)

A position must be closed if any of the following occurs: 1. Stop loss hit 2. Take profit hit 3. HTF trend invalidates 4. Volatility regime contracts 5. Momentum continuation fails 6. Funding becomes extreme against the position 7. Safety kill switch triggers

Time-based exits are explicitly forbidden.

⸻

13. Cooldown Rule
    • After 2 consecutive losing trades:
    • Suspend all new entries
    • Resume trading only after the next HTF candle closes

The cooldown applies globally.

⸻

14. Safety & Kill Switches

The system must halt new entries if:
• API error rate exceeds threshold
• Margin or account state becomes inconsistent
• Latency exceeds safe bounds
• Liquidation buffer becomes invalid
• Position mode or leverage deviates from specification

Existing positions may be closed but not added to.

⸻

15. Observability & Auditability

15.1 Logging

Each decision must log:
• Trend state
• Momentum state
• Volatility state
• Instrument-specific parameters in use
• Position sizing calculation
• Trade acceptance or rejection reason
• Exit rationale

15.2 Notifications
• Trade opened
• Trade closed
• Safety halt triggered
• Daily summary
• Monthly optimisation result

⸻

16. Automatic Optimisation Subsystem (Authoritative)

16.1 Scope of Optimisation
• Each instrument has its own independent parameter set
• Parameters are selected automatically, not manually

16.2 Optimisable Parameters (Discrete, Pre-Approved)

Only the following may be optimised:
• ATR stop multiplier: {1.2, 1.4, 1.6, 1.8}
• Volatility gate definition:
• ATR > ATR-MA (MA length ∈ {20, 30}), or
• ATR percentile ∈ {60, 70}
• RSI continuation reference level: {45, 50, 55}

No other parameters may be optimised.

⸻

16.3 Optimisation Schedule
• Once at initial deployment
• Thereafter, automatically on the first calendar day of each month
• Optimisation runs offline only
• Live trading continues using the last active parameter set until a new one is approved

⸻

16.4 Optimisation Methodology

For each instrument:
• Training window: recent fixed historical window (e.g. 120–180 days)
• Validation window: subsequent fixed window (e.g. 30–45 days)
• Candidate parameter sets evaluated only from the pre-approved discrete set

⸻

16.5 Selection Criteria

A parameter set is eligible only if it:
• Meets drawdown and trade-count minimums
• Exhibits positive expectancy net of fees
• Does not show extreme tail losses

If multiple sets qualify:
• Prefer the most stable (lower drawdown, lower variance)
• Prefer continuity with the current active set

⸻

16.6 Deployment & Governance
• New parameter sets take effect only after optimisation completes
• Parameter changes:
• Are logged
• Are versioned per instrument
• Must not be applied mid-position
• If optimisation fails or produces no valid candidate:
• Retain the existing parameter set

Automatic rollback is permitted if safety thresholds are breached.

⸻

17. Validation Requirements

Backtesting
• Minimum 2–3 years of data per instrument
• Fees and slippage included
• Strategy rejected if:
• Max drawdown > 20%
• Profit factor < 1.3

Forward Testing
• Paper trading before initial live deployment
• Live trading begins with conservative capital

⸻

18. Explicit Prohibitions

The system must never:
• Use leverage above 1×
• Use cross margin
• Optimise intraday or continuously
• Optimise parameters outside the approved discrete sets
• Change parameters mid-trade
• Open multiple positions
• Trade without a stop
• Exit purely due to elapsed time
• Bypass safety halts

⸻

19. Success Definition

The system is successful if it:
• Preserves capital across regimes
• Demonstrates positive expectancy per instrument
• Adapts slowly and predictably
• Remains deterministic and auditable
• Fails safely under all foreseeable errors

⸻

20. Binding Design Principle

Optimisation is selection, not learning.
Governance is more important than performance.
