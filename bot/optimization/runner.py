import logging
import itertools
import pandas as pd
import numpy as np
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from bot.data.indicators import IndicatorEngine
from bot.core.signal import SignalEngine, TrendState
from bot.core.risk import RiskEngine

logger = logging.getLogger(__name__)

@dataclass
class BacktestResult:
    total_r: float
    win_rate: float
    max_drawdown: float
    trade_count: int
    expectancy: float

class OptimizationRunner:
    """
    Implements PBC v2.2 section 16: Automatic Optimisation.
    """
    
    # Approved Discrete Sets (PBC 16.2)
    STOP_MULTIPLIERS = [1.2, 1.4, 1.6, 1.8]
    RSI_REFERENCES = [45, 50, 55]
    VOL_GATE_CONFIGS = [
        {"type": "ATR_GT_ATRMA", "ma_length": 20},
        {"type": "ATR_GT_ATRMA", "ma_length": 30},
        {"type": "ATR_PERCENTILE", "threshold": 60},
        {"type": "ATR_PERCENTILE", "threshold": 70},
    ]

    def __init__(self, indicator_engine: IndicatorEngine, signal_engine: SignalEngine):
        self.indicator_engine = indicator_engine
        self.signal_engine = signal_engine

    def run_backtest(
        self, 
        df_1h: pd.DataFrame, 
        df_15m: pd.DataFrame, 
        bundle_params: Dict[str, Any]
    ) -> BacktestResult:
        """
        Simplified vector-ish backtest for a specific parameter bundle.
        Note: True strategy has one-position limit globally, but for 
        per-instrument optimization, we backtest each instrument in isolation.
        """
        # 1. Pre-calculate indicators
        ltr_ma = bundle_params.get("ma_length", 20)
        
        # We need a mock bundle object for the signal engine
        class MockBundle:
            def __init__(self, p):
                self.atr_stop_multiplier = p["stop_multiplier"]
                self.rsi_reference = p["rsi_reference"]
                self.vol_gate_type = p["type"]
                self.atr_ma_length = p.get("ma_length")
                self.atr_percentile_threshold = p.get("threshold")

        m_bundle = MockBundle(bundle_params)
        
        # Calculate full series of indicators
        # (This is more efficient than row-by-row        # Calculate full series of indicators
        df = df_15m.copy()
        df['rsi'] = self.indicator_engine.calculate_rsi(df['close'], 14)
        df['atr'] = self.indicator_engine.calculate_atr(df, 14)
        
        if m_bundle.vol_gate_type == "ATR_GT_ATRMA":
            df['vol_gate_ref'] = df['atr'].rolling(window=m_bundle.atr_ma_length).mean()
        else:
            # Simple percentile logic
            df['vol_gate_ref'] = df['atr'].rolling(window=100).apply(
                lambda x: pd.Series(x).rank(pct=True).iloc[-1] * 100
            )

        # 1H indicators
        df_1h_clean = df_1h.copy()
        df_1h_clean['EMA_200'] = self.indicator_engine.calculate_ema(df_1h_clean['close'], 200)
        df_1h_clean['ATR_14'] = self.indicator_engine.calculate_atr(df_1h_clean, 14)
        
        # Resample 1H data to 15m for alignment
        # Use ffill to make 1H data available at 15m intervals
        df_1h_resampled = df_1h_clean[['EMA_200', 'ATR_14']].resample('15min').ffill()
        df = df.join(df_1h_resampled, rsuffix='_htf')

        trades = []
        in_position = False
        entry_price = 0
        direction = ""
        r_value = 0
        
        for i in range(200, len(df)): # Start after EMA200 warmup
            row = df.iloc[i]
            
            if not in_position:
                # Signal logic
                # HTF Trend
                buffer = 0.5 * row['ATR_14']
                trend = TrendState.NEUTRAL_BUFFER
                if row['close'] > (row['EMA_200'] + buffer): trend = TrendState.BULL
                elif row['close'] < (row['EMA_200'] - buffer): trend = TrendState.BEAR
                
                # Vol gate
                vol_pass = False
                if m_bundle.vol_gate_type == "ATR_GT_ATRMA":
                    vol_pass = row['atr'] > row['vol_gate_ref']
                else:
                    vol_pass = row['vol_gate_ref'] >= m_bundle.atr_percentile_threshold
                
                # Momentum
                momentum_pass = False
                if trend == TrendState.BULL and row['rsi'] >= m_bundle.rsi_reference:
                    momentum_pass = True
                    direction = "LONG"
                elif trend == TrendState.BEAR and row['rsi'] <= (100 - m_bundle.rsi_reference):
                    momentum_pass = True
                    direction = "SHORT"
                
                if momentum_pass and vol_pass:
                    in_position = True
                    entry_price = row['close']
                    r_value = row['atr'] * m_bundle.atr_stop_multiplier
            else:
                # Exit logic
                # 1. SL/TP
                if direction == "LONG":
                    if row['low'] <= (entry_price - r_value): # SL
                        trades.append(-1.0)
                        in_position = False
                    elif row['high'] >= (entry_price + 2 * r_value): # TP
                        trades.append(2.0)
                        in_position = False
                else:
                    if row['high'] >= (entry_price + r_value): # SL
                        trades.append(-1.0)
                        in_position = False
                    elif row['low'] <= (entry_price - 2 * r_value): # TP
                        trades.append(2.0)
                        in_position = False
                
                # (Ignoring regime exits in simple optimization backtest for speed, 
                # as they are emergency/safety measures mostly)
        
        if not trades:
            return BacktestResult(0, 0, 0, 0, 0)
            
        trades = np.array(trades)
        total_r = trades.sum()
        win_rate = (trades > 0).mean()
        
        # Simple DD calculation (cumulative R)
        cum_r = trades.cumsum()
        max_r = np.maximum.accumulate(cum_r)
        dd = max_r - cum_r
        max_dd = dd.max()
        
        return BacktestResult(
            total_r=total_r,
            win_rate=win_rate,
            max_drawdown=max_dd,
            trade_count=len(trades),
            expectancy=total_r / len(trades)
        )

    def optimize_instrument(
        self, 
        df_1h: pd.DataFrame, 
        df_15m: pd.DataFrame
    ) -> Optional[Dict[str, Any]]:
        """
        Runs grid search and selects the best bundle.
        """
        best_score = -float('inf')
        best_params = None
        
        combinations = list(itertools.product(
            self.STOP_MULTIPLIERS,
            self.RSI_REFERENCES,
            self.VOL_GATE_CONFIGS
        ))
        
        for stop_mult, rsi_ref, vol_cfg in combinations:
            params = {
                "stop_multiplier": stop_mult,
                "rsi_reference": rsi_ref,
                **vol_cfg
            }
            
            result = self.run_backtest(df_1h, df_15m, params)
            
            # Selection Criteria (PBC 16.5)
            # - Positive expectancy (Net of fees - 0.1 R per trade roughly)
            # - Min trade count (e.g. 5)
            # - Stability (Higher Total R / Max DD)
            
            if result.trade_count < 5:
                continue
                
            score = (result.total_r - (result.trade_count * 0.1)) / (result.max_drawdown + 1.0)
            
            if score > best_score:
                best_score = score
                best_params = {**params, "result": result}
                
        return best_params
