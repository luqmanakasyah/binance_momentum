import asyncio
import logging
from typing import Optional
from binance.enums import SIDE_BUY, SIDE_SELL
from bot.core.risk import TradePlan
from bot.execution.exchange import ExchangeInterface

logger = logging.getLogger(__name__)

class ExecutionManager:
    """
    Orchestrates order execution and failure handling.
    Implements EFHS v1.0 sequence.
    """
    
    def __init__(self, exchange: ExchangeInterface):
        self.exchange = exchange

    async def execute_trade(self, trade_plan: TradePlan, trade_plan_id: str):
        """
        Sequence:
        1. Pre-flight checks (done by exchange wrapper)
        2. ENTRY Market
        3. Await ACK
        4. Place SL and TP
        5. If failure -> CLOSE + HALT
        """
        symbol = trade_plan.symbol
        side_entry = SIDE_BUY if trade_plan.direction == "LONG" else SIDE_SELL
        side_close = SIDE_SELL if trade_plan.direction == "LONG" else SIDE_BUY
        
        # 1. Ensure Isolated 1x
        try:
            await self.client_preflight(symbol)
        except Exception as e:
            logger.error(f"Pre-flight failed for {symbol}: {e}")
            return False

        # 2. Place ENTRY
        entry_cid = self.exchange.generate_client_order_id(trade_plan_id, "ENTRY")
        try:
            entry_res = await self.exchange.place_market_entry(
                symbol, side_entry, trade_plan.qty, entry_cid
            )
            logger.info(f"Entry order submitted: {entry_res['orderId']}")
        except Exception as e:
            logger.error(f"Entry order failed: {e}")
            return False

        # 3. Wait for Fill/ACK (Binance Market orders are usually immediate)
        # In a real system, we'd poll or wait for websocket event.
        # Here we assume success if no exception or check response.
        
        # 4. Place Protective STOP and TP
        sl_cid = self.exchange.generate_client_order_id(trade_plan_id, "STOP")
        tp_cid = self.exchange.generate_client_order_id(trade_plan_id, "TP")
        
        try:
            # Place SL and TP in parallel
            sl_task = self.exchange.place_stop_loss(
                symbol, side_close, trade_plan.stop_price, trade_plan.qty, sl_cid
            )
            tp_task = self.exchange.place_take_profit(
                symbol, side_close, trade_plan.tp_price, trade_plan.qty, tp_cid
            )
            
            results = await asyncio.gather(sl_task, tp_task, return_exceptions=True)
            
            for res in results:
                if isinstance(res, Exception):
                    raise res
                    
            logger.info("Protection orders (SL/TP) placed successfully.")
            return True

        except Exception as e:
            # EFHS 5.0: Protection Guarantee
            logger.critical(f"PROTECTION GUARANTEE TRIGGERED: {e}")
            await self.handle_protection_failure(symbol, side_close, trade_plan.qty, trade_plan_id)
            return False

    async def handle_protection_failure(self, symbol: str, side: str, qty: float, trade_plan_id: str):
        """
        Emergency close and halt.
        """
        logger.critical(f"Closing position for {symbol} due to protection placement failure.")
        
        # 1. Submit CLOSE market order
        close_cid = self.exchange.generate_client_order_id(trade_plan_id, "CLOSE_EMERGENCY")
        try:
            await self.exchange.close_position_market(symbol, side, qty, close_cid)
        except Exception as e:
            logger.error(f"Emergency close failed: {e}. MANUAL INTERVENTION REQUIRED.")
            
        # 2. Cancel remaining orders
        try:
            await self.exchange.cancel_all_orders(symbol)
        except Exception:
            pass
            
        # 3. Halt System (Logic to be implemented in Supervisor/DB)
        # This will be handled by the main coordinator raising a HaltSignal
        raise Exception("SYSTEM HALTED: Protection placement failure.")

    async def client_preflight(self, symbol: str):
        """
        Wrapper for exchange pre-flight.
        """
        await self.exchange.ensure_isolated_1x(symbol)
