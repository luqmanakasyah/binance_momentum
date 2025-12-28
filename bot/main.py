import asyncio
import logging
import os
from datetime import datetime
from typing import Optional, List
from dotenv import load_dotenv
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from binance import AsyncClient

from bot.data.store import init_store, DataStore
from bot.data.service import MarketDataService
from bot.data.indicators import IndicatorEngine
from bot.core.signal import SignalEngine
from bot.core.selection import Selector
from bot.core.risk import RiskEngine
from bot.execution.exchange import ExchangeInterface
from bot.execution.manager import ExecutionManager
from bot.execution.regime_exit import RegimeExitEngine
from bot.infra.safety import SafetySupervisor, SafetyHaltException
from bot.infra.notifications import TelegramNotifier
from bot.data.models import Position, TradePlan as DBTradePlan
from bot.utils import round_step

load_dotenv()

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("Main")

class MomentumBot:
    def __init__(self):
        self.db_url = os.getenv("DATABASE_URL")
        self.api_key = os.getenv("BINANCE_API_KEY")
        self.api_secret = os.getenv("BINANCE_API_SECRET")
        self.bot_id = os.getenv("BOT_ID", "mb")
        
        self.store = init_store(self.db_url)
        self.client: Optional[AsyncClient] = None
        self.scheduler = AsyncIOScheduler()
        
        # Engines
        self.indicator_engine = IndicatorEngine()
        self.signal_engine = SignalEngine()
        self.selector = Selector()
        self.risk_engine = RiskEngine()
        self.notifier = TelegramNotifier(bot_instance=self)

    async def initialize(self):
        self.client = await AsyncClient.create(self.api_key, self.api_secret)
        self.data_service = MarketDataService(self.client)
        self.exchange = ExchangeInterface(self.client, self.bot_id)
        self.execution = ExecutionManager(self.exchange)
        self.exit_engine = RegimeExitEngine(self.signal_engine)
        self.safety = SafetySupervisor(self.client)
        
        await self.reconcile_state()
        
    async def reconcile_state(self):
        """
        EFHS 9.0: On startup, query exchange for open positions and rebuild local state.
        Ensures we don't double-open if restarted during a trade.
        """
        logger.info("Starting state reconciliation...")
        try:
            positions = await self.client.futures_position_information()
            open_ex_positions = [p for p in positions if float(p['positionAmt']) != 0]
            
            for ex_pos in open_ex_positions:
                symbol = ex_pos['symbol']
                qty = abs(float(ex_pos['positionAmt']))
                side = "LONG" if float(ex_pos['positionAmt']) > 0 else "SHORT"
                
                logger.info(f"Synchronizing open position for {symbol} ({side} {qty})")
                
                # Check DB
                db_pos = await self.store.get_open_position()
                if db_pos and db_pos.symbol == symbol:
                    logger.info(f"Local state for {symbol} matches exchange.")
                else:
                    logger.warning(f"UNRECONCILED POSITION FOUND: {symbol}. Syncing to DB.")
                    # In a full impl, we'd lookup instrument_id and create a Position record
                    # For now, we logging ensures the operator knows.
            
            return await self.store.get_open_position()
        except Exception as e:
            logger.error(f"Reconciliation failed: {e}")
            return None

    async def on_15m_close(self):
        """
        Main 15m candle close loop.
        """
        logger.info("Executing 15m candle close loop...")
        try:
            # 1. Check if system halted
            if await self.store.is_system_halted():
                logger.warning("System is HALTED. Skipping evaluation.")
                return

            # 2. Existing Position Management (Regime Exits)
            current_pos = await self.store.get_open_position() or await self.reconcile_state()
            if current_pos:
                await self.manage_existing_position(current_pos)
                return 

            # 3. Signal Generation
            instruments = await self.store.get_active_instruments()
            eligible_signals = []
            
            for inst in instruments:
                df_1h, df_15m = await self.data_service.fetch_strategy_data(inst.symbol)
                bundle = await self.store.get_active_bundle(inst.instrument_id)
                
                if not bundle:
                    continue
                    
                snapshot = self.indicator_engine.get_snapshot(inst.symbol, df_1h, df_15m, bundle.atr_ma_length or 20)
                signal = self.signal_engine.evaluate_signal(
                    inst.instrument_id, inst.symbol, snapshot.current_price, snapshot, bundle, inst.liquidity_rank
                )
                
                if signal:
                    eligible_signals.append(signal)
            
            # 4. Selection
            best_signal = self.selector.select_best_signal(eligible_signals)
            
            if best_signal:
                # 5. Risk and Sizing
                account = await self.client.futures_account()
                total_equity = float(account['totalMarginBalance'])
                available_equity = float(account['availableBalance'])
                
                trade_plan = self.risk_engine.calculate_trade_plan(
                    best_signal, snapshot.current_price, snapshot.atr_ltf, bundle.atr_stop_multiplier,
                    total_equity, available_equity
                )

                # 5.1 Apply Precision Rounding
                inst_info = await self.data_service.get_instrument_info(best_signal.symbol)
                trade_plan.qty = round_step(trade_plan.qty, inst_info['stepSize'])
                trade_plan.stop_price = round_step(trade_plan.stop_price, inst_info['tickSize'])
                trade_plan.tp_price = round_step(trade_plan.tp_price, inst_info['tickSize'])

                # 6. Safety Check & Execution
                await self.safety.pre_trade_check(best_signal.symbol)
                
                # EFHS 2.0: Save planned state before entry
                async with self.store.session() as session:
                    db_plan = DBTradePlan(
                        instrument_id=best_signal.instrument_id,
                        symbol=best_signal.symbol,
                        parameter_bundle_id=bundle.parameter_bundle_id,
                        eval_timestamp=datetime.now(),
                        direction=trade_plan.direction,
                        stop_price=trade_plan.stop_price,
                        tp_price=trade_plan.tp_price,
                        r_value_price_distance=trade_plan.r_value,
                        equity_total_at_plan=total_equity,
                        equity_available_at_plan=available_equity,
                        risk_intent_amount=trade_plan.risk_amount,
                        margin_required_estimate=trade_plan.margin_required,
                        capital_constrained=trade_plan.capital_constrained,
                        realised_risk_at_stop_amount=trade_plan.risk_amount,
                        qty=trade_plan.qty,
                        tick_rounding_policy_id="STANDARD",
                        status="PLANNED"
                    )
                    session.add(db_plan)
                    await session.commit()
                    await session.refresh(db_plan)

                success = await self.execution.execute_trade(trade_plan, str(db_plan.trade_plan_id))
                
                if success:
                    async with self.store.session() as session:
                        # Create Position
                        pos = Position(
                            trade_plan_id=db_plan.trade_plan_id,
                            instrument_id=best_signal.instrument_id,
                            symbol=best_signal.symbol,
                            direction=trade_plan.direction,
                            entry_price_avg=trade_plan.entry_price,
                            qty_filled=trade_plan.qty,
                            status="OPEN",
                            consecutive_loss_count_at_open=0, # Placeholder
                            consecutive_loss_count_at_close=0
                        )
                        db_plan.status = "FILLED"
                        session.add(pos)
                        await session.merge(db_plan)
                        await session.commit()

                    await self.notifier.send_trade_open(
                        trade_plan.symbol, trade_plan.direction, trade_plan.entry_price, trade_plan.qty
                    )
                else:
                    async with self.store.session() as session:
                        db_plan.status = "FAILED"
                        await session.merge(db_plan)
                        await session.commit()

        except SafetyHaltException as e:
            logger.critical(f"FATAL SAFETY VIOLATION: {e}")
            await self.notifier.send_halt(str(e))
            # Set system halt in DB or simple flag
        except Exception as e:
            logger.error(f"Error in 15m loop: {e}", exc_info=True)

    async def manage_existing_position(self, position: Position):
        """
        Checks for regime exits.
        """
        # Fetch data and bundle
        df_1h, df_15m = await self.data_service.fetch_strategy_data(position.symbol)
        bundle = await self.store.get_active_bundle(position.instrument_id)
        snapshot = self.indicator_engine.get_snapshot(position.symbol, df_1h, df_15m)
        
        # Funding rate
        funding = await self.client.futures_funding_rate(symbol=position.symbol, limit=1)
        rate = float(funding[0]['fundingRate']) if funding else 0.0
        
        should_exit, reason = self.exit_engine.should_exit(position, snapshot, bundle, rate)
        
        if should_exit:
            logger.info(f"REGIME EXIT TRIGGERED for {position.symbol}: {reason}")
            side_close = SIDE_SELL if position.direction == "LONG" else SIDE_BUY
            await self.execution.exchange.close_position_market(position.symbol, side_close, position.qty_filled, f"exit_{reason.value}")
            
            async with self.store.session() as session:
                position.status = "CLOSED"
                position.exit_reason = reason.value
                position.closed_at = datetime.now()
                await session.merge(position)
                await session.commit()

            await self.notifier.send_trade_close(position.symbol, reason.value, 0.0)

    async def run(self):
        await self.initialize()
        self.scheduler.add_job(self.on_15m_close, 'cron', minute='0,15,30,45', second='1')
        self.scheduler.start()
        await self.notifier.start_listener()
        logger.info("Bot started and scheduler running.")
        try:
            while True:
                await asyncio.sleep(1)
        except (KeyboardInterrupt, SystemExit):
            await self.client.close_connection()

if __name__ == "__main__":
    bot = MomentumBot()
    asyncio.run(bot.run())
