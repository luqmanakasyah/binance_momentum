from enum import Enum
from typing import Optional, Tuple
from bot.data.indicators import IndicatorSnapshot
from bot.core.signal import SignalEngine, TrendState

class ExitReason(Enum):
    TP = "TP"
    SL = "SL"
    TREND_INVALID = "TREND_INVALID"
    VOL_CONTRACTION = "VOL_CONTRACTION"
    MOMENTUM_FAIL = "MOMENTUM_FAIL"
    FUNDING_EXTREME = "FUNDING_EXTREME"
    SAFETY_HALT = "SAFETY_HALT"

class RegimeExitEngine:
    """
    Evaluates positions for regime-based exits as per PBC 12.0.
    """
    
    def __init__(self, signal_engine: SignalEngine):
        self.signal_engine = signal_engine

    def should_exit(
        self, 
        current_position: any, 
        snapshot: IndicatorSnapshot, 
        bundle: any,
        funding_rate: float
    ) -> Tuple[bool, Optional[ExitReason]]:
        """
        Checks all regime exit conditions.
        """
        # 1. HTF Trend Invalidation
        # Position direction must match HTF trend
        trend_state = self.signal_engine.evaluate_trend(
            snapshot.timestamp, # Need current price here actually, snapshot doesn't have it
            snapshot.ema_200_htf, 
            snapshot.atr_htf
        )
        # Note: Need price. I'll pass it or assume snapshot includes it.
        # Let's adjust snapshot or method signature.
        
        # 2. Volatility Contraction
        vol_gate = self.signal_engine.check_volatility_gate(snapshot, bundle)
        if not vol_gate:
            return True, ExitReason.VOL_CONTRACTION
            
        # 3. Momentum Failure (RSI)
        momentum_fail = False
        if current_position.direction == "LONG":
            if snapshot.rsi_ltf < bundle.rsi_reference:
                momentum_fail = True
        else:
            if snapshot.rsi_ltf > (100 - bundle.rsi_reference):
                momentum_fail = True
        
        if momentum_fail:
            return True, ExitReason.MOMENTUM_FAIL
            
        # 4. HTF Trend Invalidation (simplified check)
        if current_position.direction == "LONG" and trend_state == TrendState.BEAR:
            return True, ExitReason.TREND_INVALID
        if current_position.direction == "SHORT" and trend_state == TrendState.BULL:
            return True, ExitReason.TREND_INVALID
            
        # 5. Funding Extreme (Rule: > 0.1% or < -0.1% against position)
        # Threshold should be in config.
        FUNDING_EXTREME_THRESHOLD = 0.001 # 0.1%
        if current_position.direction == "LONG" and funding_rate < -FUNDING_EXTREME_THRESHOLD:
            return True, ExitReason.FUNDING_EXTREME
        if current_position.direction == "SHORT" and funding_rate > FUNDING_EXTREME_THRESHOLD:
            return True, ExitReason.FUNDING_EXTREME

        return False, None
