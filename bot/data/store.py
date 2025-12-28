import os
from contextlib import asynccontextmanager
from typing import AsyncGenerator, Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy import select
from bot.data.models import Base, Instrument, ParameterBundle, Position, SystemHaltState, CooldownState

class DataStore:
    def __init__(self, db_url: str):
        self.engine = create_async_engine(db_url, echo=False)
        self.async_session = async_sessionmaker(
            self.engine, expire_on_commit=False, class_=AsyncSession
        )

    @asynccontextmanager
    async def session(self) -> AsyncGenerator[AsyncSession, None]:
        async with self.async_session() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    async def init_db(self):
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    async def get_active_instruments(self) -> list[Instrument]:
        async with self.session() as session:
            result = await session.execute(
                select(Instrument).where(Instrument.is_active == True).order_by(Instrument.liquidity_rank)
            )
            return list(result.scalars().all())

    async def get_active_bundle(self, instrument_id: UUID) -> Optional[ParameterBundle]:
        async with self.session() as session:
            result = await session.execute(
                select(ParameterBundle).where(
                    ParameterBundle.instrument_id == instrument_id,
                    ParameterBundle.is_active == True
                )
            )
            return result.scalar_one_or_none()

    async def get_open_position(self) -> Optional[Position]:
        async with self.session() as session:
            result = await session.execute(
                select(Position).where(Position.status.in_(['OPENING', 'OPEN', 'CLOSING']))
            )
            return result.scalar_one_or_none()

    async def is_system_halted(self) -> bool:
        async with self.session() as session:
            result = await session.execute(select(SystemHaltState))
            state = result.scalar_one_or_none()
            return state.is_halted if state else False

    async def get_cooldown_state(self) -> Optional[CooldownState]:
        async with self.session() as session:
            result = await session.execute(select(CooldownState))
            return result.scalar_one_or_none()

# Global store instance for convenience (configured via main entry point)
store: Optional[DataStore] = None

def init_store(db_url: str):
    global store
    store = DataStore(db_url)
    return store
