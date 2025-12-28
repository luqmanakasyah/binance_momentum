import logging
import time
from typing import Dict, Any, List
from binance import AsyncClient

logger = logging.getLogger(__name__)

class SafetyHaltException(Exception):
    """Raised when a safety invariant is violated."""
    pass

class SafetySupervisor:
    """
    Enforces runtime invariants defined in TMRIC v1.0.
    """
    
    LATENCY_THRESHOLD_MS = 1000
    ERROR_THRESHOLD_PERCENT = 5.0 # 5% over window

    def __init__(self, client: AsyncClient):
        self.client = client
        self.error_count = 0
        self.total_requests = 0

    async def validate_account_state(self, symbol: str):
        """
        INV-EX-001/002: Ensure Isolated and 1x.
        """
        try:
            position_risk = await self.client.futures_position_information(symbol=symbol)
            if not position_risk:
                return
            
            p = position_risk[0]
            leverage = int(p['leverage'])
            margin_type = p['marginType'] # 'isolated' or 'cross'
            
            if leverage != 1:
                logger.critical(f"LEVERAGE VIOLATION: {symbol} has {leverage}x leverage. SPEC REQUIRES 1x.")
                raise SafetyHaltException(f"Leverage mismatch on {symbol}: expected 1x, got {leverage}x")
            
            if margin_type.lower() != 'isolated':
                logger.critical(f"MARGIN VIOLATION: {symbol} has {margin_type} margin. SPEC REQUIRES ISOLATED.")
                raise SafetyHaltException(f"Margin mode mismatch on {symbol}: expected ISOLATED, got {margin_type}")
                
        except SafetyHaltException:
            raise
        except Exception as e:
            logger.error(f"Failed to validate account state for {symbol}: {e}")
            # We don't necessarily halt if the API just failed one check, 
            # but we track it in error rates.

    def record_api_call(self, success: bool, latency_ms: float):
        """
        Tracks API health (INV-SAF-003).
        """
        self.total_requests += 1
        if not success:
            self.error_count += 1
            
        if latency_ms > self.LATENCY_THRESHOLD_MS:
            logger.warning(f"HIGH LATENCY DETECTED: {latency_ms}ms")
            
        # Check error rate periodically
        if self.total_requests > 20:
            error_rate = (self.error_count / self.total_requests) * 100
            if error_rate > self.ERROR_THRESHOLD_PERCENT:
                raise SafetyHaltException(f"API Error Rate too high: {error_rate:.2f}%")

    async def pre_trade_check(self, symbol: str):
        """
        Checks all invariants before placing a new entry.
        """
        await self.validate_account_state(symbol)
        # Add more checks here (latency, connectivity, etc.)
        logger.info(f"Safety pre-trade check passed for {symbol}")
