import asyncio
from typing import Dict, Any, Optional
from binance import AsyncClient
from binance.enums import *

class ExchangeInterface:
    """
    Handles interactions with Binance USD-M Futures API.
    Based on EFHS v1.0.
    """
    
    def __init__(self, client: AsyncClient, bot_id: str):
        self.client = client
        self.bot_id = bot_id

    def generate_client_order_id(self, trade_plan_id: str, role: str, attempt: int = 1) -> str:
        """
        EFHS 3.1: <bot_id>_<trade_plan_id>_<order_role>_<attempt>
        """
        return f"{self.bot_id}_{trade_plan_id}_{role}_{attempt}"

    async def ensure_isolated_1x(self, symbol: str):
        """
        Enforce isolated margin and 1x leverage.
        """
        # Change leverage to 1x
        await self.client.futures_change_leverage(symbol=symbol, leverage=1)
        
        # Change margin type to ISOLATED
        try:
            await self.client.futures_change_margin_type(symbol=symbol, marginType='ISOLATED')
        except Exception as e:
            # If already isolated, or in Multi-Assets mode, Binance might throw errors.
            # code -4168 is Multi-Assets mode conflict.
            # code -4046 is already in that margin mode.
            if "No need to change margin type" in str(e) or "-4168" in str(e) or "-4046" in str(e):
                logger.info(f"Margin mode for {symbol} already isolated or Multi-Assets mode active (ignoring).")
            else:
                raise e

    async def place_market_entry(self, symbol: str, side: str, qty: float, client_id: str) -> Dict[str, Any]:
        """
        Submits a market order to open a position.
        """
        return await self.client.futures_create_order(
            symbol=symbol,
            side=side,
            type=FUTURE_ORDER_TYPE_MARKET,
            quantity=qty,
            newClientOrderId=client_id
        )

    async def place_stop_loss(self, symbol: str, side: str, stop_price: float, qty: float, client_id: str) -> Dict[str, Any]:
        """
        Submits a STOP_MARKET order.
        """
        return await self.client.futures_create_order(
            symbol=symbol,
            side=side,
            type=FUTURE_ORDER_TYPE_STOP_MARKET,
            stopPrice=stop_price,
            quantity=qty,
            newClientOrderId=client_id,
            reduceOnly=True
        )

    async def place_take_profit(self, symbol: str, side: str, tp_price: float, qty: float, client_id: str) -> Dict[str, Any]:
        """
        Submits a TAKE_PROFIT_MARKET or LIMIT order.
        Spec says "fixed TP at exactly 2R". We'll use LIMIT for TP normally.
        """
        return await self.client.futures_create_order(
            symbol=symbol,
            side=side,
            type=FUTURE_ORDER_TYPE_LIMIT,
            timeInForce=TIME_IN_FORCE_GTC,
            price=tp_price,
            quantity=qty,
            newClientOrderId=client_id,
            reduceOnly=True
        )

    async def cancel_all_orders(self, symbol: str):
        """
        Cancels all open orders for a symbol.
        """
        await self.client.futures_cancel_all_open_orders(symbol=symbol)

    async def close_position_market(self, symbol: str, side: str, qty: float, client_id: str) -> Dict[str, Any]:
        """
        Submits an emergency or regime exit market order.
        """
        return await self.client.futures_create_order(
            symbol=symbol,
            side=side,
            type=FUTURE_ORDER_TYPE_MARKET,
            quantity=qty,
            newClientOrderId=client_id,
            reduceOnly=True
        )
