import pandas as pd
import numpy as np
from dataclasses import dataclass
from typing import Optional

@dataclass
class IndicatorSnapshot:
    symbol: str
    timestamp: pd.Timestamp
    current_price: float
    
    # HTF (1H)
    ema_200_htf: Optional[float] = None
    atr_htf: Optional[float] = None
    
    # LTF (15m)
    rsi_ltf: Optional[float] = None
    atr_ltf: Optional[float] = None
    atr_ma_ltf: Optional[float] = None
    atr_percentile_ltf: Optional[float] = None

class IndicatorEngine:
    """
    Calculates deterministic technical indicators manually to avoid dependencies.
    """

    @staticmethod
    def calculate_ema(series: pd.Series, length: int) -> pd.Series:
        return series.ewm(span=length, adjust=False).mean()

    @staticmethod
    def calculate_atr(df: pd.DataFrame, length: int) -> pd.Series:
        high = df['high']
        low = df['low']
        prev_close = df['close'].shift(1)
        
        tr = pd.concat([
            high - low,
            (high - prev_close).abs(),
            (low - prev_close).abs()
        ], axis=1).max(axis=1)
        
        # ATR uses RMA (Running Moving Average) usually
        return tr.ewm(alpha=1/length, adjust=False).mean()

    @staticmethod
    def calculate_rsi(series: pd.Series, length: int) -> pd.Series:
        delta = series.diff()
        gain = (delta.where(delta > 0, 0)).ewm(alpha=1/length, adjust=False).mean()
        loss = (-delta.where(delta < 0, 0)).ewm(alpha=1/length, adjust=False).mean()
        
        rs = gain / loss
        return 100 - (100 / (1 + rs))

    def calculate_htf_indicators(self, df_1h: pd.DataFrame) -> pd.Series:
        if len(df_1h) < 200:
            return pd.Series()
            
        ema = self.calculate_ema(df_1h['close'], 200)
        atr = self.calculate_atr(df_1h, 14)
        
        return pd.Series({
            'EMA_200': ema.iloc[-1],
            'ATR_14': atr.iloc[-1]
        })

    def calculate_ltf_indicators(
        self, 
        df_15m: pd.DataFrame, 
        atr_ma_length: int = 20,
        atr_percentile_lookback: int = 100
    ) -> pd.Series:
        if len(df_15m) < max(14, atr_ma_length):
            return pd.Series()

        rsi = self.calculate_rsi(df_15m['close'], 14)
        atr = self.calculate_atr(df_15m, 14)
        atr_ma = atr.rolling(window=atr_ma_length).mean()
        
        atr_percentile = atr.rolling(window=atr_percentile_lookback).apply(
            lambda x: pd.Series(x).rank(pct=True).iloc[-1] * 100
        )
        
        return pd.Series({
            'rsi': rsi.iloc[-1],
            'atr': atr.iloc[-1],
            'atr_ma': atr_ma.iloc[-1],
            'atr_percentile': atr_percentile.iloc[-1]
        })

    def get_snapshot(
        self, 
        symbol: str, 
        df_1h: pd.DataFrame, 
        df_15m: pd.DataFrame,
        atr_ma_length: int = 20
    ) -> IndicatorSnapshot:
        htf = self.calculate_htf_indicators(df_1h)
        ltf = self.calculate_ltf_indicators(df_15m, atr_ma_length=atr_ma_length)
        
        return IndicatorSnapshot(
            symbol=symbol,
            timestamp=df_15m.index[-1],
            current_price=float(df_15m.iloc[-1]['close']),
            ema_200_htf=htf.get('EMA_200'),
            atr_htf=htf.get('ATR_14'),
            rsi_ltf=ltf.get('rsi'),
            atr_ltf=ltf.get('atr'),
            atr_ma_ltf=ltf.get('atr_ma'),
            atr_percentile_ltf=ltf.get('atr_percentile')
        )
