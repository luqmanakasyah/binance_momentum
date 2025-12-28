import asyncio
import os
import logging
from decimal import Decimal
from datetime import datetime, timezone
from dotenv import load_dotenv
from bot.data.store import init_store
from bot.data.service import MarketDataService
from bot.data.indicators import IndicatorEngine
from bot.core.signal import SignalEngine
from bot.optimization.runner import OptimizationRunner
from bot.data.models import OptimisationRun, ParameterBundle, Instrument
from binance import AsyncClient
from sqlalchemy import select

load_dotenv()

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("Optimizer")

async def run_initial_optimization():
    db_url = os.getenv("DATABASE_URL")
    api_key = os.getenv("BINANCE_API_KEY")
    api_secret = os.getenv("BINANCE_API_SECRET")
    
    store = init_store(db_url)
    client = await AsyncClient.create(api_key, api_secret)
    data_service = MarketDataService(client)
    
    # Initialize Engines
    indicator_engine = IndicatorEngine()
    signal_engine = SignalEngine()
    runner = OptimizationRunner(indicator_engine, signal_engine)
    
    # 1. Create optimization run record
    async with store.session() as session:
        opt_run = OptimisationRun(
            run_type='DEPLOYMENT',
            triggered_at=datetime.now(timezone.utc),
            status='PARTIAL', # Update to SUCCESS later
            training_window_days=180,
            validation_window_days=45,
            strategy_spec_version='PBC_v2.2'
        )
        session.add(opt_run)
        await session.commit()
        await session.refresh(opt_run)
        
        opt_run_id = opt_run.optimisation_run_id

    instruments = await store.get_active_instruments()
    logger.info(f"Found {len(instruments)} active instruments for optimization.")

    for inst in instruments:
        logger.info(f"Optimizing {inst.symbol}...")
        try:
            # Fetch 225 days of data
            # Binance limit is often 500 or 1500 per call. 
            # 225 days of 1H = 5400 candles. Need more than one call or just fetch what we can for now.
            # Simplified: fetch last 1000 candles for demonstration if limit is an issue.
            df_1h, df_15m = await data_service.fetch_strategy_data(inst.symbol)
            
            if df_1h.empty or df_15m.empty:
                logger.warning(f"No data for {inst.symbol}, skipping.")
                continue
                
            best_params = runner.optimize_instrument(df_1h, df_15m)
            
            if best_params:
                res = best_params["result"]
                logger.info(f"Best for {inst.symbol}: RSI {best_params['rsi_reference']}, Stop {best_params['stop_multiplier']}, Total R: {res.total_r:.2f}")
                
                async with store.session() as session:
                    # Create bundle
                    bundle = ParameterBundle(
                        instrument_id=inst.instrument_id,
                        bundle_version=1,
                        optimisation_run_id=opt_run_id,
                        atr_stop_multiplier=Decimal(str(round(best_params['stop_multiplier'], 1))),
                        vol_gate_type=best_params['type'],
                        atr_ma_length=best_params.get('ma_length'),
                        atr_percentile_threshold=best_params.get('threshold'),
                        rsi_reference=best_params['rsi_reference'],
                        selected_objective_value=Decimal(str(round(float(res.total_r), 4))),
                        selected_drawdown=Decimal(str(round(float(res.max_drawdown), 4))),
                        selected_trade_count=res.trade_count,
                        is_active=True,
                        active_from=datetime.now(timezone.utc)
                    )
                    session.add(bundle)
                    await session.commit()
            else:
                logger.warning(f"No valid params found for {inst.symbol}")
                
        except Exception as e:
            logger.error(f"Error optimizing {inst.symbol}: {e}", exc_info=True)

    # Mark run as SUCCESS
    async with store.session() as session:
        opt_run.status = 'SUCCESS'
        opt_run.completed_at = datetime.now(timezone.utc)
        await session.merge(opt_run)
        await session.commit()

    await client.close_connection()
    logger.info("Initial optimization complete.")

if __name__ == "__main__":
    asyncio.run(run_initial_optimization())
