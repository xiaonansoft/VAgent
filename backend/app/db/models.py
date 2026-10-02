from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional, Any

from sqlalchemy import String, Float, Boolean, JSON, DateTime, Integer, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from ..schemas import HeatStatus
from .base import Base

# ============================================================================
# 迁移说明（本项目未使用 Alembic，采用「手动迁移 SQL」; 已在库表按下列脚本补齐）
#
# SQLite 支持 ALTER TABLE ADD COLUMN，但不支持给已有列加 REFERENCES，
# 因此 heat_id 外键在旧库上只表现为「带索引的普通列」，参照完整性由应用层保证。
#
# --- heats ---
# ALTER TABLE heats ADD COLUMN status         VARCHAR(32) DEFAULT 'CREATED';
# ALTER TABLE heats ADD COLUMN started_at     TIMESTAMP;
# ALTER TABLE heats ADD COLUMN closed_at      TIMESTAMP;
# UPDATE heats SET status = 'ARCHIVED' WHERE status IS NULL;
# CREATE INDEX IF NOT EXISTS ix_heats_status  ON heats (status);
#
# --- advice_logs ---
# ALTER TABLE advice_logs ADD COLUMN heat_id            VARCHAR;
# ALTER TABLE advice_logs ADD COLUMN overturned         BOOLEAN DEFAULT 0;
# ALTER TABLE advice_logs ADD COLUMN overturn_reason    VARCHAR;
# ALTER TABLE advice_logs ADD COLUMN overturn_by        VARCHAR;
# ALTER TABLE advice_logs ADD COLUMN overturned_at      TIMESTAMP;
# ALTER TABLE advice_logs ADD COLUMN arbitration_result BOOLEAN;
# CREATE INDEX IF NOT EXISTS ix_advice_logs_heat_id ON advice_logs (heat_id);
#
# 注：advice_logs.trace_id 已存在，无需新增。
# 若后续引入 Alembic，以上内容对应一次 revision：
#   op.add_column('heats', sa.Column('status', sa.String(32), nullable=False, server_default='CREATED'))
#   op.add_column('heats', sa.Column('started_at', sa.DateTime(), nullable=True))
#   op.add_column('heats', sa.Column('closed_at', sa.DateTime(), nullable=True))
#   op.create_index('ix_heats_status', 'heats', ['status'])
#   op.add_column('advice_logs', sa.Column('heat_id', sa.String(), nullable=True))
#   op.create_index('ix_advice_logs_heat_id', 'advice_logs', ['heat_id'])
#   op.add_column('advice_logs', sa.Column('overturned', sa.Boolean(), nullable=False, server_default='0'))
#   op.add_column('advice_logs', sa.Column('overturn_reason', sa.String(), nullable=True))
#   op.add_column('advice_logs', sa.Column('overturn_by', sa.String(), nullable=True))
#   op.add_column('advice_logs', sa.Column('overturned_at', sa.DateTime(), nullable=True))
#   op.add_column('advice_logs', sa.Column('arbitration_result', sa.Boolean(), nullable=True))
# ============================================================================


class Heat(Base):
    __tablename__ = "heats"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    heat_id: Mapped[str] = mapped_column(String, unique=True, index=True)
    furnace_id: Mapped[str] = mapped_column(String)

    # A3 · Heat 锚点: 炉次生命周期状态（取值见 schemas.HeatStatus，以字符串持久化便于迁移）
    status: Mapped[str] = mapped_column(
        String(32), default=HeatStatus.CREATED.value, index=True,
        comment="CREATED/CHARGING/BLOWING/PENDING_CONFIRM/CONFIRMED/ARCHIVED/EXCEPTION")
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    closed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    l1_recipe: Mapped[dict[str, Any]] = mapped_column(JSON)
    l2_final_temp: Mapped[float] = mapped_column(Float)
    equilibrium_final_temp: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    actual_final_temp: Mapped[float] = mapped_column(Float)
    actual_analysis: Mapped[dict[str, Any]] = mapped_column(JSON)
    advice_adopted: Mapped[bool] = mapped_column(Boolean)
    trace_id: Mapped[Optional[str]] = mapped_column(String, index=True, nullable=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))


class AdviceLog(Base):
    __tablename__ = "advice_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    trace_id: Mapped[Optional[str]] = mapped_column(String, index=True, nullable=True)

    # A3 · Heat 锚点: 建议归属到具体炉次（旧库无外键约束，仅索引 + 应用层保证）
    heat_id: Mapped[Optional[str]] = mapped_column(
        String, ForeignKey("heats.heat_id"), index=True, nullable=True)

    message: Mapped[str] = mapped_column(String)
    reply: Mapped[str] = mapped_column(String)
    tool_calls: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    context: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))

    # A2 · 人工推翻建议记录（对应 schemas.OverturnRecord 与事件 ADVICE_OVER TURNED）
    overturned: Mapped[bool] = mapped_column(Boolean, default=False)
    overturn_reason: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    overturn_by: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    overturned_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    arbitration_result: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
