from dataclasses import dataclass
from typing import Tuple
from bot.core.signal import EligibleSignal

@dataclass
class TradePlan:
    symbol: str
    direction: str
    entry_price: float
    stop_price: float
    tp_price: float
    qty: float
    r_value: float
    risk_amount: float
    margin_required: float
    capital_constrained: bool

class RiskEngine:
    """
    Implements PBC 11.x Risk and Sizing logic.
    """
    
    RISK_PERCENT = 0.005  # 0.5% of total equity
    TP_R_MULTIPLIER = 2.0  # TP is exactly 2R

    def calculate_trade_plan(
        self, 
        signal: EligibleSignal, 
        price: float, 
        atr_ltf: float, 
        atr_stop_multiplier: float,
        total_equity: float,
        available_equity: float
    ) -> TradePlan:
        """
        Calculates sizes and levels for a new trade.
        """
        # 1. Stop Distance (R)
        r_value = atr_ltf * float(atr_stop_multiplier)
        
        # 2. Stop and TP Prices
        if signal.direction == "LONG":
            stop_price = price - r_value
            tp_price = price + (r_value * self.TP_R_MULTIPLIER)
        else:
            stop_price = price + r_value
            tp_price = price - (r_value * self.TP_R_MULTIPLIER)
            
        # 3. Target Risk Amount
        target_risk_amount = total_equity * self.RISK_PERCENT
        
        # 4. Ideal Quantity (for 0.5% risk)
        # Risk = Qty * |Entry - Stop|
        # Qty = Risk / R
        ideal_qty = target_risk_amount / r_value
        
        # 5. Margin Constraint (1x Leverage)
        # Margin Required = Qty * Entry (at 1x)
        ideal_margin_required = ideal_qty * price
        
        margin_to_use = ideal_margin_required
        capital_constrained = False
        
        # PBC 11.2: If required margin exceeds available equity, use all available equity
        if ideal_margin_required > available_equity:
            margin_to_use = available_equity
            capital_constrained = True
            
        # 6. Final Quantity and Realised Risk
        final_qty = margin_to_use / price
        realised_risk = final_qty * r_value

        return TradePlan(
            symbol=signal.symbol,
            direction=signal.direction,
            entry_price=price,
            stop_price=stop_price,
            tp_price=tp_price,
            qty=final_qty,
            r_value=r_value,
            risk_amount=realised_risk,
            margin_required=margin_to_use,
            capital_constrained=capital_constrained
        )
