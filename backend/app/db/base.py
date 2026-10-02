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
    """通用 SQLite 轻迁移：对照 ORM 元数据，给旧库自动补缺失列（TEXT 兜底类型）。

    修历史坑：模型演进加列（status/started_at/heat_id 等）而旧库没有，导致
    select 整表时 no such column——与其逐列手写，不如对表元数据自动补齐。
    """
    for table_name, table in Base.metadata.tables.items():
        existing = await _get_sqlite_columns(conn, table_name)
        for col in table.columns:
            if col.name not in existing:
                await _add_sqlite_column(conn, table_name, col.name, "TEXT", existing)


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
