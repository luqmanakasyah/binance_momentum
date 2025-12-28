
# Execution and Failure Handling Specification v1.0

**Applies to:** PBC v2.2, SAS v1.0, Test Matrix v1.0, Data Schema v1.0  
**System:** Momentum Continuation Bot (HTF + ATR-Gated)  
**Market:** Binance USD-M Perpetual Futures (Isolated, 1x)

---

## 1. Purpose

This document specifies **exact execution sequencing, idempotency rules, and failure handling logic** so that:
- No trade is opened without protection
- No duplicate or phantom orders occur
- Exchange and local state remain reconcilable
- All failure modes degrade safely

This specification is binding and implementation-facing.

---

## 2. Order Roles and Lifecycle

Each trade consists of up to four logical order roles:

1. **ENTRY** – Market order to open position  
2. **STOP** – Protective stop-loss order  
3. **TP** – Fixed take-profit order at exactly 2R  
4. **CLOSE** – Market order used for regime exits or emergency closure

Each role produces one or more `order_event` records.

---

## 3. Idempotency and Client Order IDs

### 3.1 Client Order ID Scheme (Mandatory)

Every order sent to the exchange must include a deterministic `client_order_id`:

Format:
```
<bot_id>_<trade_plan_id>_<order_role>_<attempt>
```

Examples:
- `mc_bot_abc123_ENTRY_1`
- `mc_bot_abc123_STOP_1`
- `mc_bot_abc123_TP_1`

### 3.2 Idempotency Rules

- The system must **never** submit two ENTRY orders for the same `trade_plan_id`
- Retries must increment `<attempt>`
- On restart, the bot must query open orders by `client_order_id` prefix before sending anything

---

## 4. Entry Execution Sequence (Happy Path)

### Step 1: Pre-flight Checks
Before submitting ENTRY:
- Margin mode = isolated
- Leverage = 1x
- No open or opening position exists
- System not HALTED
- Cooldown inactive

Failure → abort and log audit event.

### Step 2: Submit ENTRY (Market)
- Submit ENTRY market order
- Record `order_event` with role = ENTRY, event = SUBMITTED

### Step 3: Await ENTRY Acknowledgement
- On ACK or FILL:
  - Transition trade_plan status → FILLED (or PARTIAL if applicable)
  - Record fill price and quantity

### Step 4: Place Protective STOP and TP
Immediately after ENTRY acknowledgement:
- Submit STOP order using stop price from trade_plan
- Submit TP order at exactly 2R

These may be submitted sequentially or in parallel but must both be attempted.

---

## 5. Critical Safety Rule: Protection Guarantee

> **If either STOP or TP placement fails, the position must be closed immediately.**

### Failure Scenarios
- STOP rejected
- STOP not acknowledged within timeout
- TP rejected
- Exchange error during placement

### Mandatory Response
1. Submit CLOSE market order immediately
2. Cancel any remaining protective orders
3. Transition system to HALTED
4. Emit CRITICAL audit event

This rule is non-negotiable.

---

## 6. Partial Fills Handling

### ENTRY Partial Fill
- Treat partial fill as an OPENING position
- STOP and TP must be placed for the **filled quantity**
- If further fills occur:
  - Either adjust STOP/TP quantity deterministically, or
  - Close entire position immediately (simpler and safer)

Preferred approach for retail safety:
> **If ENTRY does not fully fill within a bounded time window, close position.**

### STOP or TP Partial Fill
- Treat as closing in progress
- Cancel opposing protective order
- Finalise position once fully closed

---

## 7. Regime Exit Execution

When a regime exit is triggered (trend invalidation, volatility contraction, momentum failure, funding extreme):

1. Cancel STOP and TP orders
2. Submit CLOSE market order
3. Record exit reason explicitly in `position.exit_reason`
4. Do not attempt to “wait” for TP or STOP

Regime exits are **decisive**, not conditional.

---

## 8. Retry and Timeout Policy

### 8.1 Timeouts (Configurable but Fixed)
- ENTRY ACK timeout
- STOP ACK timeout
- TP ACK timeout

### 8.2 Retry Rules
- ENTRY: No retry if already acknowledged or partially filled
- STOP / TP: One retry allowed
- CLOSE: Retry until confirmed or system halted

All retries must be logged with incremented attempt numbers.

---

## 9. Reconciliation on Restart

On system restart:

1. Query exchange for:
   - Open positions
   - Open orders
2. Match by `client_order_id` and instrument
3. Rebuild `PositionState`:
   - If exchange shows open position but no STOP → immediately place STOP
   - If STOP cannot be placed → CLOSE position and HALT
4. Do not open new positions until reconciliation completes

---

## 10. Failure Mode Catalogue

### F-001: Duplicate ENTRY
- Cause: Lost ACK, retry without idempotency
- Mitigation: Client order IDs + open-order query

### F-002: Naked Position
- Cause: STOP placement failure
- Mitigation: Immediate CLOSE + HALT

### F-003: Phantom Position
- Cause: Exchange filled order but local state missed it
- Mitigation: Reconciliation on restart

### F-004: Partial Fill Drift
- Cause: Partial ENTRY with no adjustment
- Mitigation: Close position if not fully filled quickly

### F-005: Exchange Outage Mid-Trade
- Cause: API unavailable
- Mitigation: HALT new entries, attempt CLOSE when possible

---

## 11. Logging and Audit Requirements

Every execution action must emit:
- `order_event` rows for every exchange interaction
- `audit_event` for:
  - Entry submission
  - Protection placement success or failure
  - Forced closes
  - Halts and resumes

Logs must include:
- trade_plan_id
- order_role
- attempt number
- raw exchange response (sanitised)

---

## 12. Acceptance Criteria

This specification is satisfied only if:

1. No position can exist without a STOP
2. No duplicate ENTRY orders can occur
3. All failures result in either a safe close or a HALT
4. Restart always leads to a reconciled, deterministic state
5. Every exit has an explicit, auditable reason

---

## 13. Final Binding Principle

> **Execution is where most bots die.  
> Protection must be boring, redundant, and uncompromising.**
