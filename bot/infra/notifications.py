import os
import httpx
import logging
import asyncio
import sys
from typing import Optional, Any
from decimal import Decimal
from telegram import Update, BotCommand
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
from bot.data.store import store
from bot.data.models import NotificationEvent

logger = logging.getLogger(__name__)

def format_price(value: float, precision: int) -> str:
    """Formats a price to the correct decimal places."""
    return f"{value:,.{precision}f}"

def format_currency(value: float) -> str:
    """Formats a number to 2 decimal places."""
    return f"{value:,.2f}"

class TelegramNotifier:
    """
    Sends notifications to Telegram and handles interactive commands.
    """
    
    def __init__(self, bot_instance: Optional[Any] = None):
        self.token = os.getenv("TELEGRAM_BOT_TOKEN")
        self.chat_id = os.getenv("TELEGRAM_CHAT_ID")
        self.base_url = f"https://api.telegram.org/bot{self.token}/sendMessage"
        self.bot_instance = bot_instance # MomentumBot instance for data access

    async def notify(
        self, 
        message: str, 
        msg_type: str, 
        instrument_id: Optional[Any] = None,
        trade_plan_id: Optional[Any] = None,
        position_id: Optional[Any] = None
    ):
        """
        Sends a message and logs to DB.
        """
        if not self.token or not self.chat_id:
            logger.warning("Telegram NOT configured. Notification skipped.")
            return

        payload = {
            "chat_id": self.chat_id,
            "text": message,
            "parse_mode": "HTML"
        }

        status = "SENT"
        failure_reason = None

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(self.base_url, json=payload, timeout=10)
                response.raise_for_status()
        except Exception as e:
            logger.error(f"Failed to send Telegram notification: {e}")
            status = "FAILED"
            failure_reason = str(e)

        # Record in DB
        if store:
            try:
                async with store.session() as session:
                    event = NotificationEvent(
                        type=msg_type,
                        instrument_id=instrument_id,
                        trade_plan_id=trade_plan_id,
                        position_id=position_id,
                        status=status,
                        failure_reason=failure_reason,
                        payload_json=payload
                    )
                    session.add(event)
                    await session.commit()
            except Exception as e:
                logger.error(f"Failed to log notification to DB: {e}")

    async def send_trade_open(self, symbol: str, direction: str, price: float, qty: float):
        precision = 2
        qty_precision = 2
        if self.bot_instance:
            info = await self.bot_instance.data_service.get_instrument_info(symbol)
            precision = info.get('pricePrecision', 2)
            qty_precision = info.get('quantityPrecision', 2)

        msg = (
            f"<b>🟢 TRADE OPENED</b>\n"
            f"Symbol: {symbol}\n"
            f"Dir: {direction}\n"
            f"Price: {format_price(price, precision)}\n"
            f"Qty: {format_price(qty, qty_precision)}"
        )
        await self.notify(msg, "TRADE_OPEN")

    async def send_trade_close(self, symbol: str, reason: str, pnl: float):
        msg = (
            f"<b>🔴 TRADE CLOSED</b>\n"
            f"Symbol: {symbol}\n"
            f"Reason: {reason}\n"
            f"Realised PnL: ${format_currency(pnl)}"
        )
        await self.notify(msg, "TRADE_CLOSE")

    async def send_halt(self, reason: str):
        msg = f"<b>⚠️ SYSTEM HALTED</b>\nReason: {reason}"
        await self.notify(msg, "HALT")

    # Command Handlers
    async def cmd_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if str(update.effective_chat.id) != self.chat_id: return
        await update.message.reply_text("💓 Heartbeat: System active and monitoring.")

    async def cmd_account(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if str(update.effective_chat.id) != self.chat_id: return
        try:
            account = await self.bot_instance.client.futures_account()
            equity = float(account['totalMarginBalance'])
            avail = float(account['availableBalance'])
            msg = (
                f"<b>💰 Account Summary</b>\n"
                f"Total Equity: ${format_currency(equity)}\n"
                f"Available: ${format_currency(avail)}"
            )
            await update.message.reply_html(msg)
        except Exception as e:
            await update.message.reply_text(f"❌ Error fetching account: {e}")

    async def cmd_positions(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if str(update.effective_chat.id) != self.chat_id: return
        try:
            pos = await store.get_open_position()
            if not pos:
                await update.message.reply_text("🫙 No open positions.")
                return

            # Fetch live data
            symbol = pos.symbol # Assuming Position has symbol or we lookup
            # For now we use the instrument_id and assuming we can get symbol
            # Re-fetch symbol if needed, but let's assume it's available or we fetch via exchange
            ticker = await self.bot_instance.client.futures_symbol_ticker(symbol=pos.symbol)
            cur_price = float(ticker['price'])
            
            # PnL Calculation (Simplified)
            pnl = 0
            if pos.direction == "LONG":
                pnl = (cur_price - float(pos.entry_price_avg)) * float(pos.qty_filled)
            else:
                pnl = (float(pos.entry_price_avg) - cur_price) * float(pos.qty_filled)

            # Fetch matching trade plan for SL/TP
            # (In a real scenario, TP/SL are in the protective orders on exchange too)
            
            # Fetch precision
            precision = 2
            if self.bot_instance:
                info = await self.bot_instance.data_service.get_instrument_info(pos.symbol)
                precision = info.get('pricePrecision', 2)

            msg = (
                f"<b>📊 Open Position: {pos.symbol}</b>\n"
                f"Direction: {pos.direction}\n"
                f"Entry: {format_price(float(pos.entry_price_avg), precision)}\n"
                f"Current: {format_price(cur_price, precision)}\n"
                f"PnL: ${format_currency(pnl)}\n"
                f"Status: {pos.status}"
            )
            await update.message.reply_html(msg)
        except Exception as e:
            await update.message.reply_text(f"❌ Error fetching positions: {e}")

    async def cmd_restart(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if str(update.effective_chat.id) != self.chat_id: return
        await update.message.reply_text("🔄 Restarting bot service...")
        logger.info("Restart command received. Exiting for systemd restart.")
        # Exit process - systemd will restart it
        os._exit(0)

    async def start_listener(self):
        """Starts the interactive command listener."""
        if not self.token: return
        
        app = ApplicationBuilder().token(self.token).build()
        
        # Add Menu Commands
        await app.bot.set_my_commands([
            BotCommand("status", "heartbeat"),
            BotCommand("positions", "report open positions"),
            BotCommand("account", "account equity"),
            BotCommand("restart", "restart the bot")
        ])
        
        app.add_handler(CommandHandler("status", self.cmd_status))
        app.add_handler(CommandHandler("positions", self.cmd_positions))
        app.add_handler(CommandHandler("account", self.cmd_account))
        app.add_handler(CommandHandler("restart", self.cmd_restart))
        
        logger.info("Telegram command listener started.")
        await app.initialize()
        await app.start()
        await app.updater.start_polling()
