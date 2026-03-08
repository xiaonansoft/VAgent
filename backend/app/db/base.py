from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy import text
from app.core.config import settings
import os

DATABASE_URL = os.getenv("DATABASE_URL", settings.DATABASE_URL)

engine = create_async_engine(DATABASE_URL, echo=True)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

class Base(DeclarativeBase):
    pass

async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        if conn.dialect.name == "sqlite":
            await _ensure_sqlite_columns(conn)

async def _ensure_sqlite_columns(conn) -> None:
    heats_columns = await _get_sqlite_columns(conn, "heats")
    await _add_sqlite_column(conn, "heats", "equilibrium_final_temp", "REAL", heats_columns)
    await _add_sqlite_column(conn, "heats", "trace_id", "TEXT", heats_columns)

    advice_columns = await _get_sqlite_columns(conn, "advice_logs")
    await _add_sqlite_column(conn, "advice_logs", "tool_calls", "TEXT", advice_columns)
    await _add_sqlite_column(conn, "advice_logs", "context", "TEXT", advice_columns)
    await _add_sqlite_column(conn, "advice_logs", "created_at", "TEXT", advice_columns)

async def _get_sqlite_columns(conn, table_name: str) -> set[str]:
    result = await conn.execute(text(f"PRAGMA table_info({table_name})"))
    rows = result.mappings().all()
    return {row["name"] for row in rows}

async def _add_sqlite_column(conn, table_name: str, column_name: str, column_type: str, existing: set[str]) -> None:
    if column_name in existing:
        return
    await conn.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}"))

async def get_db():
    async with AsyncSessionLocal() as session:
        yield session
