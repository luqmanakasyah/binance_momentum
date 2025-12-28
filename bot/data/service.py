import pandas as pd
import logging
from binance import AsyncClient
from binance.enums import *

logger = logging.getLogger(__name__)

class MarketDataService:
    """
    Fetches and prepares OHLCV data from Binance.
    """
    
    def __init__(self, client: AsyncClient):
        self.client = client

    async def get_candles(self, symbol: str, interval: str, limit: int = 500) -> pd.DataFrame:
        """
        Fetches klines and returns as a cleaned pandas DataFrame.
        """
        try:
            klines = await self.client.futures_klines(
                symbol=symbol,
                interval=interval,
                limit=limit
            )
            
            df = pd.DataFrame(klines, columns=[
                'timestamp', 'open', 'high', 'low', 'close', 'volume',
                'close_time', 'quote_asset_volume', 'number_of_trades',
                'taker_buy_base_asset_volume', 'taker_buy_quote_asset_volume', 'ignore'
            ])
            
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
            df.set_index('timestamp', inplace=True)
            
            numeric_cols = ['open', 'high', 'low', 'close', 'volume']
            df[numeric_cols] = df[numeric_cols].apply(pd.to_numeric, axis=1)
            
            # Ensure index is localized to UTC if not already
            if df.index.tz is None:
                df.index = df.index.tz_localize('UTC')
                
            return df[numeric_cols]

        except Exception as e:
            logger.error(f"Failed to fetch candles for {symbol} ({interval}): {e}")
            return pd.DataFrame()

    async def fetch_strategy_data(self, symbol: str):
        """
        Fetches both 1H and 15m data needed for evaluation.
        """
        df_1h = await self.get_candles(symbol, KLINE_INTERVAL_1HOUR, limit=250)
        df_15m = await self.get_candles(symbol, KLINE_INTERVAL_15MINUTE, limit=250)
        return df_1h, df_15m
