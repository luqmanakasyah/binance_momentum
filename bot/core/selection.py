from typing import List, Optional
from bot.core.signal import EligibleSignal

class Selector:
    """
    Resolves simultaneous signals as per PBC 9.2.
    """

    def select_best_signal(self, signals: List[EligibleSignal]) -> Optional[EligibleSignal]:
        """
        Selects exactly one instrument to trade using a fixed hierarchy:
        1. Strongest HTF trend
        2. Strongest volatility expansion
        3. Highest liquidity ranking (lower value is better)
        4. Fixed static instrument priority list (symbol alphabetical as fallback)
        """
        if not signals:
            return None

        # Sort based on hierarchy
        # We want DESCENDING for trend strength and vol expansion
        # We want ASCENDING for liquidity rank (1 is best)
        # Note: Python sort is stable, so we sort in reverse order of priority.
        
        # 4. Fallback (symbol)
        signals.sort(key=lambda x: x.symbol)
        
        # 3. Liquidity Rank (Lower is better)
        signals.sort(key=lambda x: x.liquidity_rank)
        
        # 2. Vol Expansion Score (Higher is better)
        signals.sort(key=lambda x: x.vol_expansion_score, reverse=True)
        
        # 1. Trend Strength Score (Higher is better)
        signals.sort(key=lambda x: x.trend_strength_score, reverse=True)

        return signals[0]
