import asyncio
import os
from dotenv import load_dotenv
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from bot.data.models import Base, Instrument
from bot.data.store import DataStore

load_dotenv()

DEFAULT_WATCHLIST = [
    ("BTCUSDT", 1),
    ("ETHUSDT", 2),
    ("SOLUSDT", 3),
    ("BNBUSDT", 4),
    ("XRPUSDT", 5),
    ("ADAUSDT", 6),
    ("AVAXUSDT", 7),
    ("DOGEUSDT", 8),
    ("DOTUSDT", 9),
    ("LINKUSDT", 10),
    ("MATICUSDT", 11),
    ("NEARUSDT", 12),
    ("LTCUSDT", 13),
    ("BCHUSDT", 14),
    ("TRXUSDT", 15),
]

async def seed():
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        print("Error: DATABASE_URL not set in environment.")
        return

    # For seeding, we might need the sync driver if using alembic, 
    # but here we use the async store we just built.
    store = DataStore(db_url)
    
    print(f"Initializing database at {db_url}...")
    await store.init_db()
    
    async with store.session() as session:
        for symbol, rank in DEFAULT_WATCHLIST:
            # Check if exists
            from sqlalchemy import select
            result = await session.execute(select(Instrument).where(Instrument.symbol == symbol))
            if result.scalar_one_or_none():
                print(f"Skipping {symbol}, already exists.")
                continue
            
            instrument = Instrument(
                symbol=symbol,
                liquidity_rank=rank,
                is_active=True
            )
            session.add(instrument)
            print(f"Added {symbol} (Rank {rank})")
        
        await session.commit()
    
    print("Seeding complete.")

if __name__ == "__main__":
    asyncio.run(seed())
