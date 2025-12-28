from enum import Enum
from dataclasses import dataclass
from typing import Optional, List
from bot.data.indicators import IndicatorSnapshot

class TrendState(Enum):
    BULL = "BULL"
    BEAR = "BEAR"
    NEUTRAL_BUFFER = "NEUTRAL_BUFFER"

class GateState(Enum):
    PASS = "PASS"
    FAIL = "FAIL"

@dataclass
class EligibleSignal:
    instrument_id: str
    symbol: str
    direction: str  # LONG or SHORT
    eval_timestamp: any
    htf_trend_state: TrendState
    vol_expansion_score: float
    trend_strength_score: float
    liquidity_rank: int

class SignalEngine:
    """
    Implements PBC v2.2 Signal Generation logic.
    """
    
    BUFFER_MULTIPLIER = 0.5  # PBC 7.1: 0.25-0.5 x HTF ATR

    def evaluate_trend(self, price: float, ema_200: float, atr_htf: float) -> TrendState:
        """
        Determines the trend state based on EMA200 and a volatility buffer.
        """
        buffer = self.BUFFER_MULTIPLIER * atr_htf
        
        if price > (ema_200 + buffer):
            return TrendState.BULL
        elif price < (ema_200 - buffer):
            return TrendState.BEAR
        else:
            return TrendState.NEUTRAL_BUFFER

    def check_volatility_gate(self, snapshot: IndicatorSnapshot, bundle: any) -> bool:
        """
        Checks if the volatility expansion gate is open.
        """
        if bundle.vol_gate_type == "ATR_GT_ATRMA":
            return snapshot.atr_ltf > (snapshot.atr_ma_ltf if snapshot.atr_ma_ltf else 0)
        elif bundle.vol_gate_type == "ATR_PERCENTILE":
            return snapshot.atr_percentile_ltf >= bundle.atr_percentile_threshold
        return False

    def evaluate_signal(
        self, 
        instrument_id: str,
        symbol: str,
        price: float, 
        snapshot: IndicatorSnapshot, 
        bundle: any,
        liquidity_rank: int
    ) -> Optional[EligibleSignal]:
        """
        Main entry point for signal evaluation.
        """
        # 1. HTF Trend Filter
        trend_state = self.evaluate_trend(price, snapshot.ema_200_htf, snapshot.atr_htf)
        
        # 2. Volatility Expansion Gate
        vol_gate = self.check_volatility_gate(snapshot, bundle)
        
        # 3. Momentum Continuation (RSI)
        # Long: RSI > rsi_reference
        # Short: RSI < (100 - rsi_reference) ??? 
        # PBC 7.2: "Momentum must align with HTF direction"
        # SAS 3.1 rsi_reference is usually 45, 50, or 55.
        momentum_pass = False
        direction = None
        
        if trend_state == TrendState.BULL:
            if snapshot.rsi_ltf >= bundle.rsi_reference:
                momentum_pass = True
                direction = "LONG"
        elif trend_state == TrendState.BEAR:
            if snapshot.rsi_ltf <= (100 - bundle.rsi_reference):
                momentum_pass = True
                direction = "SHORT"

        if momentum_pass and vol_gate:
            # Calculate scores for Selection Hierarchy (SAS 9.1/PBC 9.2)
            # 1. Strongest HTF trend (distance from EMA200 normalized by ATR)
            trend_strength = abs(price - snapshot.ema_200_htf) / snapshot.atr_htf
            
            # 2. Strongest volatility expansion (ratio to MA or raw percentile)
            vol_expansion = snapshot.atr_ltf / snapshot.atr_ma_ltf if snapshot.atr_ma_ltf else 0
            if bundle.vol_gate_type == "ATR_PERCENTILE":
                vol_expansion = snapshot.atr_percentile_ltf / 100.0

            return EligibleSignal(
                instrument_id=instrument_id,
                symbol=symbol,
                direction=direction,
                eval_timestamp=snapshot.timestamp,
                htf_trend_state=trend_state,
                vol_expansion_score=vol_expansion,
                trend_strength_score=trend_strength,
                liquidity_rank=liquidity_rank
            )
            
        return None
